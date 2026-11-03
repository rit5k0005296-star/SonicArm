"""Audio conversion and CAM++ frontend used by the V9 validation runner."""
from __future__ import annotations

import math
import wave
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np


class AudioGateError(RuntimeError):
    """Raised with measured values when a capture is unsuitable for inference."""

    def __init__(self, metrics: Dict[str, float], limits: Dict[str, float]) -> None:
        self.metrics = metrics
        self.limits = limits
        reasons = []
        if metrics["speech_over_quiet_db"] < limits["minimum_speech_over_quiet_db"]:
            reasons.append(
                f"语音相对底噪 {metrics['speech_over_quiet_db']:.1f} dB < {limits['minimum_speech_over_quiet_db']:.1f} dB"
            )
        if metrics["speech_rms_dbfs"] < limits["minimum_speech_rms_dbfs"]:
            reasons.append(
                f"语音音量 {metrics['speech_rms_dbfs']:.1f} dBFS < {limits['minimum_speech_rms_dbfs']:.1f} dBFS"
            )
        if metrics["clip_percent"] >= limits["maximum_clip_percent"]:
            reasons.append(
                f"削波率 {metrics['clip_percent']:.3f}% >= {limits['maximum_clip_percent']:.3f}%"
            )
        detail = "；".join(reasons) or "音频质量未通过"
        super().__init__(f"音频门控失败：{detail}；通道={int(metrics['channel'])}")


def read_pcm(path: Path) -> Tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav:
        channels, width = wav.getnchannels(), wav.getsampwidth()
        rate, frames = wav.getframerate(), wav.getnframes()
        raw = wav.readframes(frames)
    if width == 3:
        values = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
        values = values[:, 0] | (values[:, 1] << 8) | (values[:, 2] << 16)
        values = np.where(values & 0x800000, values - 0x1000000, values)
        pcm = values.astype(np.float32) / np.float32(1 << 23)
    elif width == 2:
        pcm = np.frombuffer(raw, "<i2").astype(np.float32) / np.float32(1 << 15)
    else:
        raise ValueError(f"unsupported PCM width: {width * 8} bits")
    return pcm.reshape(-1, channels), rate


def save_pcm16(path: Path, waveform: np.ndarray, rate: int = 16000) -> None:
    waveform = np.clip(np.asarray(waveform), -0.999969, 0.999969)
    data = np.round(waveform * 32768.0).astype("<i2")
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(data.tobytes())


def dbfs(value: float) -> float:
    return 20.0 * math.log10(max(float(value), 1e-15))


def channel_metrics(pcm: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    centered = pcm - pcm.mean(axis=0, keepdims=True)
    rms = np.sqrt(np.mean(centered.astype(np.float64) ** 2, axis=0))
    peak = np.max(np.abs(centered), axis=0)
    clip = np.mean(np.abs(pcm) >= 0.99, axis=0) * 100.0
    return rms, peak, clip


def resample_48k_to_16k(waveform: np.ndarray, taps: int = 255, cutoff_hz: float = 7200.0) -> np.ndarray:
    waveform = np.asarray(waveform, dtype=np.float64)
    waveform -= np.mean(waveform)
    n = np.arange(taps, dtype=np.float64) - (taps - 1) / 2
    fc = cutoff_hz / 48000.0
    kernel = 2 * fc * np.sinc(2 * fc * n) * np.hamming(taps)
    kernel /= kernel.sum()
    return np.convolve(waveform, kernel, mode="same")[::3].astype(np.float32)


def analyze_and_select(quiet: np.ndarray, speech: np.ndarray, gate_config: Dict[str, Any]) -> Tuple[int, Dict[str, float]]:
    quiet_rms, _, _ = channel_metrics(quiet)
    speech_rms, speech_peak, speech_clip = channel_metrics(speech)
    snr_proxy = 20 * np.log10(np.maximum(speech_rms, 1e-15) / np.maximum(quiet_rms, 1e-15))
    channel = int(np.argmax(snr_proxy))
    metrics = {
        "channel": channel,
        "quiet_rms_dbfs": dbfs(quiet_rms[channel]),
        "speech_rms_dbfs": dbfs(speech_rms[channel]),
        "speech_peak_dbfs": dbfs(speech_peak[channel]),
        "speech_over_quiet_db": float(snr_proxy[channel]),
        "clip_percent": float(speech_clip[channel]),
    }
    limits = {
        "minimum_speech_over_quiet_db": float(gate_config["minimum_speech_over_quiet_db"]),
        "minimum_speech_rms_dbfs": float(gate_config["minimum_speech_rms_dbfs"]),
        "maximum_clip_percent": float(gate_config["maximum_clip_percent"]),
    }
    passed = (
        metrics["speech_over_quiet_db"] >= limits["minimum_speech_over_quiet_db"]
        and metrics["speech_rms_dbfs"] >= limits["minimum_speech_rms_dbfs"]
        and metrics["clip_percent"] < limits["maximum_clip_percent"]
    )
    if not passed:
        raise AudioGateError(metrics, limits)
    return channel, metrics


def cam_features(waveform_16k: np.ndarray, constants_path: Path) -> np.ndarray:
    waveform = np.asarray(waveform_16k, dtype=np.float32).reshape(-1)
    with np.load(constants_path, allow_pickle=False) as constants:
        mel, window = constants["mel"], constants["window"]
    count = 1 + (len(waveform) - 400) // 160
    if count <= 0:
        raise ValueError("recording is too short")
    frames = np.lib.stride_tricks.as_strided(
        waveform,
        shape=(count, 400),
        strides=(160 * waveform.strides[0], waveform.strides[0]),
    ).copy()
    frames -= frames.mean(axis=1, keepdims=True)
    previous = np.concatenate((frames[:, :1], frames[:, :-1]), axis=1)
    frames = (frames - np.float32(0.97) * previous) * window
    spectrum = np.abs(np.fft.rfft(frames, n=512, axis=1).astype(np.complex64)).astype(np.float32) ** 2
    features = np.log(np.maximum(spectrum @ mel.T, np.finfo(np.float32).eps)).astype(np.float32)
    features -= features.mean(axis=0, keepdims=True)
    return np.ascontiguousarray(features[None], dtype=np.float32)


def l2_normalize(vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(vector, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(vector))
    if not np.isfinite(norm) or norm <= 1e-12:
        raise RuntimeError("invalid zero or non-finite embedding")
    return vector / norm
