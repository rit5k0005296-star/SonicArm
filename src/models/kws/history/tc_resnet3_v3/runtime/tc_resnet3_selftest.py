#!/usr/bin/env python3
"""Offline TC-ResNet3 package smoke test; does not access PYNQ hardware."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from tc_resnet3_adapter import TCResNet3PS


ROOT = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    source_hashes = json.loads((ROOT / "SHA256.json").read_text(encoding="utf-8"))
    checked = ("model_weights.npz", "preprocess_config.json", "label_map.json", "decision_config.json")
    hashes_ok = all(sha256(ROOT / name) == source_hashes[name] for name in checked)
    model = TCResNet3PS(ROOT)
    time_axis = np.arange(64000, dtype=np.float32) / np.float32(16000.0)
    waveform = (0.2 * np.sin(2 * np.pi * 440.0 * time_axis)).astype(np.float32)
    first = model.recognize(waveform)
    second = model.recognize(waveform)
    checks = {
        "source_hashes_match": hashes_ok,
        "class_count_is_15": len(first["probabilities"]) == 15,
        "feature_operation_is_expected": first["preprocess"]["operation"] == "active_trim_peak_normalize_center_pad",
        "four_second_capture_is_padded_to_83200": first["preprocess"]["model_samples"] == 83200,
        "finite_probabilities": bool(np.isfinite(first["probabilities"]).all()),
        "probabilities_sum_to_one": abs(sum(first["probabilities"]) - 1.0) < 1e-5,
        "deterministic": np.array_equal(np.asarray(first["logits"]), np.asarray(second["logits"])),
        "execution_disabled": first["execution_enabled"] is False and first["execute"] is False,
        "package_threshold_is_unset": first["threshold"] is None,
    }
    report = {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "classification": {key: first[key] for key in ("class_id", "class_name", "confidence")},
        "boundary": "offline NumPy smoke test only; not real-audio accuracy or PYNQ ARM validation",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
