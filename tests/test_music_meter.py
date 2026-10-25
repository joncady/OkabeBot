import unittest
import array
import importlib.util
from pathlib import Path
import threading
import time

spec = importlib.util.spec_from_file_location(
    "music_meter", Path(__file__).parents[1] / "pi/music_meter.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class MusicMeterTests(unittest.TestCase):
    def test_energy_silence_and_attack(self):
        energy = module.Energy()
        assert energy.measure(bytes(1600)) == 0
        attack = array.array("h", [14000, -14000] * 400).tobytes()
        assert energy.measure(attack) > 0.8
        assert energy.measure(bytes(1600)) == 0

    def test_disable_stops_capture_and_clears_lease(self):
        meter = module.MusicMeter.__new__(module.MusicMeter)
        meter.guard = threading.RLock()
        meter.process = None
        meter.level = 0.8
        meter.error = None
        meter.until = time.monotonic() + 100
        assert meter.control(False) == {"active": False, "level": 0, "error": None}
        assert meter.until == 0

    def test_meter_consumes_peak_and_renews_short_lease(self):
        meter = module.MusicMeter.__new__(module.MusicMeter)
        meter.guard = threading.RLock()
        meter.process = None
        meter.level = 0.7
        meter.error = None
        assert meter.control(True)["level"] == 0.7
        assert meter.level == 0
        assert 0 < meter.until - time.monotonic() <= 3

    def test_preemption_terminates_process_and_releases_audio_lock(self):
        from unittest.mock import Mock

        meter = module.MusicMeter.__new__(module.MusicMeter)
        meter.guard = threading.RLock()
        meter.audio_lock = threading.Lock()
        meter.audio_lock.acquire()
        process = Mock()
        meter.process = process
        meter.level = 1
        meter.preempt()
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=0.5)
        process.stdout.close.assert_called_once()
        assert not meter.audio_lock.locked()
        assert meter.process is None
        assert meter.level == 0
        assert meter.blocked_until > time.monotonic()
        meter.stop()  # Idempotent; must not release someone else's lock.

    def test_music_pulse_decay_and_notification_precedence(self):
        from pi import scene

        music = {"is_playing": True, "meter_active": True, "level": 1, "pulse_at": time.monotonic()}
        strong = scene.shapes(music=music, phase=0)
        music["level"] = 0
        quiet = scene.shapes(music=music, phase=0)
        assert strong != quiet
        note = {"title": "Door opened", "body": "", "source": "system"}
        assert scene.shapes(notification=note, music=music, phase=0) == scene.shapes(
            notification=note, phase=0
        )
