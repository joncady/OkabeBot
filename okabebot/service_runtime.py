"""Small lifecycle helpers for opt-in local adapters."""

import contextlib
import signal
import threading


@contextlib.contextmanager
def stopping():
    """Let SIGTERM run cleanup and interrupt waits, rather than orphaning children."""
    event = threading.Event()
    previous = {}
    if threading.current_thread() is threading.main_thread():
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous[signum] = signal.signal(signum, lambda *_: event.set())
    try:
        yield event
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def stop_process(process):
    """Bounded child cleanup, including stuck SSH clients."""
    import subprocess

    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
