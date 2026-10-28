import base64
import threading
import unittest
from okabebot.surface_audio import AudioHub


class AudioTests(unittest.TestCase):
    def setUp(self):
        self.hub = AudioHub()
        self.device = "screen-phone"
        self.session = "a" * 32

    def poll(self, after=0, **extra):
        return self.hub.poll(
            self.device, dict(session=self.session, after=after, enabled=True, **extra)
        )

    def test_disabled_receiver_cannot_start_or_receive_replayed_audio(self):
        with self.assertRaises(ValueError):
            self.hub.command(self.device, {"op": "stream_start"})
        self.poll()
        identifier = self.hub.command(self.device, {"op": "stream_start"})["stream_id"]
        self.hub.command(
            self.device,
            {
                "op": "stream_chunk",
                "stream_id": identifier,
                "sequence": 0,
                "pcm_base64": base64.b64encode(b"\0" * 4800).decode(),
            },
        )
        self.session = "b" * 32
        self.assertEqual(self.poll()["events"], [])
        with self.assertRaises(ValueError):
            self.hub.command(self.device, {"op": "stream_end", "stream_id": identifier})

    def test_order_boundaries_and_acknowledged_completion(self):
        self.poll()
        identifier = self.hub.command(self.device, {"op": "stream_start"})["stream_id"]
        command = {
            "op": "stream_chunk",
            "stream_id": identifier,
            "sequence": 0,
            "pcm_base64": base64.b64encode(b"\0" * 4800).decode(),
        }
        self.hub.command(self.device, command)
        with self.assertRaises(ValueError):
            self.hub.command(self.device, command)
        result = []
        worker = threading.Thread(
            target=lambda: result.append(
                self.hub.command(self.device, {"op": "stream_end", "stream_id": identifier})
            )
        )
        worker.start()
        with self.hub.condition:
            self.hub.condition.wait_for(lambda: self.hub.streams[identifier]["ended"], timeout=1)
        events = self.poll()["events"]
        self.assertEqual([e["kind"] for e in events], ["start", "chunk", "end"])
        self.poll(after=events[-1]["cursor"], finished=identifier)
        worker.join(2)
        self.assertEqual(result, [{"played": True}])
        self.assertEqual(
            self.hub.poll("other", dict(session="c" * 32, after=0, enabled=True))["events"], []
        )

    def test_bad_pcm_does_not_enter_relay(self):
        self.poll()
        identifier = self.hub.command(self.device, {"op": "stream_start"})["stream_id"]
        for pcm in (
            "invalid!",
            base64.b64encode(b"x").decode(),
            base64.b64encode(b"x" * 240002).decode(),
        ):
            with self.assertRaises(ValueError):
                self.hub.command(
                    self.device,
                    {
                        "op": "stream_chunk",
                        "stream_id": identifier,
                        "sequence": 0,
                        "pcm_base64": pcm,
                    },
                )

    def test_sleep_or_wifi_gap_expires_old_audio_even_with_same_session(self):
        self.poll()
        identifier = self.hub.command(self.device, {"op": "stream_start"})["stream_id"]
        self.hub.command(
            self.device,
            {
                "op": "stream_chunk",
                "stream_id": identifier,
                "sequence": 0,
                "pcm_base64": base64.b64encode(b"\0" * 4800).decode(),
            },
        )
        self.hub.receivers[self.device]["seen"] -= 5
        self.assertEqual([e["kind"] for e in self.poll()["events"]], ["abort"])
        with self.assertRaisesRegex(ValueError, "disconnected"):
            self.hub.command(self.device, {"op": "stream_end", "stream_id": identifier})
        fresh = self.hub.command(self.device, {"op": "stream_start"})["stream_id"]
        self.assertNotEqual(identifier, fresh)
        self.assertEqual([e["kind"] for e in self.poll()["events"]], ["start"])
