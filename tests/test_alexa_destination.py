"""Isolated session renderer contract; does not invoke Alexa or move hardware."""

import unittest
from okabebot.alexa_destination import document, update

TOKEN = "1" * 64
GENERATION = "a" * 32
FRAMES = ["https://example.com/actor-%s.png" % i for i in range(4)]


class DestinationTests(unittest.TestCase):
    def root(self):
        result = document(TOKEN, "https://example.com/room.png", FRAMES)
        return result["response"]["directives"][0]["document"]["mainTemplate"]["items"][0]

    def test_empty_until_authorized_and_independently_expires(self):
        root = self.root()
        bindings = {item["name"]: item["value"] for item in root["bind"]}
        self.assertEqual(bindings["phase"], "waiting")
        self.assertEqual(bindings["leaseUntil"], 0)
        self.assertEqual(bindings["sequence"], 0)
        actor = root["items"][1]
        guard = root["items"][2]["opacity"]
        self.assertEqual(actor["display"], "${coverReady ? 'normal' : 'invisible'}")
        self.assertIn("clock < leaseUntil", guard)
        self.assertIn("clock < 60000", guard)
        self.assertIn("!closed", guard)
        self.assertEqual(actor["source"], FRAMES[0])
        self.assertEqual((actor["top"], actor["left"]), (0, 0))
        self.assertIn("invisible", actor["display"])
        self.assertNotIn("opacity", actor)
        ticks = root["handleTick"][0]["commands"]
        self.assertEqual(ticks[0]["value"], "${elapsedTime}")
        self.assertTrue(
            any(
                c.get("property") == "closed" and c["when"] == "${elapsedTime >= 60000}"
                for c in ticks
            )
        )
        self.assertFalse(any(c["type"] == "SendEvent" for c in ticks))

    def test_asset_readiness_and_bounded_normal_polling(self):
        root = self.root()
        self.assertEqual(root["items"][0]["onLoad"][0]["property"], "backgroundReady")
        self.assertEqual(root["items"][1]["onLoad"][0]["property"], "actorReady")
        polling = root["onMount"][0]
        self.assertEqual(polling["repeatCount"], 59)
        args = polling["commands"][0]["arguments"]
        self.assertEqual(args[:2], ["destination-poll", TOKEN])
        self.assertIn("${backgroundReady && coverReady && actorReady}", args)
        self.assertEqual(polling["finally"][-1]["value"], 0)
        response = document(TOKEN, "https://example.com/room.png", FRAMES)["response"]
        self.assertNotIn("outputSpeech", response)
        self.assertNotIn("reprompt", response)
        self.assertNotIn("shouldEndSession", response)

    def test_commands_use_receiver_poll_deadline_not_arrival_time(self):
        response = update(TOKEN, "entering", GENERATION, sequence=7, receiver_elapsed_ms=1200)
        directive = response["response"]["directives"][0]
        self.assertEqual(directive["token"], TOKEN)
        command = directive["commands"][0]
        self.assertEqual(command["property"], "incoming")
        self.assertEqual(
            command["value"],
            {
                "sequence": 7,
                "phase": "entering",
                "generation": GENERATION,
                "expiresAt": 5200,
            },
        )
        # All checks run in the root component's binding context, not the
        # document-level ExecuteCommands context where root bindings are absent.
        handler = self.root()["handleTick"][0]["commands"][1]
        self.assertIn("incoming.sequence > sequence", handler["when"])
        self.assertIn("incoming.expiresAt > elapsedTime", handler["when"])
        self.assertIn("!closed", handler["when"])
        self.assertEqual(handler["commands"][0]["value"], "${incoming.sequence}")

    def test_leaving_hides_before_departure_acknowledgement(self):
        handlers = self.root()["handleTick"][0]["commands"]
        applying = handlers[1]["commands"]
        phase = next(c for c in applying if c.get("property") == "phase")
        self.assertIn("incoming.phase == 'leaving' ? 'hidden'", phase["value"])
        # Hiding is applied first; a distinct later tick reports departed.
        departing = next(
            c for c in handlers if c.get("property") == "painted" and c["value"] == "departed"
        )
        self.assertIn("phase == 'hidden'", departing["when"])
        self.assertIn("appliedAt + 100", departing["when"])
        expired = update(TOKEN, "present", GENERATION, sequence=3, receiver_elapsed_ms=59000)
        self.assertEqual(
            expired["response"]["directives"][0]["commands"][0]["value"]["expiresAt"], 60000
        )

    def test_invalid_assets_tokens_and_commands_rejected(self):
        for token in ["", "x" * 64, "1" * 63, None]:
            with self.assertRaises(ValueError):
                document(token, FRAMES[0], FRAMES)
        for url in ["http://example.com/x", "https://user:secret@example.com/x", "file:///x", None]:
            with self.assertRaises(ValueError):
                document(TOKEN, url, FRAMES)
        for changes in [
            {"phase": "run_tool"},
            {"sequence": True},
            {"sequence": 0},
            {"sequence": 1000001},
            {"lease_ms": 6000},
            {"lease_ms": True},
            {"generation": "bad"},
            {"receiver_elapsed_ms": True},
            {"receiver_elapsed_ms": -1},
            {"receiver_elapsed_ms": 60000},
        ]:
            args = dict(
                token=TOKEN,
                phase="present",
                generation=GENERATION,
                sequence=1,
                receiver_elapsed_ms=1000,
            )
            args.update(changes)
            with self.assertRaises(ValueError):
                update(**args)
