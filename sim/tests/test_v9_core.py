import unittest

from v9_core import arm_step_for_label, decide, ui_payload


class DecisionTests(unittest.TestCase):
    def test_identity_denied_skips_command(self):
        result = decide(0.5, 0.67, None, ["unknown", "silence"])
        self.assertFalse(result["identity_accepted"])
        self.assertFalse(result["execute"])
        self.assertEqual(result["phase"], "denied")

    def test_valid_command_still_dry_run(self):
        kws = {"class_name": "抓取第一行第一列", "confidence": 0.98, "threshold": 0.9}
        result = decide(0.8, 0.67, kws, ["unknown", "silence"])
        self.assertTrue(result["identity_accepted"])
        self.assertTrue(result["command_accepted"])
        self.assertFalse(result["execute"])
        self.assertEqual(result["arm_step"], "pickup")

    def test_unknown_is_rejected(self):
        kws = {"class_name": "unknown", "confidence": 0.99, "threshold": 0.9}
        result = decide(0.8, 0.67, kws, ["unknown", "silence"])
        self.assertFalse(result["command_accepted"])
        self.assertFalse(result["execute"])
        self.assertEqual(result["arm_step"], "none")

    def test_low_confidence_is_rejected(self):
        kws = {"class_name": "复位", "confidence": 0.7, "threshold": 0.9}
        result = decide(0.8, 0.67, kws, ["unknown", "silence"])
        self.assertFalse(result["command_accepted"])
        self.assertFalse(result["execute"])

    def test_ui_payload_reports_serial_disconnected(self):
        decision = decide(0.8, 0.67, {"class_name": "复位", "confidence": 0.95, "threshold": 0.9}, ["unknown", "silence"])
        payload = ui_payload(
            user_id="SA-1",
            name="测试",
            similarity=0.8,
            identity_threshold=0.67,
            threshold_calibrated=False,
            kws_result={"class_name": "复位", "confidence": 0.95, "threshold": 0.9},
            decision=decision,
            physical_display_verified=False,
        )
        self.assertFalse(payload["connections"]["arm_serial"])
        self.assertFalse(payload["connections"]["display"])
        self.assertEqual(payload["arm"]["status"], "dry_run")

    def test_arm_mapping(self):
        self.assertEqual(arm_step_for_label("松开"), "place")
        self.assertEqual(arm_step_for_label("急停"), "none")


if __name__ == "__main__":
    unittest.main()
