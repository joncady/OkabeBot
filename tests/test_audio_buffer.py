import threading
import unittest
from okabebot.audio_buffer import buffered_chunks


class AudioBufferTests(unittest.TestCase):
    def test_short_speech_flushes_at_eof_without_padding_or_replay(self):
        self.assertEqual([b"abcd"], list(buffered_chunks(iter([b"ab", b"cd"]), 100)))

    def test_producer_can_generate_ahead_of_hardware(self):
        produced = threading.Event()

        def source():
            yield b"ab"
            yield b"cd"
            produced.set()
            yield b"ef"

        stream = buffered_chunks(source(), 2)
        self.assertEqual(b"ab", next(stream))
        self.assertTrue(produced.wait(1))
        self.assertEqual([b"cd", b"ef"], list(stream))

    def test_incomplete_provider_stream_is_not_replayed(self):
        def source():
            yield b"ab"
            raise RuntimeError("provider disconnected")

        stream = buffered_chunks(source(), 2)
        self.assertEqual(b"ab", next(stream))
        with self.assertRaisesRegex(RuntimeError, "disconnected"):
            next(stream)

    def test_cancel_releases_a_blocked_producer(self):
        closed = threading.Event()

        def source():
            try:
                while True:
                    yield b"ab"
            finally:
                closed.set()

        stream = buffered_chunks(source(), 2)
        next(stream)
        stream.close()
        self.assertTrue(closed.wait(1))

    def test_packets_preserve_pcm_and_stay_within_device_limit(self):
        pcm = b"ab" * 50000
        packets = list(buffered_chunks(iter([pcm[:48000], pcm[48000:96000], pcm[96000:]])))
        self.assertEqual(pcm, b"".join(packets))
        self.assertTrue(all(len(p) <= 48000 for p in packets))
        self.assertEqual(48000, len(packets[0]))
