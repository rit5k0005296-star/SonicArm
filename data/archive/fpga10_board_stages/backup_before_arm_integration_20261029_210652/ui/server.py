#!/usr/bin/env python3
"""SonicArm UI local server.

The server uses only Python's standard library so it can run on a PYNQ image
without installing Flask or other packages.
"""

from __future__ import annotations

import argparse
import copy
import json
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional


BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
MAX_BODY_BYTES = 64 * 1024
ALLOWED_PHASES = {
    "idle",
    "listening",
    "matched",
    "denied",
    "executing",
    "completed",
    "fault",
}
ALLOWED_ARM_STEPS = {"none", "pickup", "place", "reset"}
ALLOWED_ENROLLMENT_STATUSES = {"idle", "recording", "processing", "complete", "fault"}


DEFAULT_STATE: Dict[str, Any] = {
    "revision": 0,
    "phase": "idle",
    "mode": "联调模式",
    "headline": "请说出指令",
    "message": "系统将先确认身份，再识别语音命令",
    "identity": {
        "id": "",
        "name": "",
        "photo": "",
        "score": None,
        "threshold": 0.67,
        "threshold_calibrated": False,
    },
    "command": {
        "text": "",
        "status": "等待输入",
    },
    "arm": {
        "step": "none",
        "status": "idle",
        "message": "机械臂等待任务",
        "completed_steps": [],
    },
    "connections": {
        "microphone": True,
        "voiceprint": True,
        "arm_serial": True,
        "display": True,
    },
    "updated_at": "",
}

