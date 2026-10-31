"""Bounded producer/consumer buffering; never retry or replay speech."""

import queue
import threading
import time


def buffered_chunks(source, prebuffer_bytes=48000, metrics=None, *, first_chunk_bytes=None):
    """Generate ahead with a short optional first packet and bounded later packets."""
    if type(prebuffer_bytes) is not int or not 1 <= prebuffer_bytes <= 48000:
        raise ValueError("PCM packet size must be 1..48000 bytes")
    if first_chunk_bytes is not None and (
        type(first_chunk_bytes) is not int
        or not 2 <= first_chunk_bytes <= prebuffer_bytes
        or first_chunk_bytes % 2
    ):
        raise ValueError("First PCM packet must be aligned and within the normal packet size")
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
    packet_size = first_chunk_bytes or prebuffer_bytes
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
            while len(pending) >= packet_size:
                packet = bytes(pending[:packet_size])
                del pending[:packet_size]
                packet_size = prebuffer_bytes
                yield packet
    finally:
        stopped.set()
