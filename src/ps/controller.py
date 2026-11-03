"""Thread-safe web job controller for three-utterance enrollment and recognition."""
from __future__ import annotations

import json
import re
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

from v9_audio import AudioGateError, l2_normalize
from v9_core import atomic_write_json, decide, ui_payload, utc_now


SAFE_USER_ID = re.compile(r"^[A-Za-z0-9_-]{1,24}$")


class BusyError(RuntimeError):
    pass


class SonicArmController:
    def __init__(
        self, root: Path, config: Dict[str, Any], hardware: Any, state: Any, enrollment: Any,
        arm: Any = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.config = config
        self.hardware = hardware
        self.state = state
        self.enrollment = enrollment
        self.arm = arm
        self.users_dir = self.root / "data" / "users"
        self.deleted_users_dir = self.root / "data" / "deleted_users"
        self.results_dir = self.root / config["paths"]["results_dir"]
        self.users_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._busy = False
        self._job = "idle"
        self._last_error = ""
        self._quiet_reference: Optional[np.ndarray] = None
        self._quiet_reference_path: Optional[Path] = None
        self._quiet_reference_at = 0.0

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {"busy": self._busy, "job": self._job, "last_error": self._last_error}

    def list_users(self) -> Dict[str, Any]:
        users = []
        for metadata_path in sorted(self.users_dir.glob("*/profile.json")):
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                if not metadata_path.with_name("profile.npy").is_file():
                    continue
                users.append(
                    {
                        "id": str(metadata.get("id", metadata_path.parent.name)),
                        "name": str(metadata.get("name", "未命名用户")),
                        "voiceprint": True,
                        "registeredAt": str(metadata.get("created_at", "")),
                        "photo": "",
                    }
                )
            except (OSError, ValueError, TypeError):
                continue
        return {"users": users, "count": len(users), "read_only": False}

    def delete_user(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        user_id = str(payload.get("id", "")).strip()
        if not SAFE_USER_ID.fullmatch(user_id):
            raise ValueError("invalid user id")
        with self._lock:
            if self._busy:
                raise BusyError(f"{self._job} is running; user deletion is not allowed")
            user_dir = self.users_dir / user_id
            if not user_dir.is_dir():
                raise FileNotFoundError(f"user not found: {user_id}")
            metadata_path = user_dir / "profile.json"
            name = ""
            if metadata_path.is_file():
                try:
                    name = str(json.loads(metadata_path.read_text(encoding="utf-8")).get("name", ""))
                except (OSError, ValueError, TypeError):
                    pass
            self.deleted_users_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            recycle_dir = self.deleted_users_dir / f"{stamp}_{user_id}"
            user_dir.replace(recycle_dir)
        return {
            "deleted": True,
            "id": user_id,
            "name": name,
            "recoverable": True,
            "recycle_path": str(recycle_dir.relative_to(self.root)),
        }

    def _start(self, job: str, target: Any, *args: Any) -> Dict[str, Any]:
        with self._lock:
            if self._busy:
                raise BusyError(f"{self._job} is already running")
            self._busy = True
            self._job = job
            self._last_error = ""
        threading.Thread(target=self._run_guarded, args=(job, target, args), daemon=True).start()
        return {"accepted": True, "job": job, "status": "started"}

    def _run_guarded(self, job: str, target: Any, args: tuple[Any, ...]) -> None:
        try:
            target(*args)
        except BaseException as exc:
            message = f"{type(exc).__name__}: {exc}"
            with self._lock:
                self._last_error = message
            if job == "enrollment":
                self.enrollment.update({"status": "fault", "message": message})
            else:
                self.state.update(
                    {
                        "phase": "fault",
                        "headline": "识别失败",
                        "message": message,
                        "command": {"text": "", "status": "识别流程未完成"},
                        "arm": {"step": "none", "status": "idle", "message": "机械臂未启用，未发送指令"},
                    }
                )
        finally:
            with self._lock:
                self._busy = False
                self._job = "idle"

    def start_enrollment(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        user_id = str(payload.get("id", "")).strip()
        if not name or len(name) > 40:
            raise ValueError("name must contain 1-40 characters")
        if not SAFE_USER_ID.fullmatch(user_id):
            raise ValueError("id must contain only A-Z, a-z, 0-9, '_' or '-' and be 1-24 characters")
        return self._start("enrollment", self._enroll, name, user_id)

    def start_recognition(self, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        del payload
        if not list(self.users_dir.glob("*/profile.npy")):
            raise ValueError("no web-enrolled voiceprint profile; complete enrollment first")
        return self._start("recognition", self._recognize)

    def start_arm_reset(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if payload.get("confirm") is not True:
            raise ValueError("arm reset requires confirm=true")
        if self.arm is None:
            raise RuntimeError("arm integration is unavailable")
        utterance_id = f"manual-reset-{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        return self._start("arm_reset", self._arm_reset, utterance_id)

    def run_startup_arm_reset(self) -> Dict[str, Any]:
        """Synchronously reset the arm before the HTTP service accepts work."""
        if self.arm is None:
            raise RuntimeError("arm integration is unavailable")
        utterance_id = f"startup-reset-{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        self._arm_reset(utterance_id)
        return self.arm.status()

    def _arm_reset(self, utterance_id: str) -> None:
        self.state.update(
            {
                "phase": "executing",
                "headline": "机械臂复位中",
                "message": "已人工确认，正在等待机械臂动作完成",
                "arm": {"step": "reset", "status": "executing", "message": "禁止重复操作"},
            }
        )
        result = self.arm.dispatch(
            speaker_verified=True,
            asr_text="复位",
            utterance_id=utterance_id,
            reset_confirmed=True,
        )
        self.state.update(
            {
                "phase": "completed" if result["ok"] else "fault",
                "headline": "机械臂已复位" if result["ok"] else "机械臂复位失败",
                "message": result["reason"],
                "arm": {
                    "step": "reset",
                    "status": "complete" if result["ok"] else "fault",
                    "message": result["reason"],
                    "completed_steps": ["reset"] if result["ok"] else [],
                    "state": result["state"],
                },
            }
        )

    def _new_run_dir(self, prefix: str, suffix: str = "") -> Path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        run_dir = self.results_dir / f"{prefix}_{stamp}{suffix}"
        run_dir.mkdir(parents=True, exist_ok=False)
        return run_dir

    def _countdown(self, update: Any, message: str) -> None:
        for number in (3, 2, 1):
            update(f"{message}，{number}秒后开始")
            time.sleep(1.0)
        update(message)

    def _quiet_reference_is_fresh(self) -> bool:
        maximum_age = float(self.config["audio"].get("quiet_reference_max_age_seconds", 0.0))
        return (
            self._quiet_reference is not None
            and maximum_age > 0.0
            and time.monotonic() - self._quiet_reference_at <= maximum_age
        )

    def _capture_quiet_reference(self, run_dir: Path) -> np.ndarray:
        quiet = self.hardware.capture_quiet(run_dir)
        self._quiet_reference = np.array(quiet, copy=True)
        self._quiet_reference_path = run_dir / "quiet_raw24.wav"
        self._quiet_reference_at = time.monotonic()
        return quiet

    def _reuse_quiet_reference(self, run_dir: Path) -> Optional[np.ndarray]:
        if self._quiet_reference_is_fresh():
            target = run_dir / "quiet_raw24.wav"
            if self._quiet_reference_path is not None and self._quiet_reference_path.is_file():
                shutil.copy2(self._quiet_reference_path, target)
            return np.array(self._quiet_reference, copy=True)
        return None

    def _enroll(self, name: str, user_id: str) -> None:
        self.enrollment.reset()
        self.enrollment.update(
            {"name": name, "id": user_id, "samples": 0, "status": "recording", "message": "准备采集环境声"}
        )
        run_dir = self._new_run_dir("enroll", f"_{user_id}")
        self._countdown(
            lambda message: self.enrollment.update({"message": message}),
            "请保持安静，采集2秒环境声",
        )
        quiet = self._capture_quiet_reference(run_dir)
        embeddings = []
        records = []
        maximum_attempts = int(self.config["audio"].get("maximum_capture_attempts", 3))
        speech_seconds = float(self.config["audio"]["speech_seconds"])
        for index in range(1, 4):
            embedding = detail = None
            for attempt in range(1, maximum_attempts + 1):
                self._countdown(
                    lambda message: self.enrollment.update({"message": message}),
                    f"请录入第{index}/3段声纹并连续说话{speech_seconds:g}秒",
                )
                try:
                    embedding, _, detail = self.hardware.capture_embedding(
                        run_dir, f"enroll_{index}_try_{attempt}", quiet
                    )
                    break
                except AudioGateError as exc:
                    atomic_write_json(
                        run_dir / f"enroll_{index}_try_{attempt}_gate_failure.json",
                        {"sample": index, "attempt": attempt, "error": str(exc), "metrics": exc.metrics, "limits": exc.limits},
                    )
                    if attempt >= maximum_attempts:
                        raise RuntimeError(
                            f"第{index}/3段连续{maximum_attempts}次未通过：{exc}"
                        ) from exc
                    self.enrollment.update(
                        {
                            "status": "recording",
                            "message": f"第{index}/3段第{attempt}次未通过：{exc}；即将自动重录",
                        }
                    )
                    time.sleep(2.0)
            if embedding is None or detail is None:
                raise RuntimeError(f"第{index}/3段未生成有效声纹")
            embeddings.append(embedding)
            records.append(detail)
            self.enrollment.update(
                {
                    "samples": index,
                    "status": "recording" if index < 3 else "processing",
                    "message": f"第{index}/3段已录入" if index < 3 else "正在生成声纹模板",
                }
            )

        matrix = np.stack(embeddings).astype(np.float32)
        pairwise = matrix @ matrix.T
        pairwise_min = float(pairwise[np.triu_indices(3, k=1)].min())
        profile = l2_normalize(matrix.mean(axis=0)).astype(np.float32)
        user_dir = self.users_dir / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        profile_path = user_dir / "profile.npy"
        temporary = user_dir / "profile.npy.tmp"
        with temporary.open("wb") as stream:
            np.save(stream, profile, allow_pickle=False)
        temporary.replace(profile_path)
        metadata = {
            "schema_version": 1,
            "id": user_id,
            "name": name,
            "created_at": utc_now(),
            "utterance_count": 3,
            "embedding_dimension": 192,
            "pairwise_similarity": pairwise.tolist(),
            "pairwise_min": pairwise_min,
            "threshold_calibrated": False,
            "bit_sha256": self.config["expected_sha256"]["bit"],
            "hwh_sha256": self.config["expected_sha256"]["hwh"],
            "records": records,
        }
        atomic_write_json(user_dir / "profile.json", metadata)
        atomic_write_json(run_dir / "result.json", {**metadata, "profile": str(profile_path)})
        warning = "；三段一致性偏低，请考虑重新录入" if pairwise_min < float(self.config["decision"]["identity_threshold"]) else ""
        self.enrollment.update(
            {"samples": 3, "status": "complete", "message": f"声纹录入完成{warning}"}
        )

    def _load_profiles(self) -> list[Dict[str, Any]]:
        profiles = []
        for profile_path in sorted(self.users_dir.glob("*/profile.npy")):
            metadata_path = profile_path.with_name("profile.json")
            if not metadata_path.is_file():
                continue
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            vector = l2_normalize(np.load(profile_path, allow_pickle=False))
            if vector.shape != (192,):
                continue
            profiles.append({"vector": vector, "metadata": metadata})
        if not profiles:
            raise RuntimeError("no valid web-enrolled voiceprint profile")
        return profiles

    def _recognize(self) -> None:
        current = self.state.get()
        identity_threshold = float(current["identity"]["threshold"])
        self.state.update(
            {
                "phase": "listening",
                "mode": "SonicArm正式运行",
                "headline": "准备识别",
                "message": "请完成身份鉴权并说出机械臂指令",
                "identity": {"id": "", "name": "", "score": None},
                "command": {"text": "", "status": "等待输入"},
                "arm": {"step": "none", "status": "idle", "message": "机械臂等待指令", "completed_steps": []},
            }
        )
        run_dir = self._new_run_dir("recognize")
        quiet = self._reuse_quiet_reference(run_dir)
        if quiet is not None:
            self.state.update({"headline": "准备识别", "message": "已复用最近静音基线，本次无需再次采集静音"})
        else:
            self._countdown(
                lambda message: self.state.update({"headline": "准备识别", "message": message}),
                "请保持安静，采集2秒环境声",
            )
            quiet = self._capture_quiet_reference(run_dir)
        speech_seconds = float(self.config["audio"]["speech_seconds"])
        self._countdown(
            lambda message: self.state.update({"headline": "正在识别", "message": message}),
            f"请自然说出完整命令并持续发声{speech_seconds:g}秒",
        )
        embedding, waveform_16k, voiceprint_detail = self.hardware.capture_embedding(
            run_dir,
            "recognition",
            quiet,
            after_capture=lambda message: self.state.update(
                {"headline": "声音采集完毕", "message": message}
            ),
        )
        candidates = self._load_profiles()
        scored = [
            (float(item["vector"] @ embedding), item["metadata"]) for item in candidates
        ]
        similarity, metadata = max(scored, key=lambda item: item[0])
        kws_result = None
        if similarity >= identity_threshold:
            kws_result = self.hardware.recognize_command(waveform_16k)
        decision = decide(
            similarity,
            identity_threshold,
            kws_result,
            list(self.config["decision"]["reject_labels"]),
        )
        payload = ui_payload(
            user_id=str(metadata["id"]),
            name=str(metadata["name"]),
            similarity=similarity,
            identity_threshold=identity_threshold,
            threshold_calibrated=bool(self.config["decision"]["identity_threshold_calibrated"]),
            kws_result=kws_result,
            decision=decision,
            physical_display_verified=False,
        )
        if self.arm is not None:
            payload["mode"] = "SonicArm正式运行"
            payload["connections"]["arm_serial"] = bool(self.arm.connected)
            if not decision["command_accepted"]:
                payload["arm"] = {
                    "step": "none",
                    "status": "blocked",
                    "message": "身份或指令置信度未达到执行条件",
                    "completed_steps": [],
                    "state": self.arm.status()["state"],
                }
        arm_result = None
        if self.arm is not None and decision["identity_accepted"] and decision["command_accepted"]:
            voice_reset_enabled = bool(self.config.get("arm", {}).get("voice_reset_enabled", False))
            reset_confirmed = bool(
                voice_reset_enabled and str(kws_result["class_name"]).strip() == "复位"
            )
            arm_result = self.arm.dispatch(
                speaker_verified=True,
                asr_text=str(kws_result["class_name"]),
                utterance_id=run_dir.name,
                reset_confirmed=reset_confirmed,
            )
            payload["arm"] = {
                "step": decision["arm_step"],
                "status": "complete" if arm_result["ok"] else "blocked",
                "message": arm_result["reason"],
                "completed_steps": [decision["arm_step"]] if arm_result["ok"] else [],
                "state": arm_result["state"],
            }
            payload["connections"]["arm_serial"] = bool(self.arm.connected)
            payload["mode"] = "SonicArm正式运行"
            payload["message"] = arm_result["reason"]
        self.state.update(payload)
        result = {
            "schema_version": 1,
            "started_from": "web",
            "finished_at": utc_now(),
            "status": "passed",
            "voiceprint": {"similarity": similarity, "threshold": identity_threshold, **voiceprint_detail},
            "matched_user": metadata,
            "kws": {"status": "skipped_identity_denied"} if kws_result is None else kws_result,
            "decision": decision,
            "arm_dispatch": arm_result,
            "safety": {
                "dry_run": bool(self.config["decision"].get("dry_run", True)),
                "serial_opened": bool(self.arm is not None and self.arm.connected),
                "execute": bool(arm_result is not None and arm_result["ok"]),
            },
        }
        atomic_write_json(run_dir / "result.json", result)

