"""Kitchen HTTP, proactive attention, NFC and privacy integration with invented data."""

import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from okabebot.kitchen_http import handle
from okabebot.kitchen_planning import Planner
from okabebot.tags import Tags
from tests import test_kitchen as kitchen_fixtures
from tests import test_amadeus_live as fixtures


class KitchenHTTPTests(unittest.TestCase):
    setUp = kitchen_fixtures.KitchenTests.setUp
    configure = kitchen_fixtures.KitchenTests.configure
    stock = kitchen_fixtures.KitchenTests.stock

    def call(self, path, data=None, authorized=True, host="local:8768", origin=None):
        raw = json.dumps(data or {}).encode()
        handler = SimpleNamespace(
            path=path,
            headers={
                "Host": host,
                "Content-Length": str(len(raw)),
                **({"Origin": origin} if origin else {}),
            },
            authorized=lambda: authorized,
            rfile=io.BytesIO(raw),
            connection=Mock(),
            respond=Mock(),
        )
        bridge = SimpleNamespace(allowed_hosts={"local:8768"}, kitchen=self.kitchen)
        self.assertTrue(handle(handler, bridge, post=data is not None))
        return handler.respond.call_args.args

    def test_http_import_confirm_and_owner_only_cart_approval(self):
        self.assertEqual(self.call("/kitchen")[0], 200)
        self.assertEqual(self.call("/kitchen", authorized=False)[0], 403)
        self.assertEqual(
            self.call("/kitchen/settings", {"enabled": True}, origin="https://other")[0], 403
        )
        status, batch = self.call(
            "/kitchen/import", {"source": "synthetic", "text": "2 count beans"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(self.call("/kitchen/ingredients")[1]["items"], [])
        status, result = self.call(
            "/kitchen/confirm",
            {
                "id": batch["id"],
                "revision": batch["revision"],
                "items": batch["items"],
                "operation_id": "owner-review",
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["confirmed"], 1)
        self.assertEqual(
            self.call("/kitchen/shopping-approve", {"id": "x"}, authorized=False)[0], 403
        )
        self.assertEqual(self.call("/kitchen/confirm")[0], 400)
        self.assertEqual(self.call("/kitchen/erase", {"confirm": "wrong"})[0], 400)
        self.assertEqual(self.call("/kitchen/export")[0], 200)

    def test_nfc_requires_real_scan_and_does_not_retry(self):
        self.stock([dict(name="Beans", quantity=2, unit="can")])
        product = self.kitchen.dashboard()["products"][0]
        tags = Tags(
            self.folder / "tags", lambda: [], Mock(), clock=lambda: self.now, kitchen=self.kitchen
        )
        tags.save(
            dict(
                tag_id="test-tag",
                name="More beans",
                enabled=True,
                action="kitchen_reorder",
                product_id=product["id"],
                quantity=1,
                unit="can",
            )
        )
        self.assertEqual(tags.dispatch("test-tag")["status"], "real_scan_required")
        event = dict(tag_id="test-tag", event_id="scan1", observed_at=self.now)
        self.assertEqual(tags.scan(event)["status"], "added_to_local_shopping_draft")
        self.assertEqual(tags.scan(event)["status"], "duplicate")
        self.assertEqual(self.kitchen.dashboard()["shopping"][0]["items"][0]["quantity"], 1)


class KitchenProactiveTests(unittest.TestCase):
    def setUp(self):
        fixtures.LiveTests.setUp(self)
        self.kitchen = Planner(self.folder, clock=lambda: self.now)
        self.kitchen.settings({"enabled": True, "proactive": True})
        batch = self.kitchen.stage(
            "fiction", "synthetic", [dict(name="Spinach", quantity=1, best_by="2030-01-02")]
        )
        self.kitchen.confirm(batch["id"], batch["revision"], batch["items"], "confirm")
        self.args["destination"] = "desk"

    def test_attention_claim_revalidation_and_success_receipt(self):
        fixtures.LiveTests.attention(self)
        self.assertIsNone(self.live.check(**self.args))
        self.now += 121
        fixtures.LiveTests.attention(self)
        for flag in ("media", "quiet", "focus", "busy"):
            self.assertIsNone(self.live.check(**(self.args | {flag: True})))
        self.assertIsNone(self.live.check(**self.args))
        self.now += 121
        fixtures.LiveTests.attention(self)
        offer = self.live.check(**self.args)
        self.assertEqual(offer["kind"], "kitchen")
        self.assertTrue(self.live.claim(offer))
        self.assertTrue(self.live.revalidate_chore_offer(offer))
        self.assertIn("Spinach", self.live.opening(offer, Mock())["reply"])
        self.kitchen.settings({"proactive": False})
        self.assertFalse(self.live.revalidate_chore_offer(offer))

    def test_successful_delivery_suppresses_only_acknowledged_date_note(self):
        fixtures.LiveTests.attention(self)
        self.live.check(**self.args)
        self.now += 121
        fixtures.LiveTests.attention(self)
        offer = self.live.check(**self.args)
        self.assertTrue(self.live.claim(offer))
        self.live.delivered(offer, success=False)
        self.assertIsNotNone(self.kitchen.offer())
        self.live.delivered(offer, success=True)
        self.assertIsNone(self.kitchen.offer())
