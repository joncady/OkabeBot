"""Shared motion sampling and fail-closed device leases, without hardware."""

import json
import math
import shutil
import subprocess
import unittest
from pathlib import Path
from pi.animation import sample
from pi.work_state import WorkState
from okabebot.motion import catalog
from okabebot.prompts import prompt, source


class MotionTests(unittest.TestCase):
    def test_all_clips_are_bounded_and_busy_interrupts_idle(self):
        data = catalog()
        for style in data["characters"]:
            seen = set()
            for tick in range(10000):
                motion = sample(data, style, tick / 20)
                seen.add(motion["clip"])
                for key in ("body_y", "head_x", "head_y", "gaze", "hand", "foot"):
                    self.assertTrue(math.isfinite(motion[key]))
                    self.assertLessEqual(abs(motion[key]), 4)
            self.assertTrue(set(data["characters"][style]) <= seen)
        for options in ({"activity": "speaking"}, {"blocked": True}, {"reduced": True}):
            self.assertEqual(sample(data, "okabe", 25, **options)["clip"], "rest")

    def test_browser_and_pi_sample_same_channels(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node unavailable")
        cases = [
            (s, t, stage)
            for s in catalog()["characters"]
            for t in (0, 0.25, 2, 23, 24.8, 55, 89, 170)
            for stage in ("", "researching", "drafting", "awaiting_review")
        ]
        script = "const {sampleMotion}=require('./okabebot/web/lab-room.js');const fs=require('fs');const d=JSON.parse(fs.readFileSync('okabebot/assets/character-motion.json'));process.stdout.write(JSON.stringify(JSON.parse(process.argv[1]).map(([s,t,stage])=>sampleMotion(d,s,t,'idle',false,stage))));"
        result = json.loads(
            subprocess.check_output([node, "-e", script, json.dumps(cases)], text=True)
        )
        for case, browser in zip(cases, result):
            actual = sample(catalog(), case[0], case[1], stage=case[2])
            self.assertEqual(set(actual), set(browser))
            for key, value in actual.items():
                if type(value) is float:
                    self.assertAlmostEqual(value, browser[key], places=10)
                else:
                    self.assertEqual(value, browser[key])

    def test_pixel_poses_render_through_transition_boundaries(self):
        from pi import scene

        for style in catalog()["characters"]:
            for stage in ("researching", "drafting", "awaiting_review"):
                for tick in (0, 1, 5, 10, 20, 40, 80):
                    self.assertEqual(
                        scene.render(
                            style=style,
                            phase=tick / 20,
                            work={"stage": stage, "elapsed_seconds": tick / 20},
                        ).size,
                        (480, 320),
                    )

    def test_work_expires_locally_and_rejects_content_or_nonfinite_time(self):
        now = [100]
        state = WorkState(clock=lambda: now[0])
        data = dict(
            work=dict(kind="general", stage="drafting", elapsed_seconds=2, lease_seconds=8),
            motion=dict(enabled=True, reduced_motion=False),
        )
        state.update(data)
        now[0] += 3
        self.assertEqual(state.snapshot()[0]["elapsed_seconds"], 5)
        now[0] += 6
        self.assertEqual(state.snapshot()[0], {})
        for change in (
            {"title": "Private"},
            {"elapsed_seconds": float("nan")},
            {"stage": "ordering"},
        ):
            with self.assertRaises(ValueError):
                state.update(dict(data, work=dict(data["work"], **change)))


class PromptTests(unittest.TestCase):
    def test_templates_compact_static_only_and_reject_missing_slots(self):
        value = "Line one\n  $persona {literal}"
        result = prompt("dispatcher", policy=value)
        self.assertIn(value, result)
        with self.assertRaises(KeyError):
            prompt("dispatcher")
        with self.assertRaises(ValueError):
            source("../private")
        for path in Path("okabebot/prompts").glob("*.md"):
            self.assertTrue(source(path.stem))
