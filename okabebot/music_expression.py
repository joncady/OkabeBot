"""Experimental room-audio activity labels, not song mood or genre recognition."""

EXPRESSIONS = {"unknown": "neutral", "calm": "neutral", "lively": "happy", "energetic": "excited"}


class MusicExpression:
    def __init__(self):
        self.reset()

    def reset(self):
        self.score = 0.0
        self.elapsed = 0.0
        self.candidate = "unknown"
        self.held = 0.0
        self.label = "unknown"

    def update(self, level, active, dt=0.2):
        if not active:
            self.reset()
            return self.snapshot()
        dt = max(0, min(1, dt))
        self.elapsed += dt
        self.score += (max(0, min(1, level)) - self.score) * (1 - __import__("math").exp(-dt / 4))
        candidate = "energetic" if self.score > 0.55 else "lively" if self.score > 0.18 else "calm"
        if candidate != self.candidate:
            self.candidate, self.held = candidate, 0.0
        self.held += dt
        if self.elapsed >= 6 and self.held >= 3:
            self.label = candidate
        return self.snapshot()

    def snapshot(self):
        return {
            "characteristic": self.label,
            "expression": EXPRESSIONS[self.label],
            "source": "local_audio_energy",
            "score": round(self.score, 3),
        }
