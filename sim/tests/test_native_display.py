import unittest
from pathlib import Path

from native_display import NativeUIRenderer, keyboard_key_at, keyboard_key_boxes, map_touch


ROOT = Path(__file__).resolve().parents[2] / "src" / "ps"


class NativeDisplayTests(unittest.TestCase):
    def test_touch_mapping_uses_native_panel_coordinates(self):
        self.assertEqual(map_touch(0, 0), (0, 0))
        self.assertEqual(map_touch(800, 480), (799, 479))
        self.assertEqual(map_touch(400, 240), (400, 240))

    def test_renderer_produces_native_800_by_480_pages(self):
        renderer = NativeUIRenderer(ROOT)
        state = {
            "phase": "idle",
            "headline": "请说出指令",
            "message": "系统将先确认身份，再识别语音命令",
            "identity": {"name": "", "score": None},
            "command": {"text": "", "status": "等待输入"},
            "arm": {"status": "idle"},
        }
        enrollment = {"name": "", "id": "", "samples": 0, "status": "idle", "message": "准备录入"}
        recognize = renderer.render("recognize", state, enrollment, "SA001", "现场用户")
        enroll = renderer.render("enroll", state, enrollment, "SA001", "现场用户")
        keyboard = renderer.render("enroll", state, enrollment, "SA001", "ALICE", editing_field="name")
        state["command"]["text"] = "抓取第一行第二个目标"
        long_command = renderer.render("recognize", state, enrollment, "SA001", "现场用户")
        users = renderer.render(
            "users",
            state,
            enrollment,
            "SA001",
            "现场用户",
            [{"id": "SA001", "name": "张同学", "registeredAt": "2026-10-27T03:00:00"}],
            "SA001",
            False,
        )
        self.assertEqual(recognize.size, (800, 480))
        self.assertEqual(enroll.size, (800, 480))
        self.assertEqual(keyboard.size, (800, 480))
        self.assertEqual(long_command.size, (800, 480))
        self.assertEqual(users.size, (800, 480))
        self.assertNotEqual(recognize.tobytes(), enroll.tobytes())
        self.assertNotEqual(enroll.tobytes(), users.tobytes())
        self.assertNotEqual(enroll.tobytes(), keyboard.tobytes())

    def test_native_keyboard_has_letters_digits_and_field_specific_separator(self):
        name_values = {value for value, _label, _box in keyboard_key_boxes("name")}
        id_values = {value for value, _label, _box in keyboard_key_boxes("id")}
        self.assertTrue(set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789").issubset(name_values))
        self.assertIn(" ", name_values)
        self.assertIn("-", id_values)
        self.assertNotIn(" ", id_values)
        self.assertEqual(keyboard_key_at(30, 215, "name"), "Q")
        self.assertEqual(keyboard_key_at(700, 420, "id"), "DONE")
        self.assertIsNone(keyboard_key_at(0, 0, "name"))


if __name__ == "__main__":
    unittest.main()
