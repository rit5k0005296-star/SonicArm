#!/usr/bin/env python3
"""Offline package audit; it does not import PYNQ or touch hardware."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    required = [
        "README.md",
        "DISPLAY_REQUIREMENTS.md",
        "config.json",
        "app.py",
        "board_runtime.py",
        "controller.py",
        "diagnose_audio_run.py",
        "BOARD_WEB_CONTROL_DEPLOY.md",
        "v9_core.py",
        "v9_audio.py",
        "run_validation.py",
        "V9_integration_validation.ipynb",
        "ui/server.py",
        "ui/web/auth.html",
        "ui/web/app.js",
        "ui/web/register.js",
        "ui/web/users.html",
        "ui/web/users.css",
        "ui/web/users.js",
        "tc_resnet3_ps/manifest.json",
        "tc_resnet3_ps/tc_resnet3_selftest.py",
        "tc_resnet3_ps/tc_resnet3_adapter.py",
        "tc_resnet3_ps/model_weights.npz",
    ]
    missing = [name for name in required if not (ROOT / name).is_file()]
    runtime_sources = (
        "app.py",
        "board_runtime.py",
        "controller.py",
        "v9_core.py",
        "run_validation.py",
        "ui/server.py",
    )
    sources = "\n".join((ROOT / name).read_text(encoding="utf-8") for name in runtime_sources)
    forbidden_patterns = [r"\bimport\s+serial\b", r"\bfrom\s+serial\b", r"/dev/tty(?:USB|ACM)"]
    forbidden_hits = [pattern for pattern in forbidden_patterns if re.search(pattern, sources)]
    kws_decision = json.loads((ROOT / "tc_resnet3_ps" / "decision_config.json").read_text(encoding="utf-8"))
    checks = {
        "required_files_present": not missing,
        "config_dry_run": config["decision"]["dry_run"] is True,
        "config_kws_execution_disabled": config["decision"]["kws_execution_enabled"] is False,
        "packaged_kws_execution_disabled": kws_decision["execution_enabled"] is False,
        "speech_window_matches_kws": float(config["audio"]["speech_seconds"]) == 4.0,
        "tc_resnet3_selected": config["paths"]["kws_dir"] == "tc_resnet3_ps",
        "tc_resnet3_package_threshold_unset": kws_decision["threshold"] is None,
        "quiet_reference_is_bounded": 0.0 < float(config["audio"]["quiet_reference_max_age_seconds"]) <= 300.0,
        "temporary_clip_limit_is_two_percent": float(config["audio"]["maximum_clip_percent"]) == 2.0,
        "no_serial_code": not forbidden_hits,
        "physical_display_final_required": config["display"]["final_required"] is True,
        "computer_browser_not_final_evidence": config["display"]["computer_browser_is_final_evidence"] is False,
        "physical_display_unverified": config["display"]["physical_display_verified"] is False,
    }
    files = []
    for path in sorted(ROOT.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.name != "package_manifest.json":
            files.append({
                "path": path.relative_to(ROOT).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            })
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "missing": missing,
        "forbidden_hits": forbidden_hits,
        "file_count": len(files),
        "files": files,
        "boundary": "offline package audit only; no PYNQ, Overlay, microphone, model inference, display, or arm validation",
    }
    (ROOT / "package_manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "checks", "file_count", "boundary")}, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
