"""Hardware-independent state and logging helpers for SonicArm V9 validation."""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def post_json(base_url: str, endpoint: str, payload: Dict[str, Any], timeout: float = 2.0) -> Dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        base_url.rstrip("/") + endpoint,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(base_url: str, endpoint: str, timeout: float = 2.0) -> Dict[str, Any]:
    with urllib.request.urlopen(base_url.rstrip("/") + endpoint, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(temporary), str(path))


def arm_step_for_label(label: str) -> str:
    if label.startswith("抓取") or label == "抓握":
        return "pickup"
    if label == "松开":
        return "place"
    if label == "复位":
        return "reset"
    return "none"


def decide(
    similarity: float,
    identity_threshold: float,
    kws_result: Optional[Dict[str, Any]],
    reject_labels: list[str],
) -> Dict[str, Any]:
    """Create a display decision. This function never authorizes arm execution."""
    identity_accepted = bool(similarity >= identity_threshold)
    if not identity_accepted:
        return {
            "phase": "denied",
            "identity_accepted": False,
            "command_accepted": False,
            "execute": False,
            "reason": "identity_below_uncalibrated_threshold",
            "arm_step": "none",
        }
    if kws_result is None:
        return {
            "phase": "matched",
            "identity_accepted": True,
            "command_accepted": False,
            "execute": False,
            "reason": "kws_not_run",
            "arm_step": "none",
        }
    label = str(kws_result["class_name"])
    confidence = float(kws_result["confidence"])
    threshold = float(kws_result["threshold"])
    command_accepted = label not in reject_labels and confidence >= threshold
    return {
        "phase": "matched",
        "identity_accepted": True,
        "command_accepted": command_accepted,
        "execute": False,
        "reason": "dry_run_action_blocked" if command_accepted else "kws_rejected",
        "arm_step": arm_step_for_label(label) if command_accepted else "none",
    }


def ui_payload(
    *,
    user_id: str,
    name: str,
    similarity: float,
    identity_threshold: float,
    threshold_calibrated: bool,
    kws_result: Optional[Dict[str, Any]],
    decision: Dict[str, Any],
    physical_display_verified: bool = False,
) -> Dict[str, Any]:
    command_text = "" if kws_result is None else str(kws_result["class_name"])
    if not decision["identity_accepted"]:
        headline = "身份未通过"
        command_status = "未执行短语识别"
    elif not decision["command_accepted"]:
        headline = "身份通过，命令被拒绝"
        command_status = "拒识/低于暂用阈值"
    else:
        headline = "身份与命令识别完成"
        command_status = "验证模式：禁止执行"
    return {
        "phase": decision["phase"],
        "mode": "V9集成验证（禁止动作）",
        "headline": headline,
        "message": "本轮仅验证声纹、短语和UI链路，不发送机械臂串口指令",
        "identity": {
            "id": user_id,
            "name": name,
            "score": float(similarity),
            "threshold": float(identity_threshold),
            "threshold_calibrated": bool(threshold_calibrated),
        },
        "command": {
            "text": command_text,
            "status": command_status,
            "accepted": bool(decision["command_accepted"]),
        },
        "arm": {
            "step": decision["arm_step"],
            "status": "dry_run",
            "message": "机械臂动作门禁关闭，未打开串口",
            "completed_steps": [],
        },
        "connections": {
            "microphone": True,
            "voiceprint": True,
            "arm_serial": False,
            "display": bool(physical_display_verified),
        },
    }
