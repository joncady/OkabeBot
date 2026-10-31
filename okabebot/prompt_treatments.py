"""Private owner text-lab treatments, never device or memory authorization."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path

from .presence_control import read, write

FIELDS = {"routing", "continuation", "preference"}
LABELS = {
    "default": "Production default",
    "conversation_candidate": "Candidate conversational style",
    "native_candidate": "Best native-tool candidate · experimental",
    "custom": "My custom treatment",
}


def validate_prompts(value):
    if (
        not isinstance(value, dict)
        or set(value) - FIELDS
        or any(not isinstance(v, str) or not v.strip() or len(v) > 10000 for v in value.values())
        or len(json.dumps(value).encode()) > 18000
    ):
        raise ValueError("Use nonempty routing, continuation and conversation prompts within 18 KB")
    return deepcopy(value)


def defaults():
    from .conversation_agent import ROUTING, CONTINUATION
    from .conversation_prompts import PREFERENCE

    return {"routing": ROUTING, "continuation": CONTINUATION, "preference": PREFERENCE}


class Treatments:
    def __init__(self, folder):
        self.path = Path(folder) / "prompt-treatments.json"

    def snapshot(self):
        return self._snapshot(read(self.path, {}))

    def _snapshot(self, saved):
        if not isinstance(saved, dict):
            raise ValueError("Invalid saved treatment; restore the production default")
        candidate = json.loads(
            (Path(__file__).parent / "assets/prompt-treatments.json").read_text()
        )["native_candidate"]
        base = defaults()
        presets = {
            "default": base,
            "conversation_candidate": {
                **base,
                **{k: v for k, v in candidate.items() if k != "routing"},
            },
            "native_candidate": candidate,
            "custom": {**base, **validate_prompts(saved.get("custom", {}))},
        }
        selected = saved.get("selected", "default")
        if not isinstance(selected, str) or selected not in presets:
            raise ValueError("Invalid saved prompt treatment; restore the production default")
        prompts = presets[selected]
        fingerprint = hashlib.sha256(json.dumps(prompts, sort_keys=True).encode()).hexdigest()
        return {
            "selected": selected,
            "presets": [
                {"id": key, "label": label, "prompts": presets[key]}
                for key, label in LABELS.items()
            ],
            "receipt": {
                "id": selected,
                "hash": fingerprint,
                "scope": "owner_text_lab",
                "read_only": selected != "default",
                "memory_writes": selected == "default",
            },
        }

    def configure(self, data):
        if not isinstance(data, dict) or set(data) - {"selected", "prompts"}:
            raise ValueError("Choose a prompt treatment")
        if not isinstance(data.get("selected"), str) or data["selected"] not in LABELS:
            raise ValueError("Choose a known prompt treatment")
        if "prompts" in data and data["selected"] != "custom":
            raise ValueError("Save edited prompts as a custom treatment")
        saved = read(self.path, {})
        if not isinstance(saved, dict):
            saved = {}
        if data["selected"] == "default":
            try:
                validate_prompts(saved.get("custom", {}))
            except ValueError:
                saved.pop("custom", None)
        if "prompts" in data:
            prompts = validate_prompts(data["prompts"])
            if set(prompts) != FIELDS:
                raise ValueError("A custom treatment needs all three prompts")
            saved["custom"] = prompts
        saved["selected"] = data["selected"]
        # Preserve a bounded private source trail for feedback fingerprints.
        if "prompts" in data:
            history = saved.get("revisions", [])
            if not isinstance(history, list):
                history = []
            fingerprint = hashlib.sha256(json.dumps(prompts, sort_keys=True).encode()).hexdigest()
            saved["revisions"] = (
                [r for r in history if isinstance(r, dict) and r.get("hash") != fingerprint]
                + [{"hash": fingerprint, "prompts": prompts}]
            )[-8:]
        result = self._snapshot(saved)
        write(self.path, saved)
        return result

    def active(self):
        snapshot = self.snapshot()
        prompts = next(p["prompts"] for p in snapshot["presets"] if p["id"] == snapshot["selected"])
        return snapshot["receipt"], prompts if snapshot["selected"] != "default" else None
