"""Recognition-only adapter for a 16 kHz waveform produced by the V8 notebook."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from tc_resnet_frontend_numpy import waveform_feature
from tc_resnet_runtime_numpy import TCResNetNumpy, load_labels


class V8PSKWS:
    def __init__(self, root=None):
        self.root = Path(root or Path(__file__).resolve().parent)
        self.runtime = TCResNetNumpy(self.root / "tc_resnet_model_fp32.npz")
        self.labels = load_labels(self.root / "label_map.json")
        self.decision = json.loads((self.root / "decision_config.json").read_text(encoding="utf-8"))

    def recognize(self, waveform_16k):
        feature, detail = waveform_feature(waveform_16k)
        logits = self.runtime.forward(feature)
        probabilities = self.runtime.softmax(logits)
        class_id = int(np.argmax(probabilities))
        confidence = float(probabilities[class_id])
        return {
            "class_id": class_id,
            "class_name": self.labels[str(class_id)]["name"],
            "confidence": confidence,
            "threshold": float(self.decision["threshold"]),
            "execution_enabled": False,
            "execute": False,
            "reason": "recognition_only_validation_gate_disabled",
            "preprocess": detail,
            "note": "Softmax分数不是实际正确概率；本适配器不含任何机械臂控制。",
        }
