import unittest
from pi.prepared_audio import PreparedAudio


class PreparedTests(unittest.TestCase):
    def test_expiry_replacement_and_single_use(self):
        now = [0]
        audio = PreparedAudio(lambda raw: len(raw), lambda: now[0])
        old = audio.prepare(b"first")["prepared_id"]
        new = audio.prepare(b"second")["prepared_id"]
        with self.assertRaises(ValueError):
            audio.take(old)
        self.assertEqual(audio.take(new), b"second")
        with self.assertRaises(ValueError):
            audio.take(new)
        token = audio.prepare(b"last")["prepared_id"]
        now[0] = 61
        with self.assertRaises(ValueError):
            audio.take(token)
