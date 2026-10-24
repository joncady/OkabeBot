"""Local stdio MCP server. Pi traffic is authenticated and encrypted by SSH."""

import base64
import re
from typing import Literal
from mcp.server.fastmcp import FastMCP, Image
from mcp.types import ToolAnnotations
from . import rendering
from . import voice as voice_tools

from .hardware import rpc
from .config import state_dir
from .transport import device
from . import character as character_tools

mcp = FastMCP("Hardware Lab")
voice_tools.register(mcp)
character_tools.register(mcp)


READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
WRITE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
)


@mcp.tool(annotations=READ)
def get_bot_status() -> dict:
    """Read the configured SwitchBot's battery, firmware and mode over Bluetooth."""
    return rpc({"op": "bot_status"})


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False
    )
)
def press_bot(request_id: str) -> dict:
    """Physically press the Bot ONCE. Use a unique ID (8–100 letters/digits/-/_) per
    intended press. Always reuse that ID if a response is lost or outcome is unknown.
    Confirmed means the Bot acknowledged actuation, not that an appliance changed state.
    """
    return rpc({"op": "press", "request_id": request_id})


@mcp.tool(annotations=WRITE)
def display_message(
    text: str,
    title: str = "",
    duration_seconds: int = 0,
    theme: Literal["ocean", "paper", "alert"] = "ocean",
) -> dict:
    """Show readable text on the Pi screen. Duration 0 stays until replaced;
    1–86400 seconds clears automatically. Short messages work best on 3.5 inches.
    Oversized text is rejected rather than silently clipped. Replaces current content.
    """
    if not 0 <= duration_seconds <= 86400:
        raise ValueError("duration_seconds must be 0–86400")
    img = rendering.message(text, title, theme)
    return rpc(
        {
            "op": "display",
            "kind": "message",
            "title": title,
            "text": text,
            "duration_seconds": duration_seconds,
            "png_base64": base64.b64encode(rendering.png(img)).decode(),
        }
    )


@mcp.tool(annotations=WRITE)
def display_image(
    path: str, fit: Literal["contain", "cover"] = "contain", duration_seconds: int = 0
) -> dict:
    """Display a local controller image file, resized to 480x320. contain preserves all of
    the image with margins; cover crops to fill. No URL fetching or code execution.
    Duration 0 stays until replaced, otherwise 1–86400 seconds.
    """
    if not 0 <= duration_seconds <= 86400:
        raise ValueError("duration_seconds must be 0–86400")
    img = rendering.load_image(path, fit)
    return rpc(
        {
            "op": "display",
            "kind": "image",
            "duration_seconds": duration_seconds,
            "png_base64": base64.b64encode(rendering.png(img)).decode(),
        }
    )


@mcp.tool(annotations=WRITE)
def clear_display() -> dict:
    """Replace screen content with a blank dark canvas and cancel its expiry timer."""
    return rpc({"op": "clear"})


@mcp.tool(annotations=READ)
def get_display_status() -> dict:
    """Read current display metadata and dimensions without changing the screen."""
    return rpc({"op": "status"})


@mcp.tool(annotations=READ)
def preview_display() -> Image:
    """Return the current rendered canvas as an image; not a camera view of the LCD."""
    result = rpc({"op": "preview"})
    if "error" in result:
        raise RuntimeError(result["error"])
    return Image(data=base64.b64decode(result["png_base64"]), format="png")


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
    )
)
def capture_camera(low_light: bool = False) -> Image:
    """Take and return a new 1280x960 camera photo. low_light adjusts exposure;
    it does not switch the hardware infrared lamps on or prove night vision.
    """
    result = rpc({"op": "camera_photo", "low_light": low_light})
    if "error" in result:
        raise RuntimeError(result["error"])
    return Image(data=base64.b64decode(result["jpeg_base64"]), format="jpeg")


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
    )
)
def record_camera(duration_seconds: int = 5, low_light: bool = False) -> dict:
    """Record a new silent 720p MP4 for 1–20 seconds and save it on the controller.
    Returns an absolute local path. Normal mode is 15 fps; low_light uses 10 fps
    and night exposure, not software-controlled IR illumination. No continuous
    background recording. Repeating this call records a NEW clip.
    """
    if type(duration_seconds) is not int or not 1 <= duration_seconds <= 20:
        raise ValueError("duration_seconds must be 1–20")
    result = rpc(
        {"op": "camera_record", "duration_seconds": duration_seconds, "low_light": low_light}
    )
    if "error" in result:
        raise RuntimeError(result["error"])
    filename = result.get("filename", "")
    if not re.fullmatch(r"[0-9a-f]{32}\.mp4", filename):
        raise RuntimeError("Invalid recording filename returned by Pi")
    directory = state_dir() / "recordings"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    endpoint = device("display")
    remote = endpoint.config["recordings_dir"] + "/" + filename
    try:
        endpoint.download(remote, path)
        if path.stat().st_size != result["bytes"]:
            raise RuntimeError("Recording download size mismatch")
    except Exception as exc:
        path.unlink(missing_ok=True)
        raise RuntimeError(
            "Clip recorded on Pi as "
            + filename
            + " but download failed; retrieve it rather than recording again"
        ) from exc
    return dict(result, local_path=str(path))


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
