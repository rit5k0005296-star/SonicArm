#!/usr/bin/env python3
"""FPGA-10 physical HDMI + Pillow UI + USB touch smoke test."""

from __future__ import annotations

import signal
import struct
import threading
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pynq import DefaultIP, Overlay
from pynq.lib.video import PIXEL_RGB, VideoMode
from pynq.lib.video.dma import AxiVDMA
import pynq.lib._video as _video


ROOT = Path(__file__).resolve().parent
BIT = ROOT / "fpga10_audio_hdmi.bit"
TOUCH = Path("/dev/input/event0")
WIDTH, HEIGHT = 1280, 720
TOUCH_MAX_X, TOUCH_MAX_Y = 800, 480
EVENT = struct.Struct("llHHI")
BTN_TOUCH = 0x14A


def font(size: int):
    candidates = (
        ROOT / "NotoSansSC-Regular.otf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )
    for candidate in candidates:
        if Path(candidate).is_file():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


F24, F32, F44, F64 = (font(size) for size in (24, 32, 44, 64))


class SmokeUI:
    def __init__(self):
        self.page = "recognition"
        self.message = "点击开始识别，测试触摸响应"
        self.command = "待机"
        self._lock = threading.Lock()
        self._dirty = True

    def tap(self, x: int, y: int):
        with self._lock:
            if self.page == "recognition" and y >= 620:
                if x < 640:
                    self.page = "registration"
                    self.message = "注册页面触摸切换成功"
                else:
                    self.message = "触摸已触发开始识别按钮"
                    self.command = "按钮有效"
            elif self.page == "registration" and y >= 620:
                self.page = "recognition"
                self.message = "已返回识别页面"
                self.command = "待机"
            self._dirty = True

    def render_if_dirty(self):
        with self._lock:
            if not self._dirty:
                return None
            self._dirty = False
            page, message, command = self.page, self.message, self.command
        image = Image.new("RGB", (WIDTH, HEIGHT), "#f7f9fc")
        draw = ImageDraw.Draw(image)
        navy, blue, border, muted = "#121b31", "#1478c9", "#ced8e5", "#65738b"
        draw.rounded_rectangle((8, 8, 1272, 712), 10, fill="white", outline=border, width=2)
        if page == "recognition":
            draw.line((780, 8, 780, 712), fill=border, width=2)
            draw.text((32, 28), "身份识别结果", font=F32, fill=navy)
            draw.ellipse((230, 105, 550, 425), fill="#e7edf5", outline=blue, width=6)
            draw.text((322, 220), "声纹", font=F44, fill=muted)
            draw.text((285, 455), "尚未确认身份", font=F44, fill=navy)
            draw.rounded_rectangle((70, 525, 710, 585), 8, fill="#eaf5ff", outline="#9acbed")
            draw.text((105, 540), message, font=F24, fill=muted)
            draw.text((815, 28), "命令识别结果", font=F32, fill=navy)
            draw.text((900, 220), command, font=F64, fill=navy)
            draw.text((815, 420), "机械臂运动状态", font=F32, fill=navy)
            draw.text((940, 525), "禁用", font=F64, fill=muted)
            draw.rounded_rectangle((30, 620, 610, 695), 8, fill="white", outline=blue, width=3)
            draw.text((225, 637), "注册用户", font=F32, fill=blue)
            draw.rounded_rectangle((790, 620, 1250, 695), 8, fill=blue)
            draw.text((928, 637), "开始识别", font=F32, fill="white")
        else:
            draw.text((32, 28), "注册身份", font=F44, fill=navy)
            draw.text((470, 170), "注册页面", font=F64, fill=navy)
            draw.text((445, 280), message, font=F32, fill=muted)
            draw.rounded_rectangle((350, 400, 930, 500), 10, fill="#eaf5ff", outline=blue, width=3)
            draw.text((520, 430), "触摸切换正常", font=F32, fill=blue)
            draw.rounded_rectangle((30, 620, 1250, 695), 8, fill=blue)
            draw.text((520, 637), "返回识别", font=F32, fill="white")
        return np.asarray(image, dtype=np.uint8)


def main():
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    overlay = Overlay(str(BIT), download=True)

    # Overlay download resets the AXI GPIO.  Reassert the PYNQ-Z2 HDMI OUT
    # HPD/enable signal for every standalone display entry point.
    hpd = overlay.hdmi_out_hpd_gpio
    hpd.write(0x04, 0x00000000)
    hpd.write(0x00, 0x00000001)
    time.sleep(0.2)

    display = _video._display(
        overlay.ip_dict["vtc_out_0"]["phys_addr"],
        overlay.ip_dict["axi_dynclk_0"]["phys_addr"],
        1,
    )
    desc = overlay.ip_dict["axi_vdma_0"]
    vdma = DefaultIP(desc)
    vdma.framecount = int(desc["parameters"]["C_NUM_FSTORES"])
    channel = AxiVDMA.MM2SChannel(vdma, interrupt=None, memory=overlay.device.default_memory)
    mode = VideoMode(WIDTH, HEIGHT, 24, fps=60)
    overlay.color_convert_0.colorspace = PIXEL_RGB.out_color
    overlay.pixel_unpack_0.bits_per_pixel = 24
    display.mode(2)
    channel.mode = mode
    display.start()
    time.sleep(0.2)
    channel.start()
    frame = channel.newframe()
    ui = SmokeUI()

    def touch_loop():
        x = y = None
        with TOUCH.open("rb", buffering=0) as stream:
            while not stop.is_set():
                payload = stream.read(EVENT.size)
                if len(payload) != EVENT.size:
                    continue
                _sec, _usec, kind, code, value = EVENT.unpack(payload)
                if kind == 0x03 and code == 0x00:
                    x = value
                elif kind == 0x03 and code == 0x01:
                    y = value
                elif kind == 0x01 and code == BTN_TOUCH and value == 0 and x is not None and y is not None:
                    sx = max(0, min(WIDTH - 1, round(x * (WIDTH - 1) / TOUCH_MAX_X)))
                    sy = max(0, min(HEIGHT - 1, round(y * (HEIGHT - 1) / TOUCH_MAX_Y)))
                    print(f"TOUCH raw=({x},{y}) hdmi=({sx},{sy})", flush=True)
                    ui.tap(sx, sy)

    thread = threading.Thread(target=touch_loop, daemon=True)
    thread.start()
    print("DISPLAY_TOUCH_SMOKETEST_RUNNING; touch buttons; Ctrl-C to stop", flush=True)
    try:
        while not stop.is_set():
            pixels = ui.render_if_dirty()
            if pixels is not None:
                frame[:] = pixels
                frame.flush()
                channel.setframe(frame)
                print(
                    "DISPLAY_DIAG "
                    f"hpd_data=0x{hpd.read(0x00):08x} "
                    f"hpd_tri=0x{hpd.read(0x04):08x} "
                    f"vdma_cr=0x{vdma.read(0x00):08x} "
                    f"vdma_sr=0x{vdma.read(0x04):08x} "
                    f"vsize={vdma.read(0x50)} "
                    f"hsize={vdma.read(0x54)} "
                    f"stride=0x{vdma.read(0x58):08x}",
                    flush=True,
                )
            stop.wait(0.05)
    finally:
        channel.stop()
        display.stop()


if __name__ == "__main__":
    main()
