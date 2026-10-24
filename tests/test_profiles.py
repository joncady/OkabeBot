import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from copy import deepcopy
from okabebot import profiles
from okabebot.config import DEFAULTS
from okabebot.codex import configured_input


class ProfilesTests(unittest.TestCase):
    def test_selection_is_persistent_and_updates_next_turn(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(profiles, "state_dir", return_value=Path(tmp)),
            patch.object(profiles, "get_config", return_value=deepcopy(DEFAULTS)),
        ):
            profiles.select_profile("kurisu")
            self.assertEqual(profiles.current_character()["style"], "kurisu")
            self.assertIn("current character name is Kurisu", configured_input("Hello"))
            profiles.select_profile("pip")
            self.assertIn("current character name is Pip", configured_input("Hello"))
            profiles.select_profile("configured")
            self.assertEqual(profiles.current_character()["name"], "Okabe")

    def test_invalid_selection_does_not_overwrite_saved_choice(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(profiles, "state_dir", return_value=Path(tmp)),
            patch.object(profiles, "get_config", return_value=deepcopy(DEFAULTS)),
        ):
            profiles.select_profile("kurisu")
            with self.assertRaises(ValueError):
                profiles.select_profile("../bad")
            self.assertEqual(profiles.selection(), "kurisu")
            (Path(tmp) / "profile.json").write_text("{broken")
            self.assertEqual(profiles.current_character()["name"], "Okabe")


class CharacterThreadTests(unittest.TestCase):
    def test_new_persona_starts_fresh_thread_and_same_persona_reuses_it(self):
        from okabebot.codex import Codex
        from unittest.mock import Mock

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("okabebot.codex.voice_instructions", return_value="Kurisu instructions"),
        ):
            c = Codex.__new__(Codex)
            c.folder = Path(tmp)
            (c.folder / "thread.json").write_text(
                '{"thread_id":"old","instructions":"Okabe instructions"}'
            )
            c.call = Mock(return_value={"thread": {"id": "new"}})
            c.notify = Mock()
            c.ensure_character_thread()
            self.assertEqual(c.call.call_args_list[0].args[0], "thread/start")
            self.assertEqual(c.thread_id, "new")
            c.call.reset_mock()
            c.ensure_character_thread()
            c.call.assert_not_called()
