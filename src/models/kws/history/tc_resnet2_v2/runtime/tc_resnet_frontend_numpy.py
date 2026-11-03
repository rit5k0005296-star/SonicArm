"""NumPy-only 16 kHz waveform alignment and Log-Mel frontend."""
from __future__ import annotations

import json
import math
import wave
from pathlib import Path

import numpy as np


def active_bounds(x, sample_rate):
    size = max(1, int(sample_rate * 0.02))
    hop = max(1, int(sample_rate * 0.01))
    if len(x) < size:
        rms = np.array([np.sqrt(np.mean(x * x))])
    else:
        frames = np.lib.stride_tricks.sliding_window_view(x, size)[::hop]
        rms = np.sqrt(np.mean(frames * frames, axis=1))
    threshold = max(10 ** (-45 / 20), float(rms.max()) * 10 ** (-30 / 20))
    indices = np.flatnonzero(rms > threshold)
    if not len(indices):
        return 0, 0
    return int(indices[0] * hop), min(len(x), int(indices[-1] * hop + size))


def align_audio(x, cfg):
    x = np.asarray(x, dtype=np.float32).reshape(-1)
    length = int(cfg["num_samples"])
    start, end = active_bounds(x, int(cfg["sample_rate"]))
    detail = {
        "original_samples": int(len(x)),
        "active_start": int(start),
        "active_end": int(end),
        "active_duration_seconds": float((end - start) / cfg["sample_rate"]),
    }
    if end > start:
        margin = int(cfg.get("trim_margin_seconds", 0.05) * cfg["sample_rate"])
        x = x[max(0, start - margin) : min(len(x), end + margin)]
    if len(x) > length:
        raise ValueError("活动语音超过4秒窗口；请重录，不进行静默截断")
    peak = float(np.abs(x).max()) if len(x) else 0.0
    if peak > 1e-6:
        x = x * (np.float32(cfg.get("peak_normalize", 0.8)) / np.float32(peak))
    left = (length - len(x)) // 2
    x = np.pad(x, (left, length - len(x) - left))
    detail.update(operation="active_trim_peak_normalize_center_pad", offset_samples=-left)
    return x.astype(np.float32), detail


class LogMelNumpy:
    def __init__(self, cfg=None, weights_path=None):
        here = Path(__file__).resolve().parent
        self.cfg = cfg or json.loads((here / "preprocess_config.json").read_text(encoding="utf-8"))
        with np.load(weights_path or here / "tc_resnet_model_fp32.npz", allow_pickle=False) as archive:
            self.filters = archive["mel_filters"].astype(np.float32)
            self.window = archive["hann_window"].astype(np.float32)
            self.mean = np.float32(archive["feature_mean"])
            self.std = np.float32(archive["feature_std"])

    def __call__(self, audio):
        x = np.asarray(audio, dtype=np.float32).reshape(-1)
        n_fft = int(self.cfg["n_fft"])
        hop = int(self.cfg["hop_length"])
        frames = np.lib.stride_tricks.sliding_window_view(x, n_fft)[::hop]
        spectrum = np.fft.rfft(frames * self.window[None, :], n=n_fft, axis=1).astype(np.complex64)
        power = (np.abs(spectrum).astype(np.float32) ** 2).T
        feature = np.log(np.maximum(self.filters @ power, np.float32(self.cfg["log_epsilon"])))
        feature = (feature - self.mean) / self.std
        return feature[None].astype(np.float32)


def pcm16_mono_wav(path):
    with wave.open(str(path), "rb") as wav:
        if wav.getframerate() != 16000 or wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise ValueError("只接受16 kHz、单声道、PCM16 WAV")
        data = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")
    return data.astype(np.float32) / np.float32(32768.0)


def waveform_feature(audio, cfg=None):
    here = Path(__file__).resolve().parent
    cfg = cfg or json.loads((here / "preprocess_config.json").read_text(encoding="utf-8"))
    aligned, detail = align_audio(audio, cfg)
    return LogMelNumpy(cfg)(aligned), detail


def wav_feature(path, cfg=None):
    return waveform_feature(pcm16_mono_wav(path), cfg)
