import unittest

from arm_integration import ArmDispatcher, canonical_arm_command


class FakeArm:
    def __init__(self):
        self.calls = []
        self.fail = False

    def pick(self, row, col):
        self.calls.append(("pick", row, col))
        return not self.fail

    def place_right(self):
        self.calls.append(("place",))
        return not self.fail

    def reset_upright(self):
        self.calls.append(("reset",))
        return not self.fail


class ArmIntegrationTests(unittest.TestCase):
    def test_only_four_grid_labels_map(self):
        self.assertEqual(canonical_arm_command("抓取第一行第一列"), "从第一行第一列夹取")
        self.assertIsNone(canonical_arm_command("抓取第三行第三列"))
        self.assertIsNone(canonical_arm_command("抓握"))
        self.assertIsNone(canonical_arm_command("急停"))

    def test_disabled_never_calls_backend(self):
        backend = FakeArm()
        arm = ArmDispatcher(backend, enabled=False)
        result = arm.dispatch(True, "复位", "u1", reset_confirmed=True)
        self.assertEqual(result["reason"], "execution_disabled")
        self.assertEqual(backend.calls, [])

    def test_state_sequence_and_duplicate_gate(self):
        backend = FakeArm()
        arm = ArmDispatcher(backend, enabled=True)
        self.assertTrue(arm.dispatch(True, "复位", "u0", reset_confirmed=True)["ok"])
        self.assertTrue(arm.dispatch(True, "抓取第二行第一列", "u1")["ok"])
        duplicate = arm.dispatch(True, "抓取第二行第一列", "u1")
        self.assertEqual(duplicate["reason"], "duplicate_utterance")
        self.assertTrue(arm.dispatch(True, "松开", "u2")["ok"])
        self.assertEqual(arm.state, "PLACED")

    def test_identity_and_reset_confirmation(self):
        backend = FakeArm()
        arm = ArmDispatcher(backend, enabled=True)
        self.assertEqual(arm.dispatch(False, "复位", "u0")["reason"], "identity_rejected")
        self.assertEqual(arm.dispatch(True, "复位", "u0")["reason"], "reset_requires_confirmation")
        self.assertEqual(backend.calls, [])

    def test_failure_enters_fault_without_retry(self):
        backend = FakeArm()
        backend.fail = True
        arm = ArmDispatcher(backend, enabled=True)
        result = arm.dispatch(True, "复位", "u0", reset_confirmed=True)
        self.assertFalse(result["ok"])
        self.assertEqual(arm.state, "FAULT")
        self.assertEqual(len(backend.calls), 1)


if __name__ == "__main__":
    unittest.main()
