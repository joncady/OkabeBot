"""Bounded producer/consumer buffering; never retry or replay speech."""

import queue
import threading
import time


def buffered_chunks(source, prebuffer_bytes=48000, metrics=None):
    """Generate ahead and combine PCM into one-second hardware packets."""
    if type(prebuffer_bytes) is not int or not 1 <= prebuffer_bytes <= 48000:
        raise ValueError("PCM packet size must be 1..48000 bytes")
    items = queue.Queue(maxsize=16)
    stopped = threading.Event()
    metrics = metrics if metrics is not None else {}

    def send(item):
        while not stopped.is_set():
            try:
                items.put(item, timeout=0.1)
                return
            except queue.Full:
                pass

    def produce():
        previous = time.monotonic()
        try:
            for chunk in source:
                now = time.monotonic()
                metrics["source_max_gap_s"] = round(
                    max(metrics.get("source_max_gap_s", 0), now - previous), 3
                )
                previous = now
                if stopped.is_set():
                    break
                send((chunk, None))
        except Exception as exc:
            send((None, exc))
        finally:
            close = getattr(source, "close", None)
            if close:
                close()
            send((None, None))

    worker = threading.Thread(target=produce, daemon=True, name="speech-buffer")
    worker.start()
    pending = bytearray()
    try:
        while True:
            chunk, error = items.get()
            if error:
                raise error
            if chunk is None:
                if pending:
                    yield bytes(pending)
                return
            pending.extend(chunk)
            while len(pending) >= prebuffer_bytes:
                yield bytes(pending[:prebuffer_bytes])
                del pending[:prebuffer_bytes]
    finally:
        stopped.set()
