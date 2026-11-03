import json
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

from controller import BusyError, SonicArmController
from ui.server import EnrollmentStore, StateStore


class FakeHardware:
    def __init__(self):
        self.quiet_captures = 0

    def capture_quiet(self, run_dir):
        self.quiet_captures += 1
        (Path(run_dir) / "quiet_raw24.wav").write_bytes(b"fake")
        return np.zeros((16, 2), dtype=np.float32)

    def capture_embedding(self, run_dir, stem, quiet, after_capture=None):
        if after_capture is not None:
            after_capture("声音采集完毕，正在进行识别")
        vector = np.zeros(192, dtype=np.float32)
        vector[0] = 1.0
        return vector, np.zeros(48000, dtype=np.float32), {
            "audio_gate": {"speech_over_quiet_db": 20.0},
            "actual_v8_ap_start": {"pointwise": 55, "FCM": 12},
        }

    def recognize_command(self, waveform):
        return {"class_name": "复位", "confidence": 0.98, "threshold": 0.8}


class FakeArmDispatcher:
    def __init__(self):
        self.connected = True
        self.state = "UNKNOWN"
        self.calls = []

    def status(self):
        return {
            "enabled": True,
            "connected": True,
            "state": self.state,
            "executing": False,
            "last_error": "",
        }

    def dispatch(self, speaker_verified, asr_text, utterance_id, *, reset_confirmed=False):
        self.calls.append(
            {
                "speaker_verified": speaker_verified,
                "asr_text": asr_text,
                "utterance_id": utterance_id,
                "reset_confirmed": reset_confirmed,
            }
        )
        ok = bool(speaker_verified and asr_text == "复位" and reset_confirmed)
        if ok:
            self.state = "READY"
        return {
            "ok": ok,
            "command": asr_text,
            "reason": "completed" if ok else "reset_requires_confirmation",
            "state": self.state,
            "executed": ok,
        }


class InstantController(SonicArmController):
    def _countdown(self, update, message):
        update(message)


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.config = {
            "paths": {"results_dir": "results"},
            "audio": {
                "maximum_capture_attempts": 3,
                "speech_seconds": 3.0,
                "quiet_reference_max_age_seconds": 300.0,
            },
            "decision": {
                "identity_threshold": 0.67,
                "identity_threshold_calibrated": False,
                "kws_threshold": 0.8,
                "kws_threshold_calibrated": False,
                "reject_labels": ["unknown", "silence"],
            },
            "arm": {
                "auto_reset_on_startup": True,
                "voice_reset_enabled": True,
            },
            "expected_sha256": {"bit": "bit-test", "hwh": "hwh-test"},
        }
        self.state = StateStore()
        self.state.update({"identity": {"threshold": 0.67}})
        self.enrollment = EnrollmentStore()
        self.hardware = FakeHardware()
        self.controller = InstantController(
            self.root, self.config, self.hardware, self.state, self.enrollment
        )

    def tearDown(self):
        self.temporary.cleanup()

    def wait_idle(self):
        deadline = time.time() + 2.0
        while self.controller.status()["busy"] and time.time() < deadline:
            time.sleep(0.01)
        self.assertFalse(self.controller.status()["busy"])

    def test_enroll_then_recognize(self):
        accepted = self.controller.start_enrollment({"name": "张同学", "id": "SA-002"})
        self.assertTrue(accepted["accepted"])
        self.wait_idle()
        self.assertEqual(self.enrollment.get()["status"], "complete")
        profile = self.root / "data" / "users" / "SA-002" / "profile.npy"
        metadata = profile.with_name("profile.json")
        self.assertTrue(profile.is_file())
        self.assertEqual(json.loads(metadata.read_text(encoding="utf-8"))["name"], "张同学")

        accepted = self.controller.start_recognition({})
        self.assertTrue(accepted["accepted"])
        self.wait_idle()
        state = self.state.get()
        self.assertEqual(state["identity"]["id"], "SA-002")
        self.assertEqual(state["command"]["text"], "复位")
        self.assertTrue(state["command"]["accepted"])
        self.assertEqual(state["arm"]["status"], "dry_run")
        self.assertFalse(state["connections"]["arm_serial"])
        self.assertEqual(self.hardware.quiet_captures, 1)

    def test_rejects_unsafe_user_id(self):
        with self.assertRaises(ValueError):
            self.controller.start_enrollment({"name": "测试", "id": "../bad"})

    def test_single_job_lock(self):
        self.controller._busy = True
        self.controller._job = "recognition"
        with self.assertRaises(BusyError):
            self.controller.start_enrollment({"name": "测试", "id": "SA-003"})

    def test_delete_user_moves_profile_to_recoverable_directory(self):
        self.controller.start_enrollment({"name": "待删除", "id": "SA-DEL"})
        self.wait_idle()
        result = self.controller.delete_user({"id": "SA-DEL"})
        self.assertTrue(result["deleted"])
        self.assertTrue(result["recoverable"])
        self.assertFalse((self.root / "data" / "users" / "SA-DEL").exists())
        recycled = self.root / result["recycle_path"]
        self.assertTrue((recycled / "profile.npy").is_file())
        self.assertTrue((recycled / "profile.json").is_file())

    def test_delete_user_rejected_while_busy(self):
        self.controller._busy = True
        self.controller._job = "recognition"
        with self.assertRaises(BusyError):
            self.controller.delete_user({"id": "SA-002"})

    def test_startup_reset_runs_synchronously_and_reaches_ready(self):
        arm = FakeArmDispatcher()
        self.controller.arm = arm
        status = self.controller.run_startup_arm_reset()
        self.assertEqual(status["state"], "READY")
        self.assertEqual(len(arm.calls), 1)
        self.assertTrue(arm.calls[0]["reset_confirmed"])
        self.assertTrue(arm.calls[0]["utterance_id"].startswith("startup-reset-"))

    def test_authenticated_voice_reset_is_confirmed_for_dispatch(self):
        arm = FakeArmDispatcher()
        self.controller.arm = arm
        self.controller.start_enrollment({"name": "张同学", "id": "SA-VOICE-RESET"})
        self.wait_idle()
        self.controller.start_recognition({})
        self.wait_idle()
        self.assertEqual(len(arm.calls), 1)
        self.assertEqual(arm.calls[0]["asr_text"], "复位")
        self.assertTrue(arm.calls[0]["reset_confirmed"])
        self.assertEqual(self.state.get()["arm"]["state"], "READY")


if __name__ == "__main__":
    unittest.main()
