import json
import struct
import unittest
from unittest.mock import MagicMock, patch

from okabebot import speech


class LocalSpeechTests(unittest.TestCase):
    def consume(self, wire):
        peer = MagicMock()
        data = bytearray(wire)

        def receive(length):
            # Exercise partial reads, including partial frame headers.
            size = min(3, length, len(data))
            result = bytes(data[:size])
            del data[:size]
            return result

        peer.recv.side_effect = receive
        context = MagicMock()
        context.__enter__.return_value = peer
        with (
            patch.object(speech.socket, "socket", return_value=context),
            patch.object(
                speech, "get_config", return_value={"speech": {"local_socket": "/tmp/test.sock"}}
            ),
            patch("okabebot.profiles.current_character", return_value={"style": "kurisu"}),
        ):
            chunks = list(speech.local_pcm_chunks("Hello", "neutral", "warm"))
        request = json.loads(peer.sendall.call_args.args[0])
        self.assertEqual(request["character"], "kurisu")
        return chunks

    def test_fragmented_pcm_stream(self):
        self.assertEqual(self.consume(struct.pack("!I", 4) + b"1234" + b"\0" * 4), [b"1234"])

    def test_truncation_and_invalid_frame_abort(self):
        for wire in (struct.pack("!I", 4) + b"12", struct.pack("!I", 3), struct.pack("!I", 48002)):
            with self.subTest(wire=wire), self.assertRaises(RuntimeError):
                self.consume(wire)


if __name__ == "__main__":
    unittest.main()
