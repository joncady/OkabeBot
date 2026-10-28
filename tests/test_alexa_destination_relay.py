"""No AWS/hardware: real relay plus APL renderer over an isolated durable store."""

import copy
import unittest
from okabebot.alexa_destination_relay import DestinationRelay
from okabebot.alexa_skill import fixture

TOKEN = "1" * 64
GEN = "a" * 32


class Store:
    def __init__(self):
        self.values = {}
        self.versions = {}
        self.before_compare = None

    def get(self, key):
        return copy.deepcopy(self.values.get(key))

    def read(self, key):
        return self.get(key), self.versions.get(key)

    def compare_put(self, key, value, version):
        hook, self.before_compare = self.before_compare, None
        if hook:
            hook()
        if self.versions.get(key) != version:
            return False
        self.put(key, value)
        return True

    def put(self, key, value):
        self.versions[key] = self.versions.get(key, 0) + 1
        self.values[key] = copy.deepcopy(value)


class RelayTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.now = 1000
        self.relay = DestinationRelay(
            self.store,
            lambda: {
                "background": "https://example.com/background.png",
                "frames": ["https://example.com/%s.png" % n for n in range(4)],
                "character": "okabe",
                "set": "maid-cafe",
            },
            clock=lambda: self.now,
            nonce=lambda: TOKEN,
        )
        self.event = fixture()
        self.event["session"] = {"sessionId": "session-one"}
        self.event["context"]["System"]["device"] = {
            "deviceId": "device-one",
            "supportedInterfaces": {"Alexa.Presentation.APL": {}},
        }
        self.relay.launch(self.event)

    def poll(self, elapsed=1000, painted="hidden", generation=""):
        event = copy.deepcopy(self.event)
        event["request"].update(
            type="Alexa.Presentation.APL.UserEvent",
            token=TOKEN,
            arguments=["destination-poll", TOKEN, generation, painted, True, elapsed],
        )
        return event

    def test_explicit_exit_from_a_new_voice_session_requires_current_screen_token(self):
        event = copy.deepcopy(self.event)
        event["session"]["sessionId"] = "new-voice-session"
        event["context"]["Alexa.Presentation.APL"] = {"token": "2" * 64}
        self.relay.closed(event, explicit=True)
        self.assertFalse(self.store.get("session")["closed"])
        event["context"]["Alexa.Presentation.APL"]["token"] = TOKEN
        self.relay.closed(event)  # A stale SessionEnded cannot use the screen token.
        self.assertFalse(self.store.get("session")["closed"])
        self.relay.closed(event, explicit=True)
        self.assertTrue(self.store.get("session")["closed"])

    def test_speech_decorates_only_the_current_visible_matching_actor(self):
        record = self.store.get("session")
        record.update(ready=True, painted="entered", clock=1000)
        self.store.put("session", record)
        self.event["context"]["Alexa.Presentation.APL"] = {"token": TOKEN}
        directive = self.relay.speech(self.event, "okabe", 2300)
        self.assertEqual(directive["token"], TOKEN)
        self.assertEqual(directive["commands"][0]["value"], 4050)
        self.now += 2.5
        self.assertEqual(self.relay.speech(self.event, "okabe", 2300)["commands"][0]["value"], 6550)
        self.now -= 2.5
        for changes in (
            {"ready": False},
            {"painted": "hidden"},
            {"closed": True},
            {"character": "kurisu"},
            {"updated_at": self.now - 4},
            {"expires_at": self.now},
        ):
            with self.subTest(changes=changes):
                self.store.put("session", dict(record, **changes))
                self.assertIsNone(self.relay.speech(self.event, "okabe", 2300))
        self.store.put("session", record)
        self.event["context"]["Alexa.Presentation.APL"]["token"] = "2" * 64
        self.assertIsNone(self.relay.speech(self.event, "okabe", 2300))
        self.event["context"]["Alexa.Presentation.APL"]["token"] = TOKEN
        self.assertIsNone(self.relay.speech(self.event, "okabe", 20001))
        self.assertEqual(self.store.get("session"), record)

    def test_asset_diagnostic_is_bounded_and_does_not_imply_readiness(self):
        event = self.poll()
        event["request"]["arguments"][4] = False
        event["request"]["arguments"].append(9)
        self.relay.poll(event)
        record = self.store.get("session")
        self.assertEqual(record["asset_status"], 9)
        self.assertFalse(record["ready"])
        for invalid in (True, 16, -1, "signed-url"):
            event["request"]["arguments"][-1] = invalid
            with self.assertRaises(ValueError):
                self.relay.poll(event)

    def command(self):
        self.store.put(
            "command",
            dict(
                token=TOKEN,
                phase="entering",
                generation=GEN,
                sequence=1,
                receiver_elapsed_ms=1000,
                updated_at=self.now,
            ),
        )

    def test_ready_does_not_imply_arrival_and_private_identity_is_hashed(self):
        self.relay.poll(self.poll())
        state = self.store.get("session")
        self.assertTrue(state["ready"])
        self.assertEqual(state["painted"], "hidden")
        self.assertNotIn("device-one", str(state))
        self.assertNotIn("session-one", str(state))
        self.assertIsNone(self.store.get("command"))

    def test_command_is_scoped_and_only_unspent_grant_is_translated_to_poll_clock(self):
        self.command()
        self.now += 1
        result = self.relay.poll(self.poll(elapsed=2200))
        mailbox = result["response"]["directives"][0]["commands"][0]["value"]
        self.assertEqual(mailbox["expiresAt"], 5200)
        self.assertNotIn("outputSpeech", result["response"])
        self.now += 4
        self.assertEqual(self.relay.poll(self.poll(elapsed=6000))["response"], {})

    def test_repeated_command_does_not_refresh_its_wall_clock_grant(self):
        self.command()
        self.now += 2
        first = self.relay.poll(self.poll(elapsed=3500))
        expiry = first["response"]["directives"][0]["commands"][0]["value"]["expiresAt"]
        self.assertEqual(expiry, 5500)
        self.now += 0.5
        second = self.relay.poll(self.poll(elapsed=4000))
        self.assertEqual(
            second["response"]["directives"][0]["commands"][0]["value"]["expiresAt"], expiry
        )
        self.now += 0.6
        self.assertEqual(self.relay.poll(self.poll(elapsed=4600))["response"], {})

    def test_reordered_polls_and_previous_sessions_cannot_replay_arrival(self):
        self.relay.poll(self.poll(3000, "entered", GEN))
        self.relay.poll(self.poll(2000, "hidden"))
        self.assertEqual(self.store.get("session")["painted"], "entered")
        other = self.poll()
        other["context"]["System"]["device"]["deviceId"] = "other"
        with self.assertRaises(PermissionError):
            self.relay.poll(other)
        old = self.poll()
        old["request"]["token"] = "2" * 64
        with self.assertRaises(PermissionError):
            self.relay.poll(old)
        self.now = 1061
        self.assertEqual(self.relay.poll(self.poll())["response"], {})

    def test_old_session_end_cannot_close_new_skill_session(self):
        old = copy.deepcopy(self.event)
        old["session"]["sessionId"] = "old-session"
        self.relay.closed(old)
        self.assertFalse(self.store.get("session")["closed"])
        self.relay.closed(self.event)
        self.assertTrue(self.store.get("session")["closed"])
        self.assertEqual(self.relay.poll(self.poll())["response"], {})

    def test_invalid_poll_state_rejected_before_persistence(self):
        baseline = self.store.get("session")
        for index, value in [
            (3, "invoke_tool"),
            (4, "true"),
            (5, float("nan")),
            (5, True),
            (5, 60000),
        ]:
            event = self.poll()
            event["request"]["arguments"][index] = value
            with self.assertRaises(ValueError):
                self.relay.poll(event)
        self.assertEqual(self.store.get("session"), baseline)

    def test_concurrent_newer_poll_wins_over_older_acknowledgement(self):
        self.store.before_compare = lambda: self.relay.poll(self.poll(2000, "entered", GEN))
        self.relay.poll(self.poll(1000, "hidden"))
        self.assertEqual(self.store.get("session")["clock"], 2000)
        self.assertEqual(self.store.get("session")["painted"], "entered")

    def test_concurrent_close_cannot_be_undone_by_inflight_poll(self):
        self.store.before_compare = lambda: self.relay.closed(self.event)
        self.assertEqual(self.relay.poll(self.poll())["response"], {})
        self.assertTrue(self.store.get("session")["closed"])
        self.assertFalse(self.store.get("session")["ready"])

    def test_concurrent_new_launch_cannot_be_overwritten_by_old_poll(self):
        self.now += 1
        self.relay.nonce = lambda: "2" * 64
        self.store.before_compare = lambda: self.relay.launch(self.event)
        with self.assertRaises(PermissionError):
            self.relay.poll(self.poll())
        self.assertEqual(self.store.get("session")["token"], "2" * 64)


