import sys
import asyncio
import json
import base64
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

root = Path(__file__).resolve().parents[1]


async def main():
    (root / ".local").mkdir(exist_ok=True)
    async with stdio_client(
        StdioServerParameters(command=sys.executable, args=[str(root / "server.py")])
    ) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            names = [t.name for t in (await s.list_tools()).tools]
            assert "record_camera" in names and "capture_camera" in names
            photo = await s.call_tool("capture_camera", {"low_light": True})
            assert not photo.isError, photo
            im = next(c for c in photo.content if c.type == "image")
            (root / ".local/night-mcp.jpg").write_bytes(base64.b64decode(im.data))
            clip = await s.call_tool("record_camera", {"duration_seconds": 5, "low_light": True})
            assert not clip.isError, clip
            data = json.loads(next(c.text for c in clip.content if c.type == "text"))
            (root / ".local/recording-result.json").write_text(json.dumps(data))
            print(json.dumps(data), flush=True)


asyncio.run(main())
