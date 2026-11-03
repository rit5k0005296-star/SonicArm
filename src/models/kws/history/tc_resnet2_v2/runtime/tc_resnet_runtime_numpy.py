"""NumPy-only TC-ResNet inference for the PYNQ PS. No hardware-control code."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np


def _conv1d(x, weight, bias, stride=1, padding=0):
    x = np.asarray(x, dtype=np.float32)
    if padding:
        x = np.pad(x, ((0, 0), (padding, padding)))
    kernel = int(weight.shape[2])
    windows = np.lib.stride_tricks.sliding_window_view(x, kernel, axis=1)[:, ::stride, :]
    return np.einsum("ock,ctk->ot", weight, windows, optimize=True).astype(np.float32) + bias[:, None]


def _relu(x):
    return np.maximum(x, np.float32(0.0))


def _adaptive_avg_pool1d(x, bins=8):
    length = x.shape[1]
    pooled = []
    for index in range(bins):
        start = (index * length) // bins
        end = ((index + 1) * length + bins - 1) // bins
        pooled.append(x[:, start:end].mean(axis=1, dtype=np.float32))
    return np.stack(pooled, axis=1)


class TCResNetNumpy:
    def __init__(self, weights_path=None):
        here = Path(__file__).resolve().parent
        self.weights_path = Path(weights_path or here / "tc_resnet_model_fp32.npz")
        with np.load(self.weights_path, allow_pickle=False) as archive:
            self.w = {name: archive[name].astype(np.float32, copy=True) for name in archive.files}

    def _block(self, x, index, stride):
        main = _relu(_conv1d(x, self.w[f"b{index}_c1_w"], self.w[f"b{index}_c1_b"], stride, 1))
        main = _conv1d(main, self.w[f"b{index}_c2_w"], self.w[f"b{index}_c2_b"], 1, 1)
        if f"b{index}_skip_w" in self.w:
            skip = _conv1d(x, self.w[f"b{index}_skip_w"], self.w[f"b{index}_skip_b"], stride, 0)
        else:
            skip = x
        return _relu(main + skip)

    def forward(self, feature):
        x = np.asarray(feature, dtype=np.float32)
        if x.shape == (1, 40, 398):
            x = x[0]
        if x.shape != (40, 398):
            raise ValueError(f"expected [1,40,398] or [40,398], got {x.shape}")
        x = _relu(_conv1d(x, self.w["stem_w"], self.w["stem_b"], 1, 1))
        x = self._block(x, 0, 1)
        x = self._block(x, 1, 2)
        x = self._block(x, 2, 2)
        flat = _adaptive_avg_pool1d(x, 8).reshape(-1)
        return (self.w["fc_w"] @ flat + self.w["fc_b"]).astype(np.float32)

    @staticmethod
    def softmax(logits):
        z = np.asarray(logits, dtype=np.float32)
        exp = np.exp(z - np.max(z)).astype(np.float32)
        return exp / exp.sum(dtype=np.float32)


def load_labels(path=None):
    path = Path(path or Path(__file__).resolve().parent / "label_map.json")
    return json.loads(path.read_text(encoding="utf-8"))