class StoreTests(unittest.TestCase):
    def test_private_store_bounds_keys_payload_and_closes_streams(self):
        import io
        from unittest.mock import Mock
        from okabebot.alexa_destination_relay import PrivateDestinationStore

        client = Mock()
        store = PrivateDestinationStore(client, "private-bucket")
        stream = io.BytesIO(b'{"ready":true}')
        client.get_object.return_value = {"Body": stream, "ETag": "version-one"}
        self.assertEqual(store.get("session"), {"ready": True})
        self.assertTrue(stream.closed)
        client.get_object.assert_called_once_with(
            Bucket="private-bucket", Key="surface/session.json"
        )
        for payload in [b"x" * 16385, b"[]"]:
            stream = io.BytesIO(payload)
            client.get_object.return_value = {"Body": stream, "ETag": "version-one"}
            with self.assertRaises(ValueError):
                store.get("session")
            self.assertTrue(stream.closed)
        with self.assertRaises(KeyError):
            store.get("../../other-object")
        with self.assertRaises(ValueError):
            store.put("command", {"value": float("nan")})
        client.put_object.assert_not_called()
        store.put("command", {"phase": "hidden"})
        kwargs = client.put_object.call_args.kwargs
        self.assertEqual(kwargs["Key"], "surface/command.json")
        self.assertEqual(kwargs["ServerSideEncryption"], "AES256")
        self.assertEqual(kwargs["CacheControl"], "no-store")

    def test_store_uses_conditional_writes_and_retries_only_version_conflicts(self):
        from unittest.mock import Mock
        from okabebot.alexa_destination_relay import PrivateDestinationStore

        client = Mock()
        store = PrivateDestinationStore(client, "private-bucket")
        self.assertTrue(store.compare_put("session", {"clock": 1}, None))
        self.assertEqual(client.put_object.call_args.kwargs["IfNoneMatch"], "*")
        self.assertTrue(store.compare_put("session", {"clock": 2}, "etag-one"))
        self.assertEqual(client.put_object.call_args.kwargs["IfMatch"], "etag-one")
        for code in ("PreconditionFailed", "ConditionalRequestConflict"):
            error = RuntimeError("version changed")
            error.response = {"Error": {"Code": code}}
            client.put_object.side_effect = error
            self.assertFalse(store.compare_put("session", {"clock": 3}, "old-etag"))
        denied = RuntimeError("denied")
        denied.response = {"Error": {"Code": "AccessDenied"}}
        client.put_object.side_effect = denied
        with self.assertRaises(RuntimeError):
            store.compare_put("session", {"clock": 3}, "old-etag")
