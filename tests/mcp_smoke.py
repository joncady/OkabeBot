"""Live MCP integration check. No actuation unless --press is explicitly supplied."""

import asyncio
import base64
import json
from pathlib import Path
import sys
import uuid
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


async def main():
    (ROOT / ".local").mkdir(exist_ok=True)
    from PIL import Image

    Image.new("RGB", (480, 320), "#101e25").save(ROOT / ".local/preview.png")
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "server.py")])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            names = [t.name for t in (await session.list_tools()).tools]
            assert len(names) == 18, names
            print("Tools:", ", ".join(names), flush=True)

            async def call(name, args=None):
                r = await session.call_tool(name, args or {})
                assert not r.isError, r
                data = json.loads(next(c.text for c in r.content if c.type == "text"))
                assert "error" not in data, data
                print(name, data, flush=True)
                return data

            status = await call("get_bot_status")
            assert status["outcome"] == "confirmed" and status["mode"] == "press", status
            await call(
                "display_message", {"text": "Testing automatic expiry.", "duration_seconds": 1}
            )
            await asyncio.sleep(2)
            assert (await call("get_display_status"))["kind"] == "idle"
            await call("display_image", {"path": str(ROOT / ".local/preview.png")})
            await call("clear_display")
            await call(
                "display_message", {"title": "Connected", "text": "Your hardware lab is ready."}
            )
            preview = await session.call_tool("preview_display")
            assert not preview.isError
            image = next(c for c in preview.content if c.type == "image")
            (ROOT / ".local/live-preview.png").write_bytes(base64.b64decode(image.data))
            if "--press" in sys.argv:
                rid = "smoke-" + uuid.uuid4().hex
                first = await call("press_bot", {"request_id": rid})
                assert first["outcome"] == "confirmed", first
                repeat = await call("press_bot", {"request_id": rid})
                assert repeat["deduplicated"] is True
            print("Live MCP checks passed.", flush=True)


asyncio.run(main())
