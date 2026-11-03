"""FPGA-8 runtime adapter that reuses the already loaded audio/model Overlay.

This is derived from the validated FPGA-7 unified runtime.  It deliberately
does not program the PL when an Overlay is supplied by the notebook.
"""
from pathlib import Path
import platform
import sys
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
TEST1 = HERE.parent
if not (TEST1 / "static_runtime.py").is_file():
    raise RuntimeError("Copy this file into SonicArm/test_1/fpga_v8 beside cam_v8_audio.bit")
sys.path.insert(0, str(TEST1))

import static_runtime as sr
import fpga_context as pc


MODE_POINTWISE = 0
MODE_FCM = 1


def register_map(hwh_path):
    tree = ET.parse(hwh_path).getroot()
    module = next(m for m in tree.iter("MODULE") if m.get("INSTANCE") == "unified_0")
    if module.get("VLNV") != "xilinx.com:hls:unified_v7:1.0":
        raise ValueError("FPGA-8 中 unified_0 不是预期的 unified_v7:1.0")
    result = {}
    for register in module.findall(".//REGISTERS/REGISTER"):
        prop = register.find("./PROPERTY[@NAME='ADDRESS_OFFSET']")
        if prop is not None:
            result[register.get("NAME")] = int(prop.get("VALUE"), 0)
    pointers = tuple(dict.fromkeys((*pc.POINTERS, *sr.old.fcm.POINTERS)))
    scalars = tuple(dict.fromkeys((*pc.SCALARS, *sr.old.fcm.SCALARS, "mode")))
    required = ["CTRL", "GIER", "IP_IER", "IP_ISR", "ap_return", *scalars]
    for name in pointers:
        required.extend((name + "_1", name + "_2"))
    missing = [name for name in required if name not in result]
    if missing:
        raise ValueError("FPGA-8 HWH 寄存器表不完整: " + ", ".join(missing))
    return result


class ModeIP:
    def __init__(self, owner, mode):
        self.owner = owner
        self.mode = mode

    def write(self, address, value):
        if address == self.owner.offsets["CTRL"] and value & 1:
            self.owner.prepare(self.mode)
            label = "pointwise" if self.mode == MODE_POINTWISE else "FCM"
            self.owner.calls[label] += 1
        self.owner.ip.write(address, value)

    def read(self, address):
        return self.owner.ip.read(address)


class EngineView:
    def __init__(self, owner, mode):
        self.owner = owner
        self.ip = ModeIP(owner, mode)
        self.offsets = owner.offsets
        self.timeout = 30.0

    @property
    def poisoned(self):
        return self.owner.poisoned

    @poisoned.setter
    def poisoned(self, value):
        self.owner.poisoned = bool(value)


class Engine:
    def __init__(self, measuring=False, overlay=None, hwh_path=None):
        if platform.system() != "Linux" or platform.machine().lower() not in ("armv7l", "armv8l"):
            raise RuntimeError("请在 PYNQ-Z2 ARM Linux 上运行")
        from pynq import Overlay, Clocks

        bit_path = HERE / "cam_v8_audio.bit"
        hwh_path = Path(hwh_path or HERE / "cam_v8_audio.hwh")
        if overlay is None:
            overlay = Overlay(str(bit_path), download=True)
        self.overlay = overlay
        self.clock = float(Clocks.fclk0_mhz)
        if abs(self.clock - 100.0) > 0.1:
            raise ValueError(f"FPGA-8 要求 FCLK0=100 MHz，当前为 {self.clock}")
        self.offsets = register_map(hwh_path)
        self.ip = self.overlay.unified_0
        self.poisoned = False
        self.current_mode = None
        self.calls = {"pointwise": 0, "FCM": 0}
        self.records = []
        self.requested_measuring = bool(measuring)
        self.counter_available = False
        for key in ("GIER", "IP_IER"):
            self.ip.write(self.offsets[key], 0)
        if not self.ip.read(self.offsets["CTRL"]) & 4:
            raise RuntimeError("FPGA-8 unified_0 在初始化后不是 idle 状态")
        self.pw = EngineView(self, MODE_POINTWISE)
        self.fcm = EngineView(self, MODE_FCM)

    def prepare(self, mode):
        if self.poisoned:
            raise RuntimeError("上次 FPGA 调用失败；请给开发板断电重启")
        if mode == self.current_mode:
            return
        if mode == MODE_POINTWISE:
            self.ip.write(self.offsets["mode"], MODE_POINTWISE)
            for name in ("freq", "kernel", "stride_f"):
                self.ip.write(self.offsets[name], 1)
            self.ip.write(self.offsets["residual_1"], self.ip.read(self.offsets["output_r_1"]))
            self.ip.write(self.offsets["residual_2"], self.ip.read(self.offsets["output_r_2"]))
        elif mode == MODE_FCM:
            self.ip.write(self.offsets["mode"], MODE_FCM)
        else:
            raise ValueError("无效的 unified_0 模式")
        self.current_mode = mode


class Runtime(sr.StaticV4):
    def __init__(self, debug=False, capacity=529, measuring=False, overlay=None, hwh_path=None):
        self.base = self.fcm_context = self.runner = self.first = self.engine = None
        self.mode = "fpga"
        if sr.old.UNSAFE:
            raise RuntimeError("上次硬件调用失败；请给开发板断电重启")
        rows, params = sr.old.layers()
        self.runner = sr.old.FCMRunner(rows, params)
        try:
            self.first = sr.FirstCPU(self.runner)
            self.base = sr.StaticHybrid("integer", debug, first=self.first)
            self.engine = Engine(measuring, overlay=overlay, hwh_path=hwh_path)
            self.fcm_context = sr.old.FCMContext(
                self.engine.fcm, rows, params, min(2048, capacity), debug
            )
            self.runner.context = self.fcm_context
            original = pc.Engine
            pc.Engine = lambda timeout=30.0: self.engine.pw
            try:
                self.base.fpga = pc.FPGAContext(
                    [self.base.layers[k] for k in self.base.params], self.base.params, debug=debug
                )
            finally:
                pc.Engine = original
            self.base.mode = "fpga"
            for context in (self.base.fpga, self.fcm_context):
                if any(int(buf.physical_address) % 8 or buf.nbytes < 8 for buf in context.allocated):
                    raise ValueError("CMA 缓冲区不满足 FPGA-8 的 64-bit 对齐要求")
        except BaseException:
            self.close()
            raise

    def run(self, features, audit=False):
        before = dict(self.engine.calls)
        raw, detail = super().run(features, audit)
        actual = {name: self.engine.calls[name] - before[name] for name in before}
        expected = {
            "pointwise": sum(r["chunks"] for r in detail["layers"] if r["component"] == "pointwise"),
            "FCM": sum(r["chunks"] for r in detail["layers"] if r["component"] == "FCM"),
        }
        if actual != expected:
            raise AssertionError(f"FPGA 实际 ap_start 次数不匹配: actual={actual}, expected={expected}")
        detail["actual_v8_ap_start"] = actual
        return raw, detail

    def close(self):
        if self.engine and self.engine.poisoned:
            sr.old.UNSAFE = True
        super().close()

