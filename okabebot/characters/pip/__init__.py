"""Pip's character implementation and associated assets."""

from ..base import Character


class PipCharacter(Character):
    def shapes(self, **state):
        from .art import shapes

        return shapes(**state)


CHARACTER = PipCharacter(__file__)
