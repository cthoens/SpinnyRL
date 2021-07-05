import asyncio
import websockets
import json

from aiortc import (
    RTCIceCandidate,
    RTCPeerConnection,
    RTCSessionDescription,
    VideoStreamTrack,
)

async def main():
    ws = await websockets.client.connect('ws://192.168.178.40:8080/stream/webrtc')
    res = await ws.send(
            json.dumps(
                {
                    "what": "call",
                    "options": {
                        "force_hw_vcodec": False,
                        "vformat": 30,
                        "trickle_ice": True
                    }
                }
            )
    )
    message_str = await ws.recv()
    message = json.loads(message_str)
    print(message["data"])
    pc = RTCPeerConnection()
    await pc.setRemoteDescription(RTCSessionDescription(**json.loads(message["data"])))


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(
            main()
        )
    except KeyboardInterrupt:
        pass
    # finally:
        # cleanup
