
from __future__ import annotations

import importlib.util
import threading
from pathlib import Path
from typing import Any, Dict, Optional


PICK_COMMANDS = {
    "从第一行第一列夹取": (1, 1),
    "从第一行第二列夹取": (1, 2),
    "从第二行第一列夹取": (2, 1),
    "从第二行第二列夹取": (2, 2),
}
VOICE_COMMANDS = set(PICK_COMMANDS) | {"松开", "复位"}

# TC-ResNet3 was trained with labels different from the arm-controller handoff wording.
# Only the four physically available grid cells and the two handoff commands map.
KWS_TO_ARM_COMMAND = {
    "抓取第一行第一列": "从第一行第一列夹取",
    "抓取第一行第二列": "从第一行第二列夹取",
    "抓取第二行第一列": "从第二行第一列夹取",
    "抓取第二行第二列": "从第二行第二列夹取",
    "松开": "松开",
    "复位": "复位",
}


def normalize_command(text: Any) -> str:
    return (
        str(text)
        .strip()
        .replace(" ", "")
        .replace("，", "")
        .replace("。", "")
        .replace("！", "")
    )


def canonical_arm_command(kws_label: Any) -> Optional[str]:
    return KWS_TO_ARM_COMMAND.get(normalize_command(kws_label))


class VerifiedArmBackend:
    """Load the already-tested board module without changing its protocol."""

    def __init__(self, module_path: Path) -> None:
        self.module_path = Path(module_path).resolve()
        if not self.module_path.is_file():
            raise FileNotFoundError(f"verified arm module not found: {self.module_path}")
        spec = importlib.util.spec_from_file_location("sonicarm_verified_arm_backend", self.module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load verified arm module: {self.module_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for name in ("arm_pick", "arm_place_right", "arm_reset_upright"):
            if not callable(getattr(module, name, None)):
                raise AttributeError(f"verified arm module must define {name}()")
        self.module = module

    def initialize(self) -> None:
        initialize = getattr(self.module, "initialize_arm", None)
        if callable(initialize):
            initialize()

    def close(self) -> None:
        close = getattr(self.module, "close_arm", None)
        if callable(close):
            close()

    def pick(self, row: int, col: int) -> bool:
        return bool(self.module.arm_pick(row, col))

    def place_right(self) -> bool:
        return bool(self.module.arm_place_right())

    def reset_upright(self) -> bool:
        return bool(self.module.arm_reset_upright())


class ArmDispatcher:
    """Single-flight state machine; failures enter FAULT and are never retried."""

    def __init__(self, backend: Optional[Any] = None, enabled: bool = False) -> None:
        self.backend = backend
        self.enabled = bool(enabled)
        self.state = "UNKNOWN"
        self.last_utterance_id: Optional[str] = None
        self.last_error = ""
        self._lock = threading.Lock()
        self._executing = False

    @property
    def connected(self) -> bool:
        return self.backend is not None

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.enabled,
                "connected": self.connected,
                "state": self.state,
                "executing": self._executing,
                "last_error": self.last_error,
            }

    def dispatch(
        self,
        speaker_verified: bool,
        asr_text: Any,
        utterance_id: Any,
        *,
        reset_confirmed: bool = False,
    ) -> Dict[str, Any]:
        command = canonical_arm_command(asr_text)
        uid = str(utterance_id) if utterance_id is not None else ""
        with self._lock:
            if speaker_verified is not True:
                return self._result(False, command, "identity_rejected")
            if command not in VOICE_COMMANDS:
                return self._result(False, command, "command_not_whitelisted")
            if not uid:
                return self._result(False, command, "utterance_id_required")
            if uid == self.last_utterance_id:
                return self._result(False, command, "duplicate_utterance")
            if not self.enabled:
                return self._result(False, command, "execution_disabled")
            if self.backend is None:
                return self._result(False, command, "backend_unavailable")
            if self._executing:
                return self._result(False, command, "arm_busy")
            if self.state == "FAULT" and command != "复位":
                return self._result(False, command, "arm_fault_requires_reset")
            if command in PICK_COMMANDS and self.state != "READY":
                return self._result(False, command, "pick_requires_ready")
            if command == "松开" and self.state != "GRIPPED":
                return self._result(False, command, "place_requires_gripped")
            if command == "复位" and not reset_confirmed:
                return self._result(False, command, "reset_requires_confirmation")
            # Consume before motion so a repeated callback cannot trigger twice.
            self.last_utterance_id = uid
            self._executing = True

        try:
            if command in PICK_COMMANDS:
                ok = self.backend.pick(*PICK_COMMANDS[command])
                next_state = "GRIPPED"
            elif command == "松开":
                ok = self.backend.place_right()
                next_state = "PLACED"
            else:
                ok = self.backend.reset_upright()
                next_state = "READY"
            with self._lock:
                if ok:
                    self.state = next_state
                    self.last_error = ""
                    return self._result(True, command, "completed")
                self.state = "FAULT"
                self.last_error = "verified arm backend returned False"
                return self._result(False, command, "backend_failed")
        except BaseException as exc:
            with self._lock:
                self.state = "FAULT"
                self.last_error = f"{type(exc).__name__}: {exc}"
                return self._result(False, command, "backend_exception")
        finally:
            with self._lock:
                self._executing = False

    def _result(self, ok: bool, command: Optional[str], reason: str) -> Dict[str, Any]:
        return {
            "ok": bool(ok),
            "command": command or "",
            "reason": reason,
            "state": self.state,
            "executed": bool(ok),
        }

