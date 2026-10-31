"""Python 3.7 character interface shared by controller and standalone satellites."""

from abc import ABC, abstractmethod
from functools import lru_cache
import json
import re
from pathlib import Path
from string import Template


class Character(ABC):
    """A character owns art, prompts, motion, avatar geometry, voice and scene choices."""

    def __init__(self, module_file):
        self.folder = Path(module_file).parent
        self.definition = self.read_json("character.json")
        if self.definition["id"] != self.folder.name or not re.fullmatch(
            r"[a-z][a-z0-9_-]{0,39}", self.folder.name
        ):
            raise ValueError("Character identity must match its directory")

    @property
    def identity(self):
        return self.definition["id"]

    def read_json(self, filename):
        return json.loads((self.folder / filename).read_text())

    def prompt(self, kind, **values):
        if kind not in ("persona", "welcome-persona"):
            raise ValueError("Unknown character prompt interface")
        return Template(" ".join((self.folder / (kind + ".md")).read_text().split())).substitute(
            values
        )

    def voice(self):
        # Actual recordings/transcripts remain in the owner's private voice manifest.
        return self.read_json("voice.json")

    def profile(self):
        return dict(
            name=self.definition["name"],
            style=self.identity,
            default_voice=self.voice()["default_voice"],
            persona=self.prompt("persona"),
            welcome_persona=self.prompt("welcome-persona"),
        )

    def motion(self):
        return self.read_json("motion.json")

    @lru_cache(maxsize=16)
    def avatar(self):
        return self.read_json("avatar.json")

    def assets(self, emotion="neutral", palette=None):
        from . import motion_catalog

        return dict(
            frames=[
                self.shapes(
                    emotion=emotion, palette=palette, mouth=mouth, phase=phase, motion={"head_x": 0}
                )
                for phase in (1, 0)
                for mouth in (0, 0.5, 1)
            ],
            avatar=self.avatar(),
            motion_catalog=motion_catalog(),
        )

    def portrait(self):
        return (self.folder / "portrait.png").read_bytes()

    def scenes(self):
        return self.definition["scenes"]

    def supports(self, capability):
        return capability in self.definition.get("capabilities", [])

    @abstractmethod
    def shapes(self, **state):
        """Return pixel primitives without hardware/network side effects."""

    def render(self, **state):
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (480, 320))
        draw = ImageDraw.Draw(image)
        for kind, box, color, width in self.shapes(**state):
            if kind == "line":
                draw.line(box, fill=color, width=max(1, round(width)))
            else:
                getattr(draw, kind)(box, fill=color)
        return image
