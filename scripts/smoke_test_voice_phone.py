"""Simulate a Twilio Media Stream connection against the voice websocket,
without placing a real phone call. Speaks the exact wire protocol Twilio
uses (connected/start handshake, streamSid/callSid, mu-law audio frames);
if the agent's greeting audio comes back over the socket, the whole
STT/LLM/TTS pipeline works through the real Twilio code path — Deepgram,
Qwen, and ElevenLabs are all reachable and wired correctly.

This does NOT exercise real caller audio into Deepgram (we only send
silence) or Twilio's own call-teardown behavior on a live call — it's a
fast, free check that the plumbing works, not a substitute for actually
dialing the number.

Usage:
    .venv\\Scripts\\python scripts\\smoke_test_voice_phone.py
    .venv\\Scripts\\python scripts\\smoke_test_voice_phone.py --url wss://localhost:8000/voice/twilio/media
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys

import websockets

DEFAULT_URL = "wss://maindesk.otito.site/voice/twilio/media"
STREAM_SID = "MZfaketeststreamsid00000000000000"
CALL_SID = "CAfaketestcallsid0000000000000000"
ACCOUNT_SID = "ACfaketestaccountsid00000000000000"


async def _sender(ws, stop_event: asyncio.Event) -> None:
    # 20ms of mu-law silence (0xFF) per Twilio's 8kHz frame convention.
    silence = base64.b64encode(b"\xff" * 160).decode()
    try:
        while not stop_event.is_set():
            await ws.send(json.dumps({
                "event": "media",
                "streamSid": STREAM_SID,
                "media": {"payload": silence},
            }))
            await asyncio.sleep(0.02)
    except websockets.exceptions.ConnectionClosed:
        pass


async def run(url: str, *, frames_wanted: int = 5, timeout_secs: float = 20) -> bool:
    print(f"connecting to {url} ...")
    async with websockets.connect(url, open_timeout=15) as ws:
        await ws.send(json.dumps({"event": "connected", "protocol": "Call", "version": "1.0.0"}))
        await ws.send(json.dumps({
            "event": "start",
            "sequenceNumber": "1",
            "streamSid": STREAM_SID,
            "start": {
                "accountSid": ACCOUNT_SID,
                "streamSid": STREAM_SID,
                "callSid": CALL_SID,
                "tracks": ["inbound"],
                "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1},
                "customParameters": {"from_number": "+15551234567", "to_number": "+14842707025"},
            },
        }))
        print("sent connected + start handshake, waiting for the agent's greeting audio...")

        stop_event = asyncio.Event()
        send_task = asyncio.create_task(_sender(ws, stop_event))

        media_frames = 0
        saw_clear = False
        try:
            async with asyncio.timeout(timeout_secs):
                async for raw in ws:
                    msg = json.loads(raw)
                    ev = msg.get("event")
                    if ev == "media":
                        media_frames += 1
                        if media_frames == 1:
                            payload_len = len(msg["media"]["payload"])
                            print(f"first outbound audio frame received ({payload_len} b64 chars)")
                        if media_frames >= frames_wanted:
                            break
                    elif ev == "clear":
                        saw_clear = True
                        print("received 'clear' event (barge-in signal)")
                    elif ev != "mark":
                        print("received event:", ev)
        except TimeoutError:
            print("timed out waiting for audio")
        finally:
            stop_event.set()
            send_task.cancel()

        print(f"\nTOTAL outbound audio frames received: {media_frames} (saw clear event: {saw_clear})")
        return media_frames > 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL, help="voice media websocket URL to test")
    args = parser.parse_args()

    passed = asyncio.run(run(args.url))
    if passed:
        print("RESULT: PASS — agent produced TTS audio over the real Twilio wire protocol.")
        sys.exit(0)
    print("RESULT: FAIL — no audio came back.")
    sys.exit(1)


if __name__ == "__main__":
    main()
