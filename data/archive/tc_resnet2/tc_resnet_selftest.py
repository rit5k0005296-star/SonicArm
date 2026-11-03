"""Offline/board self-test for package integrity and fixed-vector inference."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from tc_resnet_frontend_numpy import LogMelNumpy, align_audio
from tc_resnet_runtime_numpy import TCResNetNumpy


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    here = Path(__file__).resolve().parent
    manifest = json.loads((here / "manifest.json").read_text(encoding="utf-8"))
    mismatches = []
    for entry in manifest["files"]:
        path = here / entry["name"]
        if not path.is_file() or sha256(path) != entry["sha256"]:
            mismatches.append(entry["name"])
    if mismatches:
        raise RuntimeError("文件哈希不匹配: " + ", ".join(mismatches))

    with np.load(here / "selftest_vectors.npz", allow_pickle=False) as test:
        runtime = TCResNetNumpy()
        actual_logits = np.stack([runtime.forward(x) for x in test["features"]])
        logit_error = float(np.max(np.abs(actual_logits - test["expected_logits"])))
        frontend = LogMelNumpy()
        aligned, _ = align_audio(test["audio"], frontend.cfg)
        actual_feature = frontend(aligned)
        feature_error = float(np.max(np.abs(actual_feature - test["expected_feature"])))
    if logit_error > 2e-4 or feature_error > 2e-4:
        raise AssertionError({"logit_error": logit_error, "feature_error": feature_error})
    print(json.dumps({
        "status": "passed",
        "max_abs_logit_error": logit_error,
        "max_abs_frontend_error": feature_error,
        "execution_enabled": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