DEFAULT_ENROLLMENT: Dict[str, Any] = {
    "revision": 0,
    "name": "",
    "id": "",
    "samples": 0,
    "required_samples": 3,
    "status": "idle",
    "message": "填写人员信息后开始录入",
    "updated_at": "",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def deep_merge(target: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            deep_merge(target[key], value)
        else:
            target[key] = value
    return target


def validate_patch(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object")

    if "phase" in payload and payload["phase"] not in ALLOWED_PHASES:
        raise ValueError("unsupported phase")

    identity = payload.get("identity")
    if identity is not None:
        if not isinstance(identity, dict):
            raise ValueError("identity must be an object")
        score = identity.get("score")
        threshold = identity.get("threshold")
        if score is not None and (not isinstance(score, (int, float)) or not 0 <= score <= 1):
            raise ValueError("identity.score must be between 0 and 1")
        if threshold is not None and (
            not isinstance(threshold, (int, float)) or not 0 <= threshold <= 1
        ):
            raise ValueError("identity.threshold must be between 0 and 1")

    arm = payload.get("arm")
    if arm is not None:
        if not isinstance(arm, dict):
            raise ValueError("arm must be an object")
        if "step" in arm and arm["step"] not in ALLOWED_ARM_STEPS:
            raise ValueError("unsupported arm.step")
        completed = arm.get("completed_steps")
        if completed is not None:
            if not isinstance(completed, list) or any(step not in ALLOWED_ARM_STEPS for step in completed):
                raise ValueError("arm.completed_steps contains an unsupported step")

    return payload


def validate_enrollment_patch(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object")

    allowed_keys = {"name", "id", "samples", "status", "message"}
    if any(key not in allowed_keys for key in payload):
        raise ValueError("unsupported enrollment field")

    for key in ("name", "id", "message"):
        value = payload.get(key)
        if value is not None and (not isinstance(value, str) or len(value) > 120):
            raise ValueError(f"enrollment.{key} must be a short string")

    samples = payload.get("samples")
    if samples is not None and (not isinstance(samples, int) or isinstance(samples, bool) or not 0 <= samples <= 3):
        raise ValueError("enrollment.samples must be an integer between 0 and 3")

    status = payload.get("status")
    if status is not None and status not in ALLOWED_ENROLLMENT_STATUSES:
        raise ValueError("unsupported enrollment.status")

    return payload


class StateStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = copy.deepcopy(DEFAULT_STATE)
        self._state["updated_at"] = utc_now()

    def get(self) -> Dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._state)

    def update(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            deep_merge(self._state, patch)
            self._state["revision"] += 1
            self._state["updated_at"] = utc_now()
            return copy.deepcopy(self._state)

    def reset(self) -> Dict[str, Any]:
        with self._lock:
            revision = self._state["revision"] + 1
            self._state = copy.deepcopy(DEFAULT_STATE)
            self._state["revision"] = revision
            self._state["updated_at"] = utc_now()
            return copy.deepcopy(self._state)


class EnrollmentStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = copy.deepcopy(DEFAULT_ENROLLMENT)
        self._state["updated_at"] = utc_now()

    def get(self) -> Dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._state)

    def update(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            self._state.update(patch)
            self._state["revision"] += 1
            self._state["updated_at"] = utc_now()
            return copy.deepcopy(self._state)

    def reset(self) -> Dict[str, Any]:
        with self._lock:
            revision = self._state["revision"] + 1
            self._state = copy.deepcopy(DEFAULT_ENROLLMENT)
            self._state["revision"] = revision
            self._state["updated_at"] = utc_now()
            return copy.deepcopy(self._state)

STATE = StateStore()
ENROLLMENT = EnrollmentStore()
CONTROL_BACKEND: Optional[Any] = None


def configure_control_backend(backend: Any) -> None:
    """Attach the one process that owns audio, Overlay and model execution."""
    global CONTROL_BACKEND
    CONTROL_BACKEND = backend


class SonicArmHandler(SimpleHTTPRequestHandler):
    server_version = "SonicArmUI/1.0"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def _send_json(self, payload: Dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> Dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length <= 0 or length > MAX_BODY_BYTES:
            raise ValueError("request body size is invalid")
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("request body is not valid UTF-8 JSON") from exc

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/api/state":
            self._send_json(STATE.get())
            return
        if path == "/api/health":
            self._send_json({"ok": True, "service": "sonicarm-ui", "time": utc_now()})
            return
        if path == "/api/enrollment":
            self._send_json(ENROLLMENT.get())
            return
        if path == "/api/users":
            if CONTROL_BACKEND is None:
                self._send_json({"users": [], "count": 0, "read_only": True, "error": "control backend is not running"}, HTTPStatus.SERVICE_UNAVAILABLE)
            else:
                self._send_json(CONTROL_BACKEND.list_users())
            return
        if path == "/api/control/status":
            if CONTROL_BACKEND is None:
                self._send_json({"busy": False, "job": "unavailable", "error": "control backend is not running"}, HTTPStatus.SERVICE_UNAVAILABLE)
            else:
                self._send_json(CONTROL_BACKEND.status())
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path not in {
            "/api/state",
            "/api/reset",
            "/api/enrollment",
            "/api/enrollment/reset",
            "/api/enrollment/start",
            "/api/recognition/start",
            "/api/users/delete",
        }:
            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            if path in {"/api/enrollment/start", "/api/recognition/start", "/api/users/delete"}:
                if CONTROL_BACKEND is None:
                    self._send_json({"error": "control backend is not running; start app.py"}, HTTPStatus.SERVICE_UNAVAILABLE)
                    return
                payload = self._read_json()
                if path == "/api/users/delete":
                    state = CONTROL_BACKEND.delete_user(payload)
                elif path == "/api/enrollment/start":
                    state = CONTROL_BACKEND.start_enrollment(payload)
                else:
                    state = CONTROL_BACKEND.start_recognition(payload)
                self._send_json(
                    state,
                    HTTPStatus.OK if path == "/api/users/delete" else HTTPStatus.ACCEPTED,
                )
                return
            if path == "/api/reset":
                state = STATE.reset()
            elif path == "/api/enrollment/reset":
                state = ENROLLMENT.reset()
            elif path == "/api/enrollment":
                state = ENROLLMENT.update(validate_enrollment_patch(self._read_json()))
            else:
                state = STATE.update(validate_patch(self._read_json()))
        except ValueError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        except RuntimeError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.CONFLICT)
            return
        except FileNotFoundError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
            return
        self._send_json(state)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the SonicArm identity UI")
    parser.add_argument("--host", default="127.0.0.1", help="listen address")
    parser.add_argument("--port", default=8080, type=int, help="listen port")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    server = ThreadingHTTPServer((args.host, args.port), SonicArmHandler)
    print(f"SonicArm UI: http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
