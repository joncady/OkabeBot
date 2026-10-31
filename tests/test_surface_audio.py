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

    def test_acknowledged_events_are_pruned_but_unconsumed_pcm_is_retained(self):
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
        events = self.poll()["events"]
        self.assertEqual(self.poll()["events"], events)
        self.assertEqual(
            [e["kind"] for e in self.poll(after=events[0]["cursor"])["events"]], ["chunk"]
        )
        self.assertEqual(self.poll(after=events[-1]["cursor"])["events"], [])
        self.assertEqual(self.hub.streams[identifier]["events"], [])

    def test_stream_ttl_releases_transient_pcm_without_replay(self):
        self.poll()
        identifier = self.hub.command(self.device, {"op": "stream_start"})["stream_id"]
        self.hub.streams[identifier]["created"] -= 91
        self.assertEqual(self.poll()["events"], [])
        self.assertNotIn(identifier, self.hub.streams)
        with self.assertRaisesRegex(ValueError, "expired|Unknown"):
            self.hub.command(self.device, {"op": "stream_end", "stream_id": identifier})

    def test_queue_backpressure_waits_for_acknowledgment_without_dropping_pcm(self):
        self.poll()
        identifier = self.hub.command(self.device, {"op": "stream_start"})["stream_id"]
        self.hub.command(
            self.device,
            {
                "op": "stream_chunk",
                "stream_id": identifier,
                "sequence": 0,
                "pcm_base64": base64.b64encode(b"\0" * 240000).decode(),
            },
        )
        consumed = threading.Event()

        def next_packet():
            self.hub.command(
                self.device,
                {
                    "op": "stream_chunk",
                    "stream_id": identifier,
                    "sequence": 1,
                    "pcm_base64": base64.b64encode(b"\0" * 4800).decode(),
                },
            )
            consumed.set()

        worker = threading.Thread(target=next_packet)
        worker.start()
        self.assertFalse(consumed.wait(0.05))
        events = self.poll()["events"]
        self.assertEqual([e["kind"] for e in events], ["start", "chunk"])
        self.poll(after=events[-1]["cursor"])
        self.assertTrue(consumed.wait(1))
        worker.join(1)
        self.assertEqual(self.hub.streams[identifier]["sequence"], 2)

    def test_default_start_preserves_tv_prebuffer_until_explicitly_overridden(self):
        self.poll()
        self.hub.command(self.device, {"op": "stream_start"})
        default = self.poll()["events"][0]
        self.assertNotIn("startup_buffer_ms", default)
        self.assertEqual(default["sample_rate"], 24000)
        self.hub.command(self.device, {"op": "stream_start", "startup_buffer_ms": 300})
        starts = [e for e in self.poll()["events"] if e["kind"] == "start"]
        self.assertEqual(starts[-1]["startup_buffer_ms"], 300)

    def test_waiting_chunk_cannot_continue_after_receiver_session_replacement(self):
        self.poll()
        identifier = self.hub.command(self.device, {"op": "stream_start"})["stream_id"]
        self.hub.command(
            self.device,
            {
                "op": "stream_chunk",
                "stream_id": identifier,
                "sequence": 0,
                "pcm_base64": base64.b64encode(b"\0" * 240000).decode(),
            },
        )
        done = threading.Event()
        errors = []

        def append():
            try:
                self.hub.command(
                    self.device,
                    {
                        "op": "stream_chunk",
                        "stream_id": identifier,
                        "sequence": 1,
                        "pcm_base64": base64.b64encode(b"\0" * 4800).decode(),
                    },
                )
            except ValueError as exc:
                errors.append(str(exc))
            finally:
                done.set()

        worker = threading.Thread(target=append)
        worker.start()
        self.assertFalse(done.wait(0.05))
        self.session = "d" * 32
        self.poll()
        self.assertTrue(done.wait(1))
        worker.join(1)
        self.assertTrue(errors)
        self.assertEqual(self.hub.streams[identifier]["sequence"], 1)
        with self.assertRaises(ValueError):
            self.hub.command(self.device, {"op": "stream_end", "stream_id": identifier})

    def test_waiting_chunk_cannot_emit_after_stream_expiry_and_removal(self):
        self.poll()
        identifier = self.hub.command(self.device, {"op": "stream_start"})["stream_id"]
        self.hub.command(
            self.device,
            {
                "op": "stream_chunk",
                "stream_id": identifier,
                "sequence": 0,
                "pcm_base64": base64.b64encode(b"\0" * 240000).decode(),
            },
        )
        stream = self.hub.streams[identifier]
        done = threading.Event()
        errors = []

        def append():
            try:
                self.hub.command(
                    self.device,
                    {
                        "op": "stream_chunk",
                        "stream_id": identifier,
                        "sequence": 1,
                        "pcm_base64": base64.b64encode(b"\0" * 4800).decode(),
                    },
                )
            except ValueError as exc:
                errors.append(str(exc))
            finally:
                done.set()

        worker = threading.Thread(target=append)
        worker.start()
        self.assertFalse(done.wait(0.05))
        stream["created"] -= 91
        self.poll()
        self.assertTrue(done.wait(1))
        worker.join(1)
        self.assertTrue(errors)
        self.assertEqual(stream["sequence"], 1)
        self.assertNotIn(identifier, self.hub.streams)
