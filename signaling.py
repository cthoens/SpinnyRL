import asyncio
import json
import logging
import os
import random
import sys

from aiortc import RTCIceCandidate, RTCSessionDescription
from aiortc.sdp import candidate_from_sdp, candidate_to_sdp

import websockets

logger = logging.getLogger(__name__)
BYE = object()
ICE_DONE = object()


def object_from_string(message_str):
    message = json.loads(message_str)
    what = message["what"]
    if message["data"] != '':
        message = json.loads(message["data"])
    else:
        message = {}
    if what in ["answer", "offer"]:
        return RTCSessionDescription(**message)
    elif what == "iceCandidate":
        if "candidate" in message:
            candidate = candidate_from_sdp(message["candidate"].split(":", 1)[1])
            candidate.sdpMid = message["sdpMid"]
            candidate.sdpMLineIndex = message["sdpMLineIndex"]
            return candidate
        else:
            return ICE_DONE
    elif what == "hangup":
        return BYE
    else:
        raise Exception("Unknown message")


def object_to_string(obj):
    if isinstance(obj, RTCSessionDescription):
        message = {"what": "answer", "data": json.dumps({"type": obj.type, "sdp": obj.sdp})}
    elif isinstance(obj, RTCIceCandidate):
        message = {
            "candidate": "candidate:" + candidate_to_sdp(obj),
            "id": obj.sdpMid,
            "label": obj.sdpMLineIndex,
            "what": "candidate",
        }
    else:
        assert obj is BYE
        message = {"what": "hangup"}
    return json.dumps(message, sort_keys=True)


class Uv4lSignaling:
    def __init__(self):
        self._websocket = None

    async def connect(self):
        self._websocket = await websockets.client.connect('ws://192.168.178.40:8080/stream/webrtc')
        await self._websocket.send(
            json.dumps(
                {
                    "what": "call",
                    "options": {
                        "force_hw_vcodec": False,
                        "vformat": 10,
                        "trickle_ice": True
                    }
                }
            )
        )

    async def close(self):
        if self._websocket:
            try:
                await self.send(BYE)
                await self._websocket.close()
            except websockets.exceptions.ConnectionClosedOK as e:
                pass
            self._websocket = None

    async def receive(self):
        try:
            message = await self._websocket.recv()
        except websockets.exceptions.ConnectionClosedOK as e:
            raise asyncio.CancelledError
        return object_from_string(message)

    async def send(self, obj):
        message = object_to_string(obj)
        await self._websocket.send(message)


def add_signaling_arguments(parser):
    """
    Add signaling method arguments to an argparse.ArgumentParser.
    """
    parser.add_argument(
        "--signaling-host", default="127.0.0.1", help="Signaling host (tcp-socket only)"
    )
    parser.add_argument(
        "--signaling-port", default=1234, help="Signaling port (tcp-socket only)"
    )


def create_signaling(args):
    """
    Create a signaling method based on command-line arguments.
    """
    return Uv4lSignaling()

