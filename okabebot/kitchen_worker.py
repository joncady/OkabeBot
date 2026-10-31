"""Daily local-time index with restart catch-up; async shopping is isolated from speech."""

from .kitchen_browser import Browser
from .kitchen_shopping import Shopping


def poll(bridge):
    kitchen = bridge.kitchen
    while not bridge.closing.is_set():
        try:
            kitchen.index()
            browser = Browser(kitchen.folder)
            if browser.configure()["enabled"]:
                # Optional dependency, private browser profile, independent of foreground turns.
                Shopping(kitchen.folder).run(browser)
        except Exception:
            pass  # State remains private; durable jobs expose blockers/uncertain outcomes.
        bridge.closing.wait(60)
