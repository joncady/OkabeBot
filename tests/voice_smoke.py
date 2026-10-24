"""Live voice test: speaks once, records five seconds, then replays the recording."""

import sys
import asyncio
import json
import wave
import struct
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


async def main():
    (ROOT / ".local").mkdir(exist_ok=True)
    async with stdio_client(
        StdioServerParameters(command=sys.executable, args=[str(ROOT / "server.py")])
    ) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            names = [t.name for t in (await s.list_tools()).tools]
            assert all(
                n in names
                for n in [
                    "speak",
                    "record_audio",
                    "play_audio",
                    "get_voice_status",
                    "get_button_events",
                ]
            )

            async def call(name, args={}):
                r = await s.call_tool(name, args)
                assert not r.isError, r
                d = json.loads(next(c.text for c in r.content if c.type == "text"))
                print(name, d, flush=True)
                return d

            await call("get_voice_status")
            await call(
                "speak",
                {
                    "text": "Hardware Lab is connected. Please say something for the microphone test."
                },
            )
            r = await call("record_audio", {"duration_seconds": 5})
            with wave.open(r["local_path"]) as w:
                assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 16000)
                raw = w.readframes(w.getnframes())
                samples = struct.unpack("<%dh" % (len(raw) // 2), raw)
                assert any(samples), "Microphone returned digital silence; check hardware routing"
                print(
                    "Microphone peak:",
                    max(abs(x) for x in samples),
                    "RMS:",
                    round((sum(x * x for x in samples) / len(samples)) ** 0.5, 1),
                    flush=True,
                )
            await call("play_audio", {"path": r["local_path"]})
            await call("get_button_events")
            (ROOT / ".local/voice-test.json").write_text(json.dumps(r))


asyncio.run(main())
