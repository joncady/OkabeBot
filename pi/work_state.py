"""Leased, content-free work intent. Python 3.7; no wall-clock synchronization."""

import math
import time

STAGES = ("researching", "comparing", "drafting", "awaiting_review", "blocked")


class WorkState:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.until = 0
        self.value = {}
        self.motion = {"enabled": True, "reduced_motion": False}

    def update(self, data):
        work = data.get("work", {})
        motion = data.get("motion", {})
        if (
            not isinstance(motion, dict)
            or set(motion) != {"enabled", "reduced_motion"}
            or any(type(v) is not bool for v in motion.values())
        ):
            raise ValueError("Invalid motion settings")
        if not isinstance(work, dict) or set(work) - {
            "kind",
            "stage",
            "elapsed_seconds",
            "lease_seconds",
        }:
            raise ValueError("Use content-free work intent")
        if work:
            if work.get("stage") not in STAGES or work.get("kind") not in (
                "shopping_list",
                "general",
            ):
                raise ValueError("Unknown work intent")
            for key, low, high in (("elapsed_seconds", 0, 86400), ("lease_seconds", 1, 15)):
                value = work.get(key)
                if (
                    type(value) not in (int, float)
                    or not math.isfinite(value)
                    or not low <= value <= high
                ):
                    raise ValueError("Invalid work timing")
        self.value, self.motion = dict(work), dict(motion)
        self.until = self.clock() + work.get("lease_seconds", 0)
        self.received = self.clock()

    def snapshot(self):
        value = dict(self.value) if self.clock() < self.until else {}
        if value:
            value["elapsed_seconds"] += max(0, self.clock() - self.received)
        return value, dict(self.motion)
