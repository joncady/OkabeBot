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

    def test_short_first_packet_does_not_wait_for_next_generation_segment(self):
        release = threading.Event()
        stopped = threading.Event()

        def source():
            try:
                yield b"ab" * 4
                release.wait(2)
                yield b"cd" * 12
            finally:
                stopped.set()

        stream = buffered_chunks(source(), 16, first_chunk_bytes=4)
        try:
            self.assertEqual(next(stream), b"abab")
            self.assertFalse(release.is_set())
            release.set()
            self.assertEqual(b"abab" + b"cd" * 12, b"".join(stream))
            self.assertTrue(stopped.wait(1))
        finally:
            release.set()
            stream.close()

    def test_first_packet_policy_preserves_bytes_and_rejects_invalid_sizes(self):
        pcm = b"ab" * 40
        packets = list(buffered_chunks(iter([pcm]), 32, first_chunk_bytes=8))
        self.assertEqual([8, 32, 32, 8], [len(p) for p in packets])
        self.assertEqual(pcm, b"".join(packets))
        for size in (0, 1, 3, 34, True):
            with self.subTest(size=size), self.assertRaises(ValueError):
                list(buffered_chunks(iter([pcm]), 32, first_chunk_bytes=size))
