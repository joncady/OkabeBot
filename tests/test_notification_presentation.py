"""Deterministic presentation clocks, interruption and face independence; no hardware."""

import json
import shutil
import subprocess
import unittest
from okabebot.characters.presentation import Notice
from okabebot.characters import motion_catalog
from pi.animation import sample
from pi import scene


class NoticeTests(unittest.TestCase):
    def test_enter_repeated_poll_exit_and_privacy_withdrawal(self):
        notice = Notice(clock=lambda: 0)
        item = dict(
            id="fiction", source="calendar", title="Invented appointment", body="Synthetic details"
        )
        notice.set(item, 0)
        self.assertEqual(notice.sample(0)[1], 0)
        self.assertAlmostEqual(notice.sample(0.25)[1], 0.5)
        notice.set(dict(reversed(list(item.items()))), 0.3)
        self.assertEqual(notice.sample(0.5)[1], 1)
        notice.set(None, 0.6)
        visible, progress = notice.sample(0.6)
        self.assertEqual(visible, {"title": "", "body": "", "source": ""})
        self.assertEqual(progress, 1)
        self.assertAlmostEqual(notice.sample(0.75)[1], 0.5)
        self.assertEqual(notice.sample(0.91), (None, 0))

    def test_replacement_exits_before_new_content_and_cancel_never_revives(self):
        notice = Notice(clock=lambda: 0)
        notice.set({"title": "First"}, 0)
        notice.sample(0.5)
        notice.set({"title": "Second"}, 0.5)
        self.assertEqual(notice.sample(0.6)[0]["title"], "First")
        self.assertEqual(notice.sample(0.81), ({"title": "Second"}, 0))
        self.assertAlmostEqual(notice.sample(1.06)[1], 0.5)
        notice.set(None, 1.06)
        self.assertEqual(notice.sample(1.5), (None, 0))
        self.assertEqual(notice.sample(10), (None, 0))

    def test_reduced_motion_settles_immediately_and_does_not_mutate_input(self):
        notice = Notice(clock=lambda: 0)
        item = {"title": "Invented"}
        notice.set(item, 0)
        self.assertEqual(notice.sample(0, reduced=True), (item, 1))
        notice.set(None, 1)
        self.assertEqual(notice.sample(1, reduced=True), (None, 0))
        self.assertEqual(item, {"title": "Invented"})

    def test_blink_has_one_clock_across_notifications_speech_and_reduced_motion(self):
        data = motion_catalog()
        for style in data["characters"]:
            for t in (0, 0.1, 1, 2.3, 5, 7.3, 8):
                expected = sample(data, style, 100, face_seconds=t)["blink"]
                for flags in ({"blocked": True}, {"activity": "speaking"}, {"reduced": True}):
                    self.assertEqual(
                        sample(data, style, 0, face_seconds=t, **flags)["blink"], expected
                    )

    def test_zero_progress_matches_rest_and_every_transition_frame_renders(self):
        item = {"source": "system", "title": "Invented", "body": "A synthetic notification"}
        for style in motion_catalog()["characters"]:
            idle = scene.render(style=style, phase=1)
            hidden = scene.render(notification=item, style=style, phase=1, notification_progress=0)
            self.assertEqual(idle.tobytes(), hidden.tobytes(), style)
            for p in (0, 0.01, 0.1, 0.3, 0.5, 0.7, 0.9, 1):
                image = scene.render(
                    notification=item,
                    style=style,
                    phase=1,
                    notification_progress=p,
                    mouth=0.5,
                    activity="speaking",
                )
                self.assertEqual(image.size, (480, 320))

    def test_sleeves_reach_the_moving_card_grips(self):
        from okabebot.characters import get

        for style in ("okabe", "kurisu"):
            for p in (0.01, 0.1, 0.3, 0.5, 0.9, 1):
                shapes = scene.shapes(
                    style=style, notification={"source": "system"}, notification_progress=p
                )
                for side, offset in enumerate((-6, -3)):
                    forearm = shapes[offset + 1][1]
                    wrist = ((forearm[4] + forearm[6]) / 2, (forearm[5] + forearm[7]) / 2)
                    self.assertAlmostEqual(wrist[0], get(style).presentation()["grips"][side] + 10)
                    self.assertAlmostEqual(wrist[1], 191 + (1 - p) * 140)

    def test_python_browser_transition_parity(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node unavailable")
        actions = [
            ("set", 0, {"title": "First"}),
            ("sample", 0.2, None),
            ("sample", 0.5, None),
            ("set", 0.6, {"title": "Second"}),
            ("sample", 0.8, None),
            ("sample", 1, None),
            ("sample", 1.5, None),
            ("set", 1.6, None),
            ("sample", 1.7, None),
            ("sample", 2, None),
        ]
        expected = []
        notice = Notice(clock=lambda: 0)
        for op, t, value in actions:
            if op == "set":
                notice.set(value, t)
            else:
                expected.append(notice.sample(t))
        script = "const {Notice}=require('./okabebot/web/lab-room.js');const n=new Notice(),out=[];for(const [op,t,value]of JSON.parse(process.argv[1])){if(op==='set')n.set(value,t);else{const r=n.sample(t);out.push([r.notification,r.progress]);}}process.stdout.write(JSON.stringify(out));"
        actual = json.loads(
            subprocess.check_output([node, "-e", script, json.dumps(actions)], text=True)
        )
        for (value, p), (browser, q) in zip(expected, actual):
            self.assertEqual(value, browser)
            self.assertAlmostEqual(p, q)
