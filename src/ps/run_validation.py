#!/usr/bin/env python3
"""Run one live V8 voiceprint + PS TC-ResNet3 + UI validation cycle."""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import platform
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from v9_audio import analyze_and_select, cam_features, l2_normalize, read_pcm, resample_48k_to_16k, save_pcm16
from v9_core import atomic_write_json, decide, get_json, post_json, ui_payload, utc_now


ROOT = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_local(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def countdown(message: str) -> None:
    print(message, flush=True)
    for number in (3, 2, 1):
        print(number, flush=True)
        time.sleep(1.0)
    print("开始", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    parser.add_argument("--name", default="测试用户")
    parser.add_argument("--user-id", default="SA-TEST")
    parser.add_argument("--no-ui", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config.resolve())
    if platform.system() != "Linux" or platform.machine().lower() not in ("armv7l", "armv8l", "aarch64"):
        raise RuntimeError("live validation must run on PYNQ ARM Linux")
    if not config["decision"]["dry_run"] or config["decision"]["kws_execution_enabled"]:
        raise RuntimeError("V9 phase-1 safety gate must remain dry-run with execution disabled")

    v8_dir = Path(config["paths"]["v8_dir"])
    bit = v8_dir / config["paths"]["bit"]
    hwh = v8_dir / config["paths"]["hwh"]
    profile_path = v8_dir / config["paths"]["voiceprint_profile"]
    constants = Path(config["paths"]["frontend_constants"])
    kws_dir = resolve_local(ROOT, config["paths"]["kws_dir"])
    required = [bit, hwh, profile_path, constants, v8_dir / config["paths"]["voiceprint_runtime"], kws_dir / "manifest.json"]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing required files: " + ", ".join(missing))
    if sha256(bit) != config["expected_sha256"]["bit"] or sha256(hwh) != config["expected_sha256"]["hwh"]:
        raise RuntimeError("V8 bit/HWH identity mismatch")

    ui_config = config["ui"]
    use_ui = not args.no_ui
    if use_ui:
        health = get_json(ui_config["base_url"], "/api/health", float(ui_config["timeout_seconds"]))
        if not health.get("ok"):
            raise RuntimeError("UI health check failed")
        post_json(ui_config["base_url"], "/api/reset", {}, float(ui_config["timeout_seconds"]))
        post_json(
            ui_config["base_url"],
            "/api/state",
            {"phase": "listening", "mode": "V9集成验证（禁止动作）", "headline": "准备录音", "message": "机械臂串口未启用"},
            float(ui_config["timeout_seconds"]),
        )

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = resolve_local(ROOT, config["paths"]["results_dir"]) / f"run_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    result_path = run_dir / "result.json"
    result = {
        "schema_version": 1,
        "run_id": run_id,
        "started_at": utc_now(),
        "status": "running",
        "validation_level": "ps_preintegration",
        "final_system_passed": False,
        "safety": {"dry_run": True, "serial_opened": False, "execute": False},
        "artifacts": {"bit_sha256": sha256(bit), "hwh_sha256": sha256(hwh)},
    }
    atomic_write_json(result_path, result)

    audio = runtime = None
    try:
        sys.path.insert(0, str(v8_dir))
        v8_module = importlib.import_module("v8_runtime")
        sys.path.insert(0, str(kws_dir))
        kws_module = importlib.import_module("tc_resnet3_adapter")
        from pynq import Clocks, Overlay

        overlay = Overlay(str(bit), download=True)
        if not hasattr(overlay, "audio_codec_ctrl_0") or not hasattr(overlay, "unified_0"):
            raise RuntimeError("overlay lacks audio_codec_ctrl_0 or unified_0")
        if abs(float(Clocks.fclk0_mhz) - float(config["target"]["pl_clock_mhz"])) > 0.1:
            raise RuntimeError(f"unexpected FCLK0: {Clocks.fclk0_mhz}")
        audio = overlay.audio_codec_ctrl_0
        audio.configure(sample_rate=48000, iic_index=1, uio_name="audio-codec-ctrl")
        audio.deselect_inputs()
        time.sleep(0.25)
        audio.select_microphone()
        time.sleep(0.75)
        runtime = v8_module.Runtime(debug=False, capacity=529, overlay=overlay, hwh_path=hwh)

        countdown("请保持安静，准备采集2秒环境基线")
        quiet_raw = run_dir / "quiet_raw24.wav"
        audio.record(float(config["audio"]["quiet_seconds"]))
        audio.save(str(quiet_raw))
        quiet, quiet_rate = read_pcm(quiet_raw)
        countdown(f"请自然说出完整命令并持续发声，准备采集{float(config['audio']['speech_seconds']):g}秒测试语音")
        speech_raw = run_dir / "speech_raw24.wav"
        audio.record(float(config["audio"]["speech_seconds"]))
        audio.save(str(speech_raw))
        speech, speech_rate = read_pcm(speech_raw)
        if quiet_rate != 48000 or speech_rate != 48000 or quiet.shape[1] != 2 or speech.shape[1] != 2:
            raise RuntimeError("unexpected codec recording format")

        channel, gate = analyze_and_select(quiet, speech, config["audio"])
        waveform_16k = resample_48k_to_16k(speech[:, channel])
        model_wav = run_dir / "shared_16k_mono.wav"
        save_pcm16(model_wav, waveform_16k)
        features = cam_features(waveform_16k, constants)
        if features.shape[1] > 529:
            raise RuntimeError(f"CAM++ feature frames exceed V8 capacity: {features.shape}")

        started = time.perf_counter()
        raw_embedding, voiceprint_report = runtime.run(features, audit=False)
        voiceprint_ms = (time.perf_counter() - started) * 1000.0
        actual_calls = voiceprint_report.get("actual_v8_ap_start")
        if actual_calls != {"pointwise": 55, "FCM": 12}:
            raise RuntimeError(f"unexpected V8 accelerator calls: {actual_calls}")
        embedding = l2_normalize(raw_embedding)
        profile = l2_normalize(np.load(profile_path, allow_pickle=False))
        if embedding.shape != (192,) or profile.shape != (192,):
            raise RuntimeError("voiceprint embedding/profile must both have 192 values")
        similarity = float(profile @ embedding)
        identity_threshold = float(config["decision"]["identity_threshold"])

        kws_result = None
        kws_ms = None
        if similarity >= identity_threshold:
            kws = kws_module.TCResNet3PS(kws_dir)
            started = time.perf_counter()
            kws_result = kws.recognize(waveform_16k)
            kws_ms = (time.perf_counter() - started) * 1000.0
            package_threshold = kws_result.get("threshold")
            kws_result["package_threshold"] = None if package_threshold is None else float(package_threshold)
            kws_result["threshold"] = float(config["decision"]["kws_threshold"])
            kws_result["threshold_calibrated"] = bool(config["decision"]["kws_threshold_calibrated"])
            if kws_result.get("execution_enabled") or kws_result.get("execute"):
                raise RuntimeError("KWS adapter unexpectedly enabled execution")

        decision = decide(
            similarity,
            identity_threshold,
            kws_result,
            list(config["decision"]["reject_labels"]),
        )
        payload = ui_payload(
            user_id=args.user_id,
            name=args.name,
            similarity=similarity,
            identity_threshold=identity_threshold,
            threshold_calibrated=bool(config["decision"]["identity_threshold_calibrated"]),
            kws_result=kws_result,
            decision=decision,
            physical_display_verified=bool(config["display"]["physical_display_verified"]),
        )
        if use_ui:
            post_json(ui_config["base_url"], "/api/state", payload, float(ui_config["timeout_seconds"]))

        result.update(
            {
                "finished_at": utc_now(),
                "status": "passed",
                "audio": {"shared_wav": str(model_wav), "gate": gate},
                "voiceprint": {
                    "similarity": similarity,
                    "threshold": identity_threshold,
                    "threshold_calibrated": bool(config["decision"]["identity_threshold_calibrated"]),
                    "accepted": bool(similarity >= identity_threshold),
                    "inference_ms": voiceprint_ms,
                    "actual_v8_ap_start": actual_calls,
                },
                "kws": {"status": "skipped_identity_denied"} if kws_result is None else {**kws_result, "inference_ms": kws_ms},
                "decision": decision,
                "ui": {"updated": use_ui, "payload": payload},
                "display": {
                    "final_required": bool(config["display"]["final_required"]),
                    "physical_display_verified": False,
                    "computer_browser_is_final_evidence": False,
                    "status": "pending_fpga9_hdmi_vdma_and_usb_hid_validation"
                },
            }
        )
        atomic_write_json(result_path, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except BaseException as exc:
        result.update({"finished_at": utc_now(), "status": "failed", "error": f"{type(exc).__name__}: {exc}"})
        atomic_write_json(result_path, result)
        if use_ui:
            try:
                post_json(
                    ui_config["base_url"],
                    "/api/state",
                    {"phase": "fault", "headline": "V9集成验证失败", "message": str(exc), "arm": {"step": "none", "status": "fault", "message": "未发送机械臂指令"}},
                    float(ui_config["timeout_seconds"]),
                )
            except Exception:
                pass
        raise
    finally:
        if runtime is not None:
            runtime.close()
        if audio is not None:
            audio.deselect_inputs()


if __name__ == "__main__":
    raise SystemExit(main())
