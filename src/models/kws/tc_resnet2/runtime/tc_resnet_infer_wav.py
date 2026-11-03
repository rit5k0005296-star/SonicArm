"""Recognition-only command line inference for a 16 kHz mono PCM16 WAV."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from tc_resnet_frontend_numpy import wav_feature
from tc_resnet_runtime_numpy import TCResNetNumpy, load_labels


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("wav", type=Path)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    feature, detail = wav_feature(args.wav)
    runtime = TCResNetNumpy()
    logits = runtime.forward(feature)
    probabilities = runtime.softmax(logits)
    class_id = int(np.argmax(probabilities))
    labels = load_labels()
    result = {
        "wav": str(args.wav.resolve()),
        "class_id": class_id,
        "class_name": labels[str(class_id)]["name"],
        "confidence": float(probabilities[class_id]),
        "execution_enabled": False,
        "execute": False,
        "preprocess": detail,
        "note": "仅验证短语识别，不发送机械臂命令。",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
