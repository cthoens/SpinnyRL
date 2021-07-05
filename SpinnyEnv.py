from enum import Enum

from aiortc.rtcrtpreceiver import RemoteStreamTrack
from gym import spaces

from aiogym import AsyncEnv
import asyncio
import logging
import numpy as np
import random
import math
import cv2
from PIL import ImageDraw

from av import VideoFrame

from aiortc import (
    RTCIceCandidate,
    RTCPeerConnection,
    RTCSessionDescription,
    RTCDataChannel,
    VideoStreamTrack,
)
from signaling import Uv4lSignaling, BYE, ICE_DONE


class SpinnyEnv(AsyncEnv):

    def __init__(self):
        self.width = 320
        self.height = 240
        self.action_space = spaces.Discrete(40)
        self.observation_space = spaces.Box(low=0, high=255, shape=(self.height, self.width, 3), dtype=np.uint8)
        self.state = None
        self.target_angle = None
        self.target_dir = None
        self.steps_left = None
        self.interface = WebRTCInterface()
        self.arucoDict = cv2.aruco.Dictionary_get(cv2.aruco.DICT_6X6_100)
        self.arucoParams = cv2.aruco.DetectorParameters_create()

    async def step(self, action):
        await self.interface.wait_for_connection()

        if self.steps_left < 0:
            return np.array(self.state), 0, True, None
        self.steps_left -= 1

        step_count = action - self.action_space.n // 2
        await self.interface.send(step_count)
        await asyncio.sleep(abs(step_count) * 4.0 * (5.0 / 1000.0) + 0.5)
        self.state = await self.interface.get_next_frame()
        self.state = self.state.resize((self.width, self.height))
        self.state.save("obs.jpg")

        open_cv_image = np.array(self.state.convert('RGB'))
        # Convert RGB to BGR
        open_cv_image = open_cv_image[:, :, ::-1]
        corners, ids, rejected = cv2.aruco.detectMarkers(open_cv_image, self.arucoDict, parameters=self.arucoParams)

        if ids is None:
            reward = 0
        else:
            try:
                marker_id = 70
                index = ids.reshape(-1).tolist().index(marker_id)
                marker_corners = corners[index][0]

                # Augment camera image
                line_from = (marker_corners[0] + marker_corners[1]) * 0.5
                line_to = (marker_corners[2] + marker_corners[3]) * 0.5
                direction = line_to - line_from
                direction = direction / np.linalg.norm(direction)
                line_to = line_from + direction * 50
                line_to_target = line_from + self.target_dir * 50

                draw = ImageDraw.Draw(self.state)
                draw.line([*line_from, *line_to], fill=255, width=5)
                draw.line([*line_from, *line_to_target], fill=(0, 255, 0), width=5)

                # Calculate reward
                angle_deviation = math.acos(np.dot(direction, self.target_dir))
                reward = 180 - angle_deviation / (2 * math.pi) * 360
            except ValueError:
                reward = 0

        return np.array(self.state), reward, self.steps_left <= 0, None

    async def reset(self):
        self.steps_left = 10
        self.target_angle = random.randrange(0, 360) / 360 * (2 * math.pi)
        self.target_dir = np.array([math.cos(self.target_angle), math.sin(self.target_angle)])

        await self.interface.wait_for_connection()
        self.state = await self.interface.get_next_frame()
        self.state = self.state.resize((self.width, self.height))
        return np.array(self.state)

    async def render(self, mode='human'):
        pass

    async def close(self):
        await self.interface.close()


class WebRTCInterface:
    class State(Enum):
        NOT_CONNECTED = 1,
        CONNECTING = 2,
        CONNECTED = 3

    def __init__(self):
        self.signaling = Uv4lSignaling()
        self.pc = RTCPeerConnection()
        self.video_stream_track: VideoStreamTrack = None
        self.data_channel: RTCDataChannel = None
        self.state = self.State.NOT_CONNECTED

    async def get_next_frame(self):
        if self.video_stream_track._queue.qsize() == 0:
            frame: VideoFrame = await self.video_stream_track.recv()
        else:
            while self.video_stream_track._queue.qsize() > 0:
                frame: VideoFrame = await self.video_stream_track.recv()
        return frame.to_rgb().to_image()

    async def wait_for_connection(self):
        for tick in range(30):
            if self.state == self.State.CONNECTED:
                return
            elif self.state == self.state.CONNECTING:
                await asyncio.sleep(1)
            else:
                raise ValueError("Not connecting")
        raise ValueError("Connection timed out")

    async def send(self, steps: np.int):
        self.data_channel.send(steps.item().to_bytes(2, byteorder="big", signed=True))

    async def create_data_channel(self):
        @self.pc.on("datachannel")
        def on_data_channel(channel):
            logging.info(f"Data channel {channel.label} created by remote party")
            self.data_channel = channel
            if self.video_stream_track:
                self.state = self.State.CONNECTED

            @channel.on("message")
            def on_message(message):
                logging.info(f"Data channel: Got Message {message}")

    async def run(self):
        self.state = self.State.CONNECTING

        @self.pc.on("track")
        def on_track(track: RemoteStreamTrack):
            if track.kind == "video":
                logging.info("Receiving %s" % track.kind)
                self.video_stream_track = track
                if self.data_channel:
                    self.state = self.State.CONNECTED

        # connect signaling
        await self.signaling.connect()

        try:
            # consume signaling
            while True:
                try:
                    obj = await self.signaling.receive()
                except asyncio.CancelledError as e:
                    # Gets thrown when the connection is closed
                    break

                if isinstance(obj, RTCSessionDescription):
                    await self.pc.setRemoteDescription(obj)
                    await self.create_data_channel()

                    if obj.type == "offer":
                        # send answer
                        await self.pc.setLocalDescription(await self.pc.createAnswer())
                        await self.signaling.send(self.pc.localDescription)
                elif isinstance(obj, RTCIceCandidate):
                    await self.pc.addIceCandidate(obj)
                elif obj is ICE_DONE:
                    logging.info("Ice Done")
                elif obj is BYE:
                    logging.info("Exiting")
                    self.data_channel = None
                    self.video_stream_track = None
                    self.state = self.State.NOT_CONNECTED
                    break
        except KeyboardInterrupt:
            pass
        finally:
            # cleanup
            await self.signaling.close()
            logging.info("Signalling closed")
            await self.pc.close()
            logging.info("Peer connection closed")
            self.data_channel = None
            self.video_stream_track = None
            self.state = self.State.NOT_CONNECTED

    async def close(self):
        await self.signaling.send(BYE)


async def run():
    env = SpinnyEnv()
    future = asyncio.ensure_future(env.interface.run())
    await env.reset()
    await env.step(40)
    await env.close()
    await future


def main():
    import logging
    import sys

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    root.addHandler(handler)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(run())


if __name__ == '__main__':
    main()
