"""Sonic's character implementation and associated assets."""

from ..base import Character


class SonicCharacter(Character):
    def shapes(self, **state):
        from .art import shapes

        return shapes(**state)


CHARACTER = SonicCharacter(__file__)
