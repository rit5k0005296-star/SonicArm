"""Persistent PYNQ hardware runtime for web-controlled enrollment and recognition.

The Overlay, codec, CAM++ runtime and PS KWS model are initialized once.  All
public capture/inference methods must be called by one controller worker at a
time; the HTTP layer never touches hardware directly.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import platform
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, Tuple

import numpy as np

from v9_audio import (
    analyze_and_select,
    cam_features,
    l2_normalize,
    read_pcm,
    resample_48k_to_16k,
    save_pcm16,
)


MessageCallback = Callable[[str], None]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_local(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


class BoardRuntime:
    """Own the one live Overlay/audio/CAM++/KWS context."""

    def __init__(self, root: Path, config: Dict[str, Any], defer_runtime: bool = False) -> None:
        self.root = Path(root).resolve()
        self.config = config
        if platform.system() != "Linux" or platform.machine().lower() not in (
            "armv7l",
            "armv8l",
            "aarch64",
        ):
            raise RuntimeError("live web control must run on PYNQ ARM Linux")

        paths = config["paths"]
        self.v8_dir = resolve_local(self.root, paths["v8_dir"])
        self.overlay_dir = resolve_local(self.root, paths.get("overlay_dir", paths["v8_dir"]))
        self.bit = self.overlay_dir / paths["bit"]
        self.hwh = self.overlay_dir / paths["hwh"]
        self.constants = resolve_local(self.root, paths["frontend_constants"])
        self.kws_dir = resolve_local(self.root, paths["kws_dir"])
        required = (
            self.bit,
            self.hwh,
            self.constants,
            self.v8_dir / paths["voiceprint_runtime"],
            self.kws_dir / "manifest.json",
        )
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise FileNotFoundError("missing required files: " + ", ".join(missing))
        expected = config["expected_sha256"]
        if sha256(self.bit) != expected["bit"] or sha256(self.hwh) != expected["hwh"]:
            raise RuntimeError("FPGA-10 bit/HWH identity mismatch")
        print("HARDWARE 1/8 bit/HWH identity verified", flush=True)

        sys.path.insert(0, str(self.v8_dir))
        print("HARDWARE 2/8 importing CAM++ and TC-ResNet3 runtimes", flush=True)
        self._v8_module = importlib.import_module("v8_runtime")
        sys.path.insert(0, str(self.kws_dir))
        self._kws_module = importlib.import_module("tc_resnet3_adapter")
        from pynq import Clocks, Overlay

        print("HARDWARE 3/8 downloading FPGA-10 Overlay", flush=True)
        self.overlay = Overlay(str(self.bit), download=True)
        print("HARDWARE 4/8 Overlay download complete", flush=True)
        required_ips = (
            "audio_codec_ctrl_0",
            "unified_0",
            "axi_vdma_0",
            "axi_dynclk_0",
            "vtc_out_0",
            "color_convert_0",
            "pixel_unpack_0",
            "hdmi_out_hpd_gpio",
        )
        # Inspect metadata only.  Accessing overlay.axi_vdma_0 would invoke the
        # stock PYNQ driver, which expects an interrupt pin that this deliberate
        # synchronous design does not expose.
        missing_ips = [name for name in required_ips if name not in self.overlay.ip_dict]
        if missing_ips:
            raise RuntimeError("FPGA-10 overlay lacks required IP: " + ", ".join(missing_ips))
        expected_clock = float(config["target"]["pl_clock_mhz"])
        if abs(float(Clocks.fclk0_mhz) - expected_clock) > 0.1:
            raise RuntimeError(f"unexpected FCLK0: {Clocks.fclk0_mhz}")

        self.audio = None
        self.voiceprint = None
        self.kws = None
        if not defer_runtime:
            self.initialize_runtime()

    def initialize_runtime(self) -> None:
        """Initialize audio and inference after display has claimed its framebuffer."""
        if self.audio is not None or self.voiceprint is not None or self.kws is not None:
            raise RuntimeError("audio and inference runtime already initialized")
        print("HARDWARE 5/8 configuring audio codec", flush=True)
        self.audio = self.overlay.audio_codec_ctrl_0
        self.audio.configure(sample_rate=48000, iic_index=1, uio_name="audio-codec-ctrl")
        self.audio.deselect_inputs()
        time.sleep(0.25)
        self.audio.select_microphone()
        time.sleep(0.75)
        print("HARDWARE 6/8 audio codec ready; initializing CAM++", flush=True)
        self.voiceprint = self._v8_module.Runtime(
            debug=False,
            capacity=529,
            overlay=self.overlay,
            hwh_path=self.hwh,
        )
        print("HARDWARE 7/8 CAM++ ready; loading TC-ResNet3", flush=True)
        self.kws = self._kws_module.TCResNet3PS(self.kws_dir)
        print("HARDWARE 8/8 TC-ResNet3 ready", flush=True)

    def close(self) -> None:
        if getattr(self, "voiceprint", None) is not None:
            self.voiceprint.close()
        if getattr(self, "audio", None) is not None:
            self.audio.deselect_inputs()

    def _record_raw(self, path: Path, seconds: float) -> np.ndarray:
        self.audio.record(float(seconds))
        self.audio.save(str(path))
        pcm, rate = read_pcm(path)
        if rate != 48000 or pcm.ndim != 2 or pcm.shape[1] != 2:
            raise RuntimeError(f"unexpected codec recording format: rate={rate}, shape={pcm.shape}")
        return pcm

    def capture_quiet(self, run_dir: Path) -> np.ndarray:
        return self._record_raw(run_dir / "quiet_raw24.wav", float(self.config["audio"]["quiet_seconds"]))

    def capture_embedding(
        self,
        run_dir: Path,
        stem: str,
        quiet: np.ndarray,
        after_capture: MessageCallback | None = None,
    ) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
        raw_path = run_dir / f"{stem}_raw24.wav"
        pcm = self._record_raw(raw_path, float(self.config["audio"]["speech_seconds"]))
        if after_capture is not None:
            after_capture("声音采集完毕，正在进行识别")
        channel, gate = analyze_and_select(quiet, pcm, self.config["audio"])
        waveform_16k = resample_48k_to_16k(pcm[:, channel])
        wav_path = run_dir / f"{stem}_16k_mono.wav"
        save_pcm16(wav_path, waveform_16k)
        features = cam_features(waveform_16k, self.constants)
        if features.shape[1] > 529:
            raise RuntimeError(f"CAM++ feature frames exceed V8 capacity: {features.shape}")
        started = time.perf_counter()
        raw_embedding, report = self.voiceprint.run(features, audit=False)
        inference_ms = (time.perf_counter() - started) * 1000.0
        actual_calls = report.get("actual_v8_ap_start")
        if actual_calls != {"pointwise": 55, "FCM": 12}:
            raise RuntimeError(f"unexpected V8 accelerator calls: {actual_calls}")
        embedding = l2_normalize(raw_embedding)
        if embedding.shape != (192,):
            raise RuntimeError(f"unexpected voiceprint embedding shape: {embedding.shape}")
        detail = {
            "raw_wav": str(raw_path),
            "model_wav": str(wav_path),
            "audio_gate": gate,
            "voiceprint_inference_ms": float(inference_ms),
            "actual_v8_ap_start": actual_calls,
        }
        return embedding, waveform_16k, detail

    def recognize_command(self, waveform_16k: np.ndarray) -> Dict[str, Any]:
        started = time.perf_counter()
        result = self.kws.recognize(waveform_16k)
        result["inference_ms"] = (time.perf_counter() - started) * 1000.0
        package_threshold = result.get("threshold")
        result["package_threshold"] = None if package_threshold is None else float(package_threshold)
        class_name = str(result.get("class_name", ""))
        command_thresholds = self.config["decision"].get("kws_command_thresholds", {})
        result["threshold"] = float(
            command_thresholds.get(class_name, self.config["decision"]["kws_threshold"])
        )
        result["threshold_calibrated"] = bool(
            self.config["decision"]["kws_threshold_calibrated"]
        )
        if result.get("execution_enabled") or result.get("execute"):
            raise RuntimeError("KWS adapter unexpectedly enabled execution")
        return result

