"""Kurisu's character implementation and associated assets."""

from ..base import Character


class KurisuCharacter(Character):
    def shapes(self, **state):
        from .art import shapes

        return shapes(**state)


CHARACTER = KurisuCharacter(__file__)
