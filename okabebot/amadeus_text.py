"""Owner-only silent chat sharing preference policy, isolated from spoken sessions."""

import json
import re

from .amadeus_live import ProactiveConversation
from .amadeus_habits import preference
from .amadeus_onboarding import SYSTEM, KEY
from .presence_control import read, write


class TextConversation(ProactiveConversation):
    def __init__(self, folder, **kwargs):
        super().__init__(folder, state_key="conversation.text", **kwargs)
        self.turn_limit = 30

    @staticmethod
    def permitted(setup, cfg):
        return (
            bool(setup.get("profile"))
            and setup.get("paused") is False
            and setup.get("guest") is False
        )

    def send(self, text, generate, tool_turn=None, specs=None):
        if not isinstance(text, str) or not text.strip() or len(text) > 1000:
            raise ValueError("Enter a message of 1–1000 characters")
        with self.lock:
            with self.store() as s:
                setup = preference(s, SYSTEM, KEY, {})
                profile = setup.get("profile", SYSTEM)
                settings = preference(s, profile, "conversation.preferences", {})
                if not self.permitted(setup, {}) or settings.get("enabled") is not True:
                    raise ValueError(
                        "Enable preference conversations in private Amadeus setup first"
                    )
                if not self.context():
                    s.remember(
                        profile,
                        self.state_key,
                        dict(
                            session_until=self.clock() + 600, turns=0, pending=None, last_reply=""
                        ),
                    )
            current = self.context() or {}
            tool_text = text
            if (
                current.get("last_tools") == ["get_calendar_agenda"]
                and re.match(r"\s*(what about|and|how about)\b", text, re.I)
                and re.search(
                    r"\b(tomorrow|today|week|month|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
                    text,
                    re.I,
                )
            ):
                tool_text = "What is on my calendar " + text
            result = None
            if tool_turn:
                result = tool_turn(tool_text.strip(), history=current.get("history", []))
                if result.get("conversation") is True:
                    result = None
            if result is not None:
                reply = result["reply"]
            else:

                def conversation_generate(message, context):
                    return generate(
                        message,
                        {
                            **context,
                            "capabilities": [
                                {"name": name, "description": spec.get("description", "")}
                                for name, spec in (specs or {}).items()
                            ],
                        },
                    )

                reply = self.answer(text.strip(), conversation_generate)
            with self.store() as s:
                state = preference(s, profile, self.state_key, {})
                history = state.get("history", [])
                history = (
                    history
                    + [
                        {"role": "user", "content": text.strip()},
                        {"role": "assistant", "content": reply},
                    ]
                )[-8:]
                while history and len(json.dumps(history).encode()) > 2200:
                    history = history[2:]
                state.update(history=history, last_reply=reply)
                if result is not None:
                    state["last_tools"] = result.get("tools", [])
                if result is not None:
                    state.update(pending=None, memory_status=None)
                while state["history"] and len(json.dumps(state).encode()) > 3800:
                    state["history"] = state["history"][2:]
                s.remember(profile, self.state_key, state)
            with self.store() as s:
                context = preference(s, profile, self.state_key, {})
            return {
                "reply": reply,
                "pending": context.get("pending"),
                "silent": True,
                "memory": context.get("memory_status"),
                "tools": (result or {}).get("tools", []),
                "reply_composition": (result or {}).get("reply_composition"),
            }

    def feedback(self, data):
        if set(data) - {"rating", "note"} or data.get("rating") not in ("useful", "unhelpful"):
            raise ValueError("Choose useful or unhelpful")
        note = data.get("note", "")
        if not isinstance(note, str) or len(note) > 1000:
            raise ValueError("Keep feedback under 1000 characters")
        with self.lock:
            path = self.folder / "text-feedback.json"
            rows = read(path, {}).get("items", [])
            context = self.context() or {}
            rows.append(
                dict(
                    at=self.clock(),
                    rating=data["rating"],
                    note=note,
                    context=context.get("history", [])[-2:],
                )
            )
            write(path, {"items": rows[-100:]})
        return {"saved": True}
