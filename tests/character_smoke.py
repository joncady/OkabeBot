"""Live Okabe test: intentionally plays three named voice samples."""

import sys
import asyncio
import base64
import json
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
            names = {t.name for t in (await s.list_tools()).tools}
            assert {
                "character_speak",
                "character_expression",
                "list_character_voices",
                "set_character_voice",
            } <= names
            for voice, emotion in [("warm", "happy"), ("calm", "curious"), ("robotic", "excited")]:
                r = await s.call_tool(
                    "character_speak",
                    {
                        "text": "Hi, I'm Okabe. This is my %s voice. I'm ready to help with your hardware lab."
                        % voice,
                        "emotion": emotion,
                        "voice": voice,
                    },
                )
                assert not r.isError, r
                data = json.loads(next(c.text for c in r.content if c.type == "text"))
                assert data["spoken"] and data["animation"], data
                print(voice, data, flush=True)
            r = await s.call_tool("character_expression", {"emotion": "happy"})
            assert not r.isError, r
            p = await s.call_tool("preview_display", {})
            image = next(c for c in p.content if c.type == "image")
            (ROOT / ".local/character-live.png").write_bytes(base64.b64decode(image.data))
            print("All three voices and live display passed", flush=True)


asyncio.run(main())
