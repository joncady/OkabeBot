"""Owner-only silent chat sharing preference policy, isolated from spoken sessions."""

import json
import re

from .amadeus_live import ProactiveConversation, confirmation_answer, is_stop
from .amadeus_habits import preference
from .amadeus_onboarding import SYSTEM, KEY
from .presence_control import read, write
from .conversation_state import normalize_state, update_task_state


class TextConversation(ProactiveConversation):
    def __init__(self, folder, state_key="conversation.text", **kwargs):
        super().__init__(folder, state_key=state_key, **kwargs)
        self.turn_limit = 30

    @staticmethod
    def permitted(setup, cfg):
        return (
            bool(setup.get("profile"))
            and setup.get("paused") is False
            and setup.get("guest") is False
        )

    def send(self, text, generate, tool_turn=None, specs=None, *, resume_only=False):
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
                    if resume_only:
                        return {"reply": None, "closed": True, "tools": []}
                    s.remember(
                        profile,
                        self.state_key,
                        dict(
                            session_until=self.clock() + 600, turns=0, pending=None, last_reply=""
                        ),
                    )
            current = self.context() or {}
            task_state = normalize_state(current.get("task_state"))
            tool_text = text
            if (
                task_state.get("kind") != "read"
                and current.get("last_tools") == ["get_calendar_agenda"]
                and re.match(r"\s*(what about|and|how about)\b", text, re.I)
                and re.search(
                    r"\b(tomorrow|today|week|month|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
                    text,
                    re.I,
                )
            ):
                tool_text = "What is on my calendar " + text
            result = None
            control_reply = is_stop(text) or (
                current.get("pending") and confirmation_answer(text) is not None
            )
            if tool_turn and not control_reply:
                try:
                    result = tool_turn(
                        tool_text.strip(), history=current.get("history", []), task_state=task_state
                    )
                except Exception:
                    # A failed turn must not leave old query slots active behind an action.
                    with self.store() as store, store.db:
                        store.db.execute("BEGIN IMMEDIATE")
                        latest_setup = preference(store, SYSTEM, KEY, {})
                        state = preference(store, profile, self.state_key, {})
                        if (
                            latest_setup.get("profile") == profile
                            and state
                            and state.get("session_until") == current.get("session_until")
                            and state.get("claimed_at") == current.get("claimed_at")
                        ):
                            state.pop("task_state", None)
                            store.remember(profile, self.state_key, state)
                    raise
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
                            "task_state": task_state,
                            "capabilities": [
                                {"name": name, "description": spec.get("description", "")}
                                for name, spec in (specs or {}).items()
                            ],
                        },
                    )

                reply = self.answer(text.strip(), conversation_generate)
            if reply is None:
                return {"reply": None, "closed": True, "tools": []}
            with self.store() as s:
                state = preference(s, profile, self.state_key, {})
                history = state.get("history", [])
                pair = [
                    {"role": "user", "content": text.strip()},
                    {"role": "assistant", "content": reply},
                ]
                # Proactive.answer now retains its own history; tool replies still need it here.
                if history[-2:] != pair:
                    history += pair
                history = history[-8:]
                while history and len(json.dumps(history).encode()) > 2200:
                    history = history[2:]
                state.update(history=history, last_reply=reply)
                state["task_state"] = update_task_state(
                    task_state, user_text=text, calls=(result or {}).get("calls", []), reply=reply
                )
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

    def record_treatment(self, receipt):
        with self.lock, self.store() as store:
            setup = preference(store, SYSTEM, KEY, {})
            profile = setup.get("profile")
            if profile:
                state = preference(store, profile, self.state_key, {})
                if state.get("session_until", 0) > self.clock():
                    state["prompt_treatment"] = receipt
                    store.remember(profile, self.state_key, state)

    def feedback(self, data):
        if set(data) - {"rating", "note"} or data.get("rating") not in ("useful", "unhelpful"):
            raise ValueError("Choose useful or unhelpful")
        note = data.get("note", "")
        if not isinstance(note, str) or len(note) > 1000:
            raise ValueError("Keep feedback under 1000 characters")
        with self.lock, self.store() as s, s.db:
            s.db.execute("BEGIN IMMEDIATE")
            setup = preference(s, SYSTEM, KEY, {})
            if not setup.get("profile"):
                raise ValueError("Save private setup before leaving feedback")
            context = preference(s, setup["profile"], self.state_key, {})
            path = self.folder / "text-feedback.json"
            rows = read(path, {}).get("items", [])
            rows.append(
                dict(
                    at=self.clock(),
                    rating=data["rating"],
                    note=note,
                    treatment=context.get("prompt_treatment"),
                    context=context.get("history", [])[-2:]
                    if context.get("session_until", 0) > self.clock()
                    else [],
                )
            )
            # Serialize this sidecar write with whole-store forgetting through SQLite.
            write(path, {"items": rows[-100:]})
        return {"saved": True}
