"""Synthetic kitchen lifecycle and approval boundaries; no accounts or hardware."""

from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from okabebot.amadeus import Store
from okabebot.amadeus_onboarding import SYSTEM, KEY
from okabebot.kitchen import export
from okabebot.kitchen_import import parse
from okabebot.kitchen_planning import Planner
from okabebot.kitchen_shopping import Shopping


class KitchenTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.now = datetime(2032, 6, 7, 10, tzinfo=timezone.utc).timestamp()
        self.setup = dict(profile="synthetic", paused=False, guest=False, timezone="UTC")
        self.configure()
        self.kitchen = Planner(self.folder, clock=lambda: self.now)
        self.kitchen.settings({"enabled": True})

    def configure(self):
        with closing(Store(self.folder)) as s:
            s.remember(SYSTEM, KEY, self.setup)

    def stock(self, items, identity="receipt-1"):
        batch = self.kitchen.stage("fiction", identity, items)
        return self.kitchen.confirm(batch["id"], batch["revision"], items, "confirm:" + identity)

    def test_import_review_dedupe_and_distinct_purchase_lots(self):
        items = [dict(name="Rice", quantity=2, unit="kg")]
        a = self.kitchen.stage("fiction", "r1", items)
        self.assertEqual(self.kitchen.snapshot()["items"], [])
        self.assertEqual(a, self.kitchen.stage("fiction", "r1", items))
        with self.assertRaises(ValueError):
            self.kitchen.stage("fiction", "r1", [dict(name="Beans")])
        first = self.kitchen.confirm(a["id"], a["revision"], items, "op1")
        self.assertEqual(first, self.kitchen.confirm(a["id"], a["revision"], items, "op1"))
        self.stock(items, "r2")
        self.assertEqual(len(self.kitchen.snapshot()["items"]), 2)
        self.assertEqual(len({v["product_id"] for v in self.kitchen.snapshot()["items"]}), 1)

    def test_atomic_import_validation_and_movement_versions(self):
        with self.assertRaises(ValueError):
            self.stock([dict(name="Rice"), dict(name="Beans", quantity=-1)])
        self.assertEqual(self.kitchen.snapshot()["items"], [])
        self.stock([dict(name="Eggs", quantity=6)])
        lot = self.kitchen.snapshot()["items"][0]
        updated = self.kitchen.adjust(lot["id"], lot["revision"], 2, "consume-1", "consume")
        self.assertEqual(updated["quantity"], 4)
        self.assertEqual(
            updated, self.kitchen.adjust(lot["id"], lot["revision"], 2, "consume-1", "consume")
        )
        with self.assertRaises(ValueError):
            self.kitchen.adjust(lot["id"], lot["revision"], 0, "stale")
        with self.assertRaises(ValueError):
            self.kitchen.adjust(lot["id"], updated["revision"], 9, "over", "consume")

    def test_recipe_dates_tastes_and_stock_reservations(self):
        self.stock(
            [
                dict(name="Beans", quantity=2, unit="count", best_by="2032-06-08"),
                dict(name="Rice", quantity=1, unit="count"),
            ]
        )
        self.kitchen.import_recipes(
            [
                dict(
                    name="Beans bowl",
                    ingredients=[dict(name="Beans", quantity=1), dict(name="Rice", quantity=1)],
                    tags=["quick"],
                    meals=["dinner"],
                ),
                dict(
                    name="Toast", ingredients=[dict(name="Bread", quantity=1)], meals=["breakfast"]
                ),
            ]
        )
        self.kitchen.settings({"planning_days": 2, "tastes": ["quick"]})
        ideas = self.kitchen.suggest()["suggestions"]
        self.assertEqual(ideas[0]["taste_matches"], ["quick"])
        self.assertTrue(ideas[0]["use_soon"])
        plan = self.kitchen.generate()
        rice = next(v for v in plan["shopping"]["items"] if v["name"] == "rice")
        self.assertEqual(rice["quantity"], 1)
        self.assertEqual(len(plan["plan"]["slots"]), 4)  # Mon/Tue breakfast+dinner
        # Recipe recommendation never consumes inventory.
        self.assertEqual(sum(v["quantity"] for v in self.kitchen.snapshot()["items"]), 3)

    def test_weekend_slots_snooze_and_stale_uncertainty(self):
        self.now = datetime(2032, 6, 12, 10, tzinfo=timezone.utc).timestamp()
        self.stock([dict(name="Milk", quantity=1, best_by="2032-06-13")])
        self.kitchen.settings({"planning_days": 1, "proactive": True})
        self.assertEqual(len(self.kitchen.generate()["plan"]["slots"]), 3)
        self.assertIsNotNone(self.kitchen.offer())
        self.kitchen.settings({"snoozed_until": self.now + 3600})
        self.assertIsNone(self.kitchen.offer())
        self.now += 31 * 86400
        self.assertTrue(self.kitchen.snapshot()["items"][0]["stale"])

    def test_daily_index_once_timezone_and_resume_pending(self):
        self.kitchen.settings({"daily_hour": 11})
        self.assertEqual(self.kitchen.index()["state"], "not_due")
        self.now += 3600
        first = self.kitchen.index()
        self.assertEqual(first, self.kitchen.index())
        # Interrupted after durable claim resumes next tick.
        with self.kitchen.session() as (s, p, c):
            self.kitchen.put(s, p, "index", dict(first, plan_pending=True))
        self.assertFalse(self.kitchen.index()["plan_pending"])

    def test_private_pause_guest_disable_and_forget(self):
        self.stock([dict(name="Oats")])
        self.assertTrue(self.kitchen.dashboard()["products"])
        with closing(Store(self.folder)) as s:
            self.assertTrue(export(s, "synthetic"))
        self.setup["guest"] = True
        self.configure()
        with self.assertRaises(PermissionError):
            self.kitchen.snapshot()
        with self.assertRaises(PermissionError):
            self.kitchen.generate()
        self.setup["guest"] = False
        self.configure()
        with closing(Store(self.folder)) as s:
            s.forget("synthetic")
        with closing(Store(self.folder)) as s:
            self.assertEqual(export(s, "synthetic"), [])

    def test_nfc_actions_are_durable_and_do_not_order(self):
        self.stock([dict(name="Coffee", quantity=2, unit="bag")])
        lot = self.kitchen.snapshot()["items"][0]
        a = self.kitchen.tag(lot["product_id"], "kitchen_reorder", 1, "bag", "scan-1")
        self.assertEqual(
            a, self.kitchen.tag(lot["product_id"], "kitchen_reorder", 1, "bag", "scan-1")
        )
        self.assertEqual(self.kitchen.dashboard()["shopping"][0]["items"][0]["quantity"], 1)
        self.kitchen.tag(lot["product_id"], "kitchen_used_up", 1, "bag", "scan-2")
        self.assertEqual(self.kitchen.snapshot()["items"][0]["quantity"], 0)

    def test_receipt_and_grocy_imports_are_only_candidates(self):
        values = parse("BEANS 2.99\nTOTAL 2.99\nTAX 0.00\n", "receipt")
        self.assertEqual(values[0]["name"], "BEANS")
        self.assertEqual(len(values), 1)
        value = parse(
            json.dumps([dict(product={"name": "Oats"}, amount=2, best_before_date="2032-09-01")]),
            "json",
        )[0]
        self.assertEqual(value["name"], "Oats")
        self.assertEqual(value["best_by"], "2032-09-01")
        with self.assertRaises(ValueError):
            parse("No recognizable price lines", "receipt")

    def test_units_normalize_without_density_guessing_and_goals_are_private(self):
        from unittest.mock import patch

        self.stock([dict(name="Rice", quantity=1, unit="kg")])
        self.assertEqual(self.kitchen.snapshot()["items"][0]["quantity"], 1000)
        self.kitchen.import_recipes(
            [
                dict(
                    name="Rice bowl",
                    ingredients=[dict(name="Rice", quantity=100, unit="g")],
                    tags=["quick"],
                )
            ]
        )
        self.kitchen.settings({"coaching": True, "goals": ["quick"]})
        self.assertFalse(self.kitchen.suggest()["suggestions"][0]["missing"])
        with patch("okabebot.amadeus_health.others_detected", return_value=True):
            self.assertEqual(self.kitchen.suggest()["coaching_goals"], [])

    def test_browser_contract_changes_cancel_approval_and_owner_cancel_is_final(self):
        from okabebot.kitchen_browser import Browser, FIELDS

        shop, job = self.shopping_job()
        products = [
            dict(product_id="sku", name="Beans", price_cents=100, packs=1, requested_name="beans")
        ]
        review = shop.review(job["id"], job["revision"], products)
        shop.approve(job["id"], review["revision"], review["manifest_hash"])
        Browser(self.folder).configure(
            {"enabled": True, "selectors": {k: "synthetic" for k in FIELDS}}
        )

        class NoWrites:
            def add_exact(self, product):
                raise AssertionError("Changed browser must never be used")

        self.assertEqual(shop.run(NoWrites())["status"], "blocked")
        with self.kitchen.session() as (s, p, c):
            draft = self.kitchen.get(s, p, "shopping", "synthetic-draft")
            draft = self.kitchen.put(s, p, "shopping", draft)
        queued = shop.queue(draft["id"], draft["revision"])
        self.assertEqual(shop.cancel(queued["id"], queued["revision"])["status"], "canceled")
        self.assertEqual(shop.run(NoWrites()), {"state": "idle"})

    def test_meal_windows_and_delivery_do_not_suppress_later_dinner(self):
        self.now = datetime(2032, 6, 7, 7, tzinfo=timezone.utc).timestamp()
        self.kitchen.settings({"proactive": True, "planning_days": 1})
        self.kitchen.import_recipes(
            [
                dict(
                    name="Synthetic bowl",
                    ingredients=[dict(name="Beans", quantity=1)],
                    meals=["breakfast", "dinner"],
                )
            ]
        )
        self.kitchen.generate()
        breakfast = self.kitchen.offer()
        self.assertTrue(breakfast["slot"].endswith(":breakfast"))
        with self.kitchen.session() as (s, p, c):
            s.remember(p, "kitchen.delivered", {"slots": {breakfast["slot"]: self.now}})
        self.assertIsNone(self.kitchen.offer())
        self.now += 10 * 3600
        self.assertTrue(self.kitchen.offer()["slot"].endswith(":dinner"))

    def test_cancel_during_multiple_packs_stops_before_next_write(self):
        shop, job = self.shopping_job()
        products = [
            dict(product_id="sku", name="Beans", price_cents=100, packs=3, requested_name="beans")
        ]
        review = shop.review(job["id"], job["revision"], products)
        shop.approve(job["id"], review["revision"], review["manifest_hash"])
        calls = []

        class CancelAfterOne:
            def add_exact(inner, product):
                calls.append(product)
                with shop.session() as (s, p, c):
                    current = shop.get(s, p, "browser_job", job["id"])
                shop.cancel(job["id"], current["revision"])

        self.assertEqual(shop.run(CancelAfterOne())["status"], "unknown")
        self.assertEqual(len(calls), 1)

    def shopping_job(self):
        with self.kitchen.session() as (s, p, c):
            draft = self.kitchen.put(
                s,
                p,
                "shopping",
                dict(
                    id="synthetic-draft",
                    name="Shopping",
                    items=[dict(name="beans", quantity=1, unit="can")],
                ),
            )
        shop = Shopping(self.folder, clock=lambda: self.now)
        return shop, shop.queue(draft["id"], draft["revision"])

    def test_shopping_search_review_approval_and_no_checkout(self):
        shop, job = self.shopping_job()

        class Adapter:
            calls = []

            def search(self, items):
                return [
                    dict(
                        product_id="synthetic-sku",
                        name="Beans",
                        price_cents=199,
                        packs=1,
                        requested_name="beans",
                    )
                ]

            def add_exact(self, item):
                self.calls.append(item)

        adapter = Adapter()
        review = shop.run(adapter)
        self.assertEqual(review["status"], "review")
        self.assertEqual(adapter.calls, [])
        with self.assertRaises(ValueError):
            shop.approve(job["id"], review["revision"], "wrong")
        shop.approve(job["id"], review["revision"], review["manifest_hash"])
        self.assertEqual(shop.run(adapter)["status"], "complete")
        self.assertEqual(len(adapter.calls), 1)
        self.assertEqual(shop.run(adapter), {"state": "idle"})

    def test_shopping_expiry_consent_changes_and_uncertain_write(self):
        shop, job = self.shopping_job()
        products = [
            dict(product_id="sku", name="Beans", price_cents=100, packs=1, requested_name="beans")
        ]
        review = shop.review(job["id"], job["revision"], products)
        shop.approve(job["id"], review["revision"], review["manifest_hash"])

        class Broken:
            def add_exact(self, item):
                raise TimeoutError("after click")

        self.assertEqual(shop.run(Broken())["status"], "unknown")
        self.assertEqual(shop.run(Broken()), {"state": "idle"})
        # Another draft approval expires before any browser write.
        with self.kitchen.session() as (s, p, c):
            draft = self.kitchen.get(s, p, "shopping", "synthetic-draft")
            draft = self.kitchen.put(s, p, "shopping", draft)
        job = shop.queue(draft["id"], draft["revision"])
        review = shop.review(job["id"], job["revision"], products)
        shop.approve(job["id"], review["revision"], review["manifest_hash"])
        self.now += 901
        self.assertEqual(shop.run(Broken())["status"], "blocked")
