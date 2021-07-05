import argparse
import asyncio
import logging

from aiortc import (
    RTCIceCandidate,
    RTCPeerConnection,
    RTCSessionDescription,
    VideoStreamTrack,
)
from media import MediaBlackhole, MediaRecorder
from signaling import BYE, ICE_DONE, add_signaling_arguments, create_signaling


async def create_data_channel(pc):
    @pc.on("datachannel")
    def on_datachannel(channel):
        async def send_movements():
            while True:
                channel.send((30).to_bytes(2, byteorder="big", signed=True))
                await asyncio.sleep(2)
                channel.send((-30).to_bytes(2, byteorder="big", signed=True))
                await asyncio.sleep(2)

        print(channel.label, "-", "created by remote party")
        asyncio.ensure_future(send_movements())

        @channel.on("message")
        def on_message(message):
            print("Got Message")


async def run(pc, recorder, signaling, role):
    @pc.on("track")
    def on_track(track):
        if track.kind == "video":
            print("Receiving %s" % track.kind)
            recorder.addTrack(track)

    # connect signaling
    await signaling.connect()

    # consume signaling
    while True:
        try:
            obj = await signaling.receive()
        except asyncio.CancelledError as e:
            # Gets thrown when the connection is close
            break

        if isinstance(obj, RTCSessionDescription):
            await pc.setRemoteDescription(obj)
            await create_data_channel(pc)
            await recorder.start()

            if obj.type == "offer":
                # send answer
                await pc.setLocalDescription(await pc.createAnswer())
                await signaling.send(pc.localDescription)
        elif isinstance(obj, RTCIceCandidate):
            await pc.addIceCandidate(obj)
        elif obj is ICE_DONE:
            print("Ice Done")
        elif obj is BYE:
            print("Exiting")
            break


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Video stream from the command line")
    parser.add_argument("role", choices=["offer", "answer"])
    parser.add_argument("--play-from", help="Read the media from a file and sent it."),
    parser.add_argument("--record-to", help="Write received media to a file."),
    parser.add_argument("--verbose", "-v", action="count")
    add_signaling_arguments(parser)
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    # create signaling and peer connection
    signaling = create_signaling(args)
    pc = RTCPeerConnection()

    # create media sink
    if args.record_to:
        recorder = MediaRecorder(args.record_to)
    else:
        recorder = MediaBlackhole()

    # run event loop
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(
            run(
                pc=pc,
                recorder=recorder,
                signaling=signaling,
                role=args.role,
            )
        )
    except KeyboardInterrupt:
        pass
    finally:
        # cleanup
        loop.run_until_complete(recorder.stop())
        print("Recorder Stopped")
        loop.run_until_complete(signaling.close())
        print("Signalling stopped")
        loop.run_until_complete(pc.close())
        print("Peer connection closed")

