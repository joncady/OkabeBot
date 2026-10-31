"""Okabe's character implementation and associated assets."""

from ..base import Character


class OkabeCharacter(Character):
    def shapes(self, **state):
        from .art import shapes

        return shapes(**state)


CHARACTER = OkabeCharacter(__file__)
