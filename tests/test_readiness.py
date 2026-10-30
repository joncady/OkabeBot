import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from okabebot.readiness import Readiness, database_health, home_assistant_health, log_findings


class ReadinessTests(unittest.TestCase):
    def test_startup_then_ready_and_later_fault_does_not_reset_startup(self):
        now = Mock(return_value=1000)
        monitor = Readiness(
            "/unused",
            clock=now,
            db_probe=lambda _: {"state": "ready"},
            ha_probe=lambda _: {"state": "ready"},
        )
        devices = {"voice": {"available": True}, "display": {"available": True}}
        self.assertEqual("starting", monitor.snapshot(devices, {"available": False}, True)["state"])
        monitor.probe()
        with patch("builtins.print") as log:
            result = monitor.snapshot(devices, {"available": True}, True)
            monitor.snapshot(devices, {"available": True}, True)
            self.assertEqual("ready", result["state"])
            log.assert_called_once()
        now.return_value = 1001
        result = monitor.snapshot(devices, {"available": False}, True)
        self.assertEqual("attention", result["state"])
        self.assertEqual(1000, result["startup_complete_at"])

    def test_startup_failure_ages_into_attention_and_recovers(self):
        now = Mock(return_value=1000)
        monitor = Readiness(
            "/unused",
            clock=now,
            db_probe=Mock(side_effect=OSError("secret path")),
            ha_probe=lambda _: {"state": "not_configured"},
        )
        monitor.probe()
        now.return_value = 1200
        result = monitor.snapshot({}, {}, False)
        self.assertEqual("attention", result["state"])
        self.assertNotIn("secret", str(result))

    def test_partial_feed_does_not_mean_disconnected(self):
        m = Readiness(
            "/unused",
            db_probe=lambda _: {"state": "ready"},
            ha_probe=lambda _: {"state": "not_configured"},
        )
        m.probe()
        result = m.snapshot(
            {"voice": {"available": True}, "display": {"available": True}},
            {"available": True},
            True,
            {"watch_history": {"state": "connected_partial"}},
        )
        self.assertEqual("ready", result["state"])
        self.assertEqual("partial", result["components"][-1]["state"])

    def test_read_only_database_probe_reports_corruption_and_excludes_backups(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with sqlite3.connect(root / "valid.sqlite3") as db:
                db.execute("CREATE TABLE sample (id INTEGER)")
            (root / "bad.sqlite3").write_text("not a database")
            (root / "rollback").mkdir()
            (root / "rollback/ignored.sqlite3").write_text("bad")
            result = database_health(root)
            self.assertEqual("attention", result["state"])
            self.assertEqual("2 databases checked; 1 need attention", result["detail"])
            self.assertEqual("not_configured", home_assistant_health(root)["state"])
            self.assertFalse((root / "amadeus").exists())

    def test_database_checks_are_cached_but_ha_rechecked(self):
        db = Mock(return_value={"state": "ready"})
        ha = Mock(return_value={"state": "ready"})
        m = Readiness("/unused", db_probe=db, ha_probe=ha)
        m.probe()
        m.probe()
        self.assertEqual(1, db.call_count)
        self.assertEqual(2, ha.call_count)

    def test_log_diagnostics_distinguish_listener_failure_from_startup_history(self):
        text = "ERROR [firebase_messaging.fcmpushclient] Unknown error: bad, shutting down FcmPushClient.\nERROR [homeassistant.components.rest_command] Error fetching data: private.example\nWARNING [homeassistant.components.recorder.util] Ended unfinished session (private details)"
        findings = log_findings(text)
        self.assertEqual(["attention", "recovered", "history"], [x["state"] for x in findings])
        self.assertNotIn("private", str(findings))
        self.assertEqual([], log_findings("unrelated failure"))

    def test_pending_github_connection_keeps_initial_recovery_window(self):
        now = Mock(return_value=1000)
        m = Readiness(
            "/unused",
            clock=now,
            db_probe=lambda _: {"state": "ready"},
            ha_probe=lambda _: {"state": "ready"},
        )
        m.probe()
        devices = {"voice": {"available": True}, "display": {"available": True}}
        pending = {"configured": True, "available": False}
        self.assertEqual(
            "starting", m.snapshot(devices, {"available": True}, True, github=pending)["state"]
        )
        now.return_value += 181
        self.assertEqual(
            "attention", m.snapshot(devices, {"available": True}, True, github=pending)["state"]
        )
        self.assertEqual(
            "ready",
            m.snapshot(
                devices, {"available": True}, True, github={"configured": True, "available": True}
            )["state"],
        )

    def test_github_auth_failure_is_not_mistaken_for_pending_connection(self):
        m = Readiness(
            "/unused", db_probe=lambda _: {"state": "ready"}, ha_probe=lambda _: {"state": "ready"}
        )
        m.probe()
        result = m.snapshot(
            {"voice": {"available": True}, "display": {"available": True}},
            {"available": True},
            True,
            github={"configured": True, "available": False, "auth_required": True},
        )
        self.assertEqual("attention", result["state"])
