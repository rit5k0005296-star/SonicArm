import threading
import unittest
from http.server import ThreadingHTTPServer

from ui.server import SonicArmHandler, configure_control_backend
from v9_core import get_json, post_json


class DummyControlBackend:
    def __init__(self):
        self.calls = []

    def status(self):
        return {"busy": False, "job": "idle", "last_error": ""}

    def list_users(self):
        return {"users": [{"id": "SA-002", "name": "张同学", "voiceprint": True, "registeredAt": "2026-10-23T00:00:00+00:00", "photo": ""}], "count": 1, "read_only": False}

    def delete_user(self, payload):
        self.calls.append(("delete", payload))
        return {"deleted": True, "id": payload["id"], "recoverable": True, "recycle_path": "data/deleted_users/test_SA-002"}

    def start_enrollment(self, payload):
        self.calls.append(("enrollment", payload))
        return {"accepted": True, "job": "enrollment", "status": "started"}

    def start_recognition(self, payload):
        self.calls.append(("recognition", payload))
        return {"accepted": True, "job": "recognition", "status": "started"}


class UIAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.backend = DummyControlBackend()
        configure_control_backend(cls.backend)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), SonicArmHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_health_and_dry_run_state(self):
        self.assertTrue(get_json(self.base_url, "/api/health")["ok"])
        state = post_json(
            self.base_url,
            "/api/state",
            {
                "phase": "matched",
                "mode": "V9集成验证（禁止动作）",
                "identity": {"score": 0.8, "threshold": 0.67, "threshold_calibrated": False},
                "command": {"text": "复位", "status": "验证模式：禁止执行"},
                "arm": {"step": "reset", "status": "dry_run", "message": "未打开串口", "completed_steps": []},
                "connections": {"arm_serial": False},
            },
        )
        self.assertEqual(state["arm"]["status"], "dry_run")
        self.assertFalse(state["connections"]["arm_serial"])

    def test_control_start_endpoints(self):
        enrollment = post_json(
            self.base_url,
            "/api/enrollment/start",
            {"name": "张同学", "id": "SA-002"},
        )
        recognition = post_json(self.base_url, "/api/recognition/start", {})
        status = get_json(self.base_url, "/api/control/status")
        self.assertTrue(enrollment["accepted"])
        self.assertTrue(recognition["accepted"])
        self.assertEqual(status["job"], "idle")

    def test_users_endpoint_reads_control_backend(self):
        payload = get_json(self.base_url, "/api/users")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["users"][0]["id"], "SA-002")
        self.assertFalse(payload["read_only"])

    def test_delete_user_endpoint_is_recoverable(self):
        payload = post_json(self.base_url, "/api/users/delete", {"id": "SA-002"})
        self.assertTrue(payload["deleted"])
        self.assertTrue(payload["recoverable"])
        self.assertEqual(self.backend.calls[-1], ("delete", {"id": "SA-002"}))


if __name__ == "__main__":
    unittest.main()
