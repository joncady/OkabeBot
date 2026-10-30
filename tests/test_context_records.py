"""Synthetic collection/compaction fixtures, never participant records."""

from tempfile import TemporaryDirectory
import unittest
from okabebot.amadeus import Store
from okabebot.context_records import ingest, query, clear


class RecordsTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.now = 2000000000
        self.store = Store(self.folder.name, clock=lambda: self.now)

    def tearDown(self):
        self.store.close()
        self.folder.cleanup()

    def put(self, items, **kw):
        with self.store.db:
            ingest(
                self.store,
                "tasks",
                "invented",
                items,
                complete=kw.get("complete", True),
                valid_until=self.now + 60,
                noisy=kw.get("noisy", False),
            )

    def test_full_collection_pagination_repeat_updates_and_identity(self):
        items = [{"id": str(i), "title": "Same title", "state": "needs_action"} for i in range(75)]
        self.put(items)
        self.now += 10
        self.put(list(reversed(items)))
        self.assertEqual(
            self.store.db.execute("SELECT count(*) FROM context_records").fetchone()[0], 75
        )
        self.assertEqual(
            self.store.db.execute("SELECT count(*) FROM context_changes").fetchone()[0], 75
        )
        first = query(self.store, "tasks", "invented", limit=50)
        second = query(self.store, "tasks", "invented", limit=50, offset=first["next_offset"])
        self.assertEqual(len(first["items"]) + len(second["items"]), 75)
        items[0]["title"] = "Renamed"
        self.put(items)
        self.assertEqual(
            self.store.db.execute("SELECT count(*) FROM context_changes").fetchone()[0], 76
        )
        self.assertEqual(len(query(self.store, "tasks", "invented", text="Renamed")["items"]), 1)

    def test_partial_omission_never_means_completed_or_deleted(self):
        self.put([{"id": "a", "title": "Keep"}, {"id": "b", "title": "Other"}])
        self.put([], complete=False)
        self.assertEqual(len(query(self.store, "tasks", "invented")["items"]), 2)
        self.put([], complete=True)
        self.assertEqual(query(self.store, "tasks", "invented")["items"], [])
        kinds = [r[0] for r in self.store.db.execute("SELECT kind FROM context_changes")]
        self.assertEqual(kinds.count("absent"), 2)

    def test_numeric_noise_aggregates_and_stale_is_not_absence(self):
        for n in (20, 20, 21):
            self.put([{"id": "temperature", "state": str(n)}], noisy=True)
        row = self.store.db.execute("SELECT * FROM context_signal_buckets").fetchone()
        self.assertEqual(
            (
                row["reports"],
                row["transitions"],
                row["minimum"],
                row["maximum"],
                row["numeric_count"],
            ),
            (3, 1, 20, 21, 3),
        )
        self.assertEqual(
            self.store.db.execute("SELECT count(*) FROM context_changes").fetchone()[0], 0
        )
        self.now += 61
        self.assertFalse(query(self.store, "tasks", "invented")["items"][0]["fresh"])
        with self.store.db:
            clear(self.store.db, source="tasks")
        self.assertEqual(query(self.store, "tasks", "invented")["items"], [])

    def test_duplicate_identical_reports_fold_but_conflicting_identity_rolls_back(self):
        self.put([{"id": "a", "title": "One"}] * 3)
        self.assertEqual(
            self.store.db.execute("SELECT reports FROM context_records").fetchone()[0], 1
        )
        with self.assertRaises(ValueError):
            self.put([{"id": "a", "title": "One"}, {"id": "a", "title": "Other"}])
        self.assertEqual(
            query(self.store, "tasks", "invented")["items"][0]["value"]["title"], "One"
        )

    def test_discrete_error_and_completion_survive_signal_aggregation(self):
        for state in ("running", "running", "error", "complete"):
            self.put([{"id": "washer", "state": state}], noisy=True)
        rows = self.store.db.execute("SELECT payload FROM context_changes").fetchall()
        self.assertEqual(len(rows), 3)
        self.assertIn('"error"', rows[1][0])

    def test_legacy_migration_preserves_original_time_and_deduplicates_reports(self):
        self.store.sources = frozenset(["tasks"])
        payload = {
            "provider": "tasks",
            "items": [{"id": "a", "title": "Invented task"}],
            "complete": "yes",
            "valid_until_at": self.now + 60,
        }
        self.store.observe(
            source="tasks",
            external_id="old-one",
            subject="invented",
            kind="feed_snapshot",
            payload=payload,
            observed_at=self.now - 100,
        )
        self.store.observe(
            source="tasks",
            external_id="old-two",
            subject="invented",
            kind="feed_snapshot",
            payload=payload,
            observed_at=self.now - 50,
        )
        self.put([{"id": "a", "title": "Invented task"}])
        rows = self.store.db.execute(
            "SELECT * FROM context_changes WHERE kind='legacy_observed'"
        ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["observed_at"], self.now - 100)
        self.assertEqual(rows[0]["expires_at"], self.now - 100 + self.store.retention)

    def test_aggregate_view_and_expiry(self):
        self.store.retention = 60
        for n in (10, 20):
            self.put([{"id": "sensor", "state": str(n)}], noisy=True)
        result = query(self.store, "tasks", "invented", view="aggregates")
        self.assertEqual(result["items"][0]["value"]["mean_observed"], 15)
        self.assertTrue(result["items"][0]["historical"])
        self.now += 61
        self.store.prune()
        self.assertEqual(query(self.store, "tasks", "invented", view="aggregates")["items"], [])

    def test_numeric_aggregates_never_mix_units(self):
        self.put([{"id": "temperature", "state": "20", "unit": "°C"}], noisy=True)
        self.put([{"id": "temperature", "state": "68", "unit": "°F"}], noisy=True)
        result = query(self.store, "tasks", "invented", view="aggregates")
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual({r["value"]["unit"] for r in result["items"]}, {"°C", "°F"})
