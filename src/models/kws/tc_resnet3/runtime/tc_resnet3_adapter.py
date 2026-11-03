"""NumPy-only TC-ResNet3 adapter for the SonicArm integration runtime."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np


class TCResNet3PS:
    def __init__(self, model_dir: Path) -> None:
        self.root = Path(model_dir)
        self.weights = dict(np.load(self.root / "model_weights.npz", allow_pickle=False))
        self.cfg = json.loads((self.root / "preprocess_config.json").read_text(encoding="utf-8"))
        self.labels = json.loads((self.root / "label_map.json").read_text(encoding="utf-8"))
        self.decision = json.loads((self.root / "decision_config.json").read_text(encoding="utf-8"))

    def _features(self, waveform_16k: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
        x = np.asarray(waveform_16k, dtype=np.float32).reshape(-1)
        if not len(x) or not np.isfinite(x).all():
            raise ValueError("empty or invalid 16 kHz waveform")
        target = int(self.cfg["sample_rate"])
        frame_length = max(1, int(target * 0.02))
        frame_step = int(target * 0.01)
        frames = (
            np.lib.stride_tricks.sliding_window_view(x, frame_length)[::frame_step]
            if len(x) >= frame_length
            else x[None]
        )
        rms = np.sqrt(np.mean(frames * frames, axis=1))
        threshold = max(10 ** (-45 / 20), float(rms.max()) * 10 ** (-30 / 20))
        active = np.flatnonzero(rms > threshold)
        start = int(active[0] * frame_step) if len(active) else 0
        end = min(len(x), int(active[-1] * frame_step + frame_length)) if len(active) else 0
        detail: Dict[str, Any] = {
            "original_samples": int(len(x)),
            "active_start": start,
            "active_end": end,
            "active_duration_seconds": float((end - start) / target),
        }
        if end > start:
            margin = int(target * float(self.cfg.get("trim_margin_seconds", 0.05)))
            x = x[max(0, start - margin):min(len(x), end + margin)]
        model_samples = int(self.cfg["num_samples"])
        if len(x) > model_samples:
            raise ValueError("active audio exceeds the 5.2-second TC-ResNet3 model window")
        peak = float(np.abs(x).max())
        if peak > 1e-6:
            x = x * (float(self.cfg.get("peak_normalize", 0.8)) / peak)
        left = (model_samples - len(x)) // 2
        x = np.pad(x, (left, model_samples - len(x) - left)).astype(np.float32)
        detail.update(
            operation="active_trim_peak_normalize_center_pad",
            offset_samples=-left,
            model_samples=model_samples,
        )
        n_fft = int(self.cfg["n_fft"])
        hop = int(self.cfg["hop_length"])
        frames = np.lib.stride_tricks.sliding_window_view(x, n_fft)[::hop]
        fft = np.fft.rfft(frames * self.weights["frontend_window"][None], n=n_fft, axis=1)
        power = (fft.real ** 2 + fft.imag ** 2).astype(np.float32)
        mel = np.matmul(self.weights["frontend_filters"], power.T)
        feat = (np.log(np.maximum(mel, float(self.cfg["log_epsilon"]))) - float(self.cfg["mean"])) / float(self.cfg["std"])
        feat = feat.astype(np.float32)[None]
        expected = tuple(int(v) for v in self.cfg["feature_shape"])
        if feat.shape != expected:
            raise RuntimeError(f"unexpected TC-ResNet3 feature shape: {feat.shape}, expected {expected}")
        return feat, detail

    def _conv(self, x: np.ndarray, name: str, stride: int = 1, pad: int = 1) -> np.ndarray:
        weight = self.weights[name + ".weight"]
        padded = np.pad(x, ((0, 0), (0, 0), (pad, pad)))
        windows = np.lib.stride_tricks.sliding_window_view(padded, weight.shape[2], axis=2)[:, :, ::stride, :]
        return np.einsum("bctk,ock->bot", windows, weight, optimize=True).astype(np.float32)

    def _bn(self, x: np.ndarray, name: str) -> np.ndarray:
        scale = self.weights[name + ".weight"] / np.sqrt(self.weights[name + ".running_var"] + np.float32(1e-5))
        return ((x - self.weights[name + ".running_mean"][None, :, None]) * scale[None, :, None] + self.weights[name + ".bias"][None, :, None]).astype(np.float32)

    def _logits(self, x: np.ndarray) -> np.ndarray:
        x = np.maximum(self._bn(self._conv(x, "stem.0"), "stem.1"), 0)
        for index in range(3):
            prefix = f"blocks.{index}"
            stride = 1 if index == 0 else 2
            main = np.maximum(self._bn(self._conv(x, prefix + ".main.0", stride), prefix + ".main.1"), 0)
            main = self._bn(self._conv(main, prefix + ".main.3"), prefix + ".main.4")
            shortcut = x if index == 0 else self._bn(self._conv(x, prefix + ".shortcut.0", stride, pad=0), prefix + ".shortcut.1")
            x = np.maximum(main + shortcut, 0)
        length = x.shape[-1]
        pooled = np.stack([
            x[:, :, int(math.floor(i * length / 8)):int(math.ceil((i + 1) * length / 8))].mean(2)
            for i in range(8)
        ], axis=2)
        return pooled.reshape(len(x), -1) @ self.weights["fc.weight"].T + self.weights["fc.bias"]

    def recognize(self, waveform_16k: np.ndarray) -> Dict[str, Any]:
        features, detail = self._features(waveform_16k)
        logits = self._logits(features)[0]
        probabilities = np.exp(logits - logits.max())
        probabilities /= probabilities.sum()
        order = np.argsort(probabilities)[::-1]
        class_id = int(order[0])
        result = {
            "class_id": class_id,
            "class_name": self.labels[str(class_id)]["name"],
            "confidence": float(probabilities[class_id]),
            "probabilities": probabilities.tolist(),
            "logits": logits.tolist(),
            "top3": [
                {"class_id": int(i), "name": self.labels[str(int(i))]["name"], "score": float(probabilities[i])}
                for i in order[:3]
            ],
            "threshold": self.decision.get("threshold"),
            "execution_enabled": False,
            "execute": False,
            "preprocess": detail,
            "note": "TC-ResNet3 classification only; scores and threshold are not board-calibrated.",
        }
        return result
