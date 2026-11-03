#!/usr/bin/env python3
"""Report per-channel gate metrics for an existing enrollment/recognition run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from v9_audio import channel_metrics, dbfs, read_pcm


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parent / "config.json")
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    config = json.loads(args.config.resolve().read_text(encoding="utf-8"))["audio"]
    quiet, quiet_rate = read_pcm(run_dir / "quiet_raw24.wav")
    if quiet_rate != 48000 or quiet.shape[1] != 2:
        raise RuntimeError(f"unexpected quiet recording: rate={quiet_rate}, shape={quiet.shape}")
    quiet_rms, quiet_peak, quiet_clip = channel_metrics(quiet)
    report = {
        "run_dir": str(run_dir),
        "limits": {
            "minimum_speech_over_quiet_db": float(config["minimum_speech_over_quiet_db"]),
            "minimum_speech_rms_dbfs": float(config["minimum_speech_rms_dbfs"]),
            "maximum_clip_percent": float(config["maximum_clip_percent"]),
        },
        "quiet": [
            {
                "channel": channel,
                "rms_dbfs": dbfs(quiet_rms[channel]),
                "peak_dbfs": dbfs(quiet_peak[channel]),
                "clip_percent": float(quiet_clip[channel]),
            }
            for channel in range(2)
        ],
        "speech": [],
    }
    for wav_path in sorted(run_dir.glob("*_raw24.wav")):
        if wav_path.name == "quiet_raw24.wav":
            continue
        speech, rate = read_pcm(wav_path)
        if rate != 48000 or speech.shape[1] != 2:
            report["speech"].append({"file": wav_path.name, "error": f"rate={rate}, shape={speech.shape}"})
            continue
        speech_rms, speech_peak, speech_clip = channel_metrics(speech)
        snr = 20.0 * np.log10(np.maximum(speech_rms, 1e-15) / np.maximum(quiet_rms, 1e-15))
        report["speech"].append(
            {
                "file": wav_path.name,
                "channels": [
                    {
                        "channel": channel,
                        "rms_dbfs": dbfs(speech_rms[channel]),
                        "peak_dbfs": dbfs(speech_peak[channel]),
                        "speech_over_quiet_db": float(snr[channel]),
                        "clip_percent": float(speech_clip[channel]),
                    }
                    for channel in range(2)
                ],
            }
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
