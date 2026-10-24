"""AIY legacy or standard GPIO buttons behind the same tiny interface."""

from types import SimpleNamespace


class Led:
    ON, OFF = "on", "off"

    def __init__(self, output=None):
        self.output = output
        self._state = self.OFF

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, value):
        self._state = value
        if self.output:
            self.output.on() if value == self.ON else self.output.off()


def board(config):
    backend = config["button_backend"]
    if backend == "aiy":
        from aiy.board import Board

        return Board()
    if backend == "gpiozero":
        from gpiozero import Button, LED

        return SimpleNamespace(
            button=Button(config["button_pin"], pull_up=True, bounce_time=0.08),
            led=Led(LED(config["led_pin"])),
        )
    if backend == "none":
        return SimpleNamespace(
            button=SimpleNamespace(when_pressed=None, when_released=None), led=Led()
        )
    raise ValueError("button_backend must be aiy, gpiozero, or none")
