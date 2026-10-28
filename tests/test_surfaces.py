"""Isolated handoff acceptance, never discovers or changes a real TV."""

from unittest.mock import Mock, patch
import unittest
from okabebot.surfaces import Surfaces
from pi.travel import Motion, shifted


class SurfaceTests(unittest.TestCase):
    def test_motion_direction_idempotence_and_lost_controller(self):
        motion = Motion()
        command = dict(
            phase="departing",
            transition_id="a" * 32,
            direction="left",
            duration_seconds=1,
            lease_seconds=12,
        )
        motion.command(command, now=0)
        assert -520 < motion.sample(0.5)[1] < 0
        motion.command(command, now=0.7)
        assert motion.started == 0
        assert motion.sample(1)[0] == "away"
        assert motion.sample(14)[0] == "arriving"
        assert motion.sample(14.5)[1] < 0
        assert motion.sample(15)[0] == "home"
        motion.command(dict(command, direction="right", transition_id="b" * 32), now=20)
        assert motion.sample(20.5)[1] > 0

    def test_vertical_travel_preserves_direction_and_returns_home(self):
        for direction, sign in (("up", -1), ("down", 1)):
            motion = Motion()
            motion.command(
                dict(
                    phase="departing",
                    transition_id="a" * 32,
                    direction=direction,
                    duration_seconds=1,
                    lease_seconds=12,
                ),
                now=0,
            )
            phase, dx, dy = motion.sample(0.5)
            self.assertEqual(dx, 0)
            self.assertGreater(dy * sign, 200)
            motion.sample(1)
            motion.command(
                dict(
                    phase="arriving",
                    transition_id="a" * 32,
                    direction=direction,
                    duration_seconds=1,
                    lease_seconds=12,
                ),
                now=2,
            )
            self.assertEqual(motion.sample(3)[0], "home")

    def test_transforms_keep_background_fixed(self):
        shapes = [("rectangle", (0, 0, 480, 320), "black", 0), ("line", (1, 2, 3, 4), "white", 2)]
        assert shifted(shapes, -10, 3) == [shapes[0], ("line", (-9, 5, -7, 7), "white", 2)]

    def test_waits_for_both_tv_readiness_and_actual_pi_render(self):
        rpc = Mock(return_value={"presence": {"transition_id": "wrong", "rendered": "away"}})
        s = Surfaces(rpc, start=False)
        s.begin("http://test", launch=False)
        token = s.token
        s.tick(s.started + 1)
        rpc.assert_not_called()
        s.heartbeat(token)
        s.tick()
        assert s.phase == "leaving_pi"
        assert rpc.call_args.args[0]["phase"] == "departing"
        s.tick()
        assert s.phase == "leaving_pi"
        rpc.return_value = {"presence": {"transition_id": s.identifier, "rendered": "away"}}
        s.tick()
        assert s.phase == "entering_tv"
        s.acknowledge(token, "entered", s.identifier)
        assert s.phase == "tv"
        s.return_home()
        assert s.phase == "leaving_tv"
        with patch.object(s, "_quit_owned_receiver"):
            s.acknowledge(token, "departed", s.identifier)
        assert s.phase == "entering_pi"
        s.tick()
        assert rpc.call_args.args[0]["phase"] == "arriving"
        # Duplicate departed ACK cannot repeat a physical command.
        count = rpc.call_count
        with self.assertRaises(PermissionError):
            s.acknowledge(token, "departed", s.identifier)
        assert rpc.call_count == count
        rpc.return_value = {"presence": {"transition_id": s.identifier, "rendered": "home"}}
        s.tick()
        assert s.phase == "pi" and not s.authorized(token)

    def test_failed_receiver_never_hides_pi(self):
        rpc = Mock()
        s = Surfaces(rpc, start=False)
        s.begin("http://test", launch=False)
        s.tick(s.started + 21)
        assert s.phase == "pi"
        rpc.assert_not_called()

    def test_preview_cannot_control_and_stale_acks_rejected(self):
        s = Surfaces(Mock(), start=False)
        s.preview("http://test")
        token = s.preview_token
        assert s.authorized(token)
        assert not s.authorized(token, preview=False)
        with self.assertRaises(PermissionError):
            s.heartbeat(token)
        s.begin("http://test", launch=False)
        with self.assertRaises(PermissionError):
            s.acknowledge(s.token, "entered", "old")

    def test_lost_receiver_waits_until_tv_visibility_has_expired(self):
        s = Surfaces(Mock(), start=False)
        s.begin("http://test", launch=False)
        s.phase = "tv"
        s.last_seen = 0
        with patch("okabebot.surfaces.time.monotonic", return_value=10):
            s.tick(10)
        assert s.phase == "recovering"
        s.rpc.assert_not_called()
        s.tick(16)
        s.rpc.assert_not_called()
        s.tick(18)
        assert s.rpc.call_args.args[0]["phase"] == "arriving"

    def test_receiver_projection_does_not_disclose_full_control_state(self):
        s = Surfaces(Mock(), start=False)
        s.preview("http://test")
        with patch(
            "okabebot.scene.live",
            return_value={"persona": "secret", "envelope": [0, 0.4], "activity": "speaking"},
        ):
            state = s.view(
                s.preview_token,
                {
                    "messages": ["secret"],
                    "approvals": ["secret"],
                    "character": "Okabe",
                    "notifications": ["secret"],
                },
            )
        assert "messages" not in state and "approvals" not in state and "notifications" not in state
        assert state["presenter"] == {"envelope": [0, 0.4], "activity": "speaking"}
        assert "persona" not in state["character"]

    def test_fresh_receiver_relaunches_after_navigation(self):
        from pychromecast.config import APP_DASHCAST
        from types import SimpleNamespace

        cast = Mock(status=SimpleNamespace(app_id=APP_DASHCAST, session_id="owned"))
        surface = Surfaces(Mock(), cast_getter=lambda: cast, start=False)
        with patch("pychromecast.controllers.BaseController.launch") as launch:
            surface.token = "scoped"
            surface._launch("http://example.invalid/tv/#scoped")
        cast.quit_app.assert_called_once_with(timeout=5)
        self.assertTrue(launch.call_args.kwargs["force_launch"])
        self.assertEqual(surface.receiver_session, "owned")

    def test_return_never_quits_somebody_elses_app(self):
        from types import SimpleNamespace

        cast = Mock(status=SimpleNamespace(app_id="youtube", session_id="new"))
        surface = Surfaces(Mock(), cast_getter=lambda: cast, start=False)
        surface.receiver_session = "owned"
        surface._quit_owned_receiver()
        cast.quit_app.assert_not_called()

    def test_receiver_close_revokes_access_and_keeps_return_pending_offline(self):
        s = Surfaces(Mock(), start=False)
        s.begin("http://test", launch=False)
        token = s.token
        s.phase = "tv"
        s.receiver_closed(token, s.identifier)
        self.assertEqual(s.phase, "entering_pi")
        self.assertFalse(s.authorized(token))
        s.rpc.side_effect = RuntimeError("offline")
        with self.assertRaises(RuntimeError):
            s.tick()
        with patch("okabebot.surfaces.time.monotonic", return_value=100):
            s._recover("Display unavailable")
        self.assertEqual(s.phase, "entering_pi")
        self.assertFalse(s.return_command_sent)
        s.rpc.side_effect = None
        s.rpc.return_value = {"presence": {"transition_id": s.identifier, "rendered": "home"}}
        s.tick(102)
        self.assertEqual(s.rpc.call_args.args[0]["phase"], "arriving")
        s.tick(103)
        self.assertEqual(s.phase, "pi")
        self.assertEqual(s.error, "")

    def test_confirmed_cast_app_exit_returns_without_heartbeat_delay(self):
        from types import SimpleNamespace

        cast = Mock(status=SimpleNamespace(app_id="backdrop", session_id="new"))
        s = Surfaces(Mock(), cast_getter=lambda: cast, start=False)
        s.begin("http://test", launch=False)
        s.phase, s.receiver_session = "tv", "owned"
        s.tick()
        self.assertEqual(s.phase, "entering_pi")
        self.assertEqual(s.rpc.call_args.args[0]["phase"], "arriving")
        cast.quit_app.assert_not_called()

    def test_interrupted_departure_reverses_without_a_jump(self):
        motion = Motion()
        command = dict(
            phase="departing",
            transition_id="a" * 32,
            direction="left",
            duration_seconds=1,
            lease_seconds=12,
        )
        motion.command(command, now=0)
        before = motion.sample(0.4)[1]
        motion.command(dict(command, phase="arriving"), now=0.4)
        self.assertAlmostEqual(motion.sample(0.4)[1], before)
        self.assertEqual(motion.sample(1.5)[0], "home")

    def test_long_away_renewals_then_return_preserve_arrival_progress(self):
        motion = Motion()
        command = dict(
            phase="departing",
            transition_id="a" * 32,
            direction="left",
            duration_seconds=1,
            lease_seconds=12,
        )
        motion.command(command, now=0)
        motion.sample(2)
        for now in range(3, 600, 3):
            motion.command(dict(command, phase="away"), now=now)
            self.assertEqual(motion.sample(now)[0], "away")
        motion.command(dict(command, phase="arriving"), now=600)
        self.assertLess(motion.sample(600.5)[1], 0)
        motion.command(dict(command, phase="arriving"), now=600.7)
        self.assertEqual(motion.sample(601.1)[0], "home")
