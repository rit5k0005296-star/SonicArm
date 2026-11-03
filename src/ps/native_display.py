"""Native HDMI/VDMA display and USB-HID touch frontend for FPGA-10.

The caller owns the Overlay.  This module never downloads a bitstream and is
therefore safe to run beside the audio, voiceprint and KWS runtimes in the same
process.
"""
from __future__ import annotations

import signal
import select
import struct
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont


LOGICAL_WIDTH = 800
LOGICAL_HEIGHT = 480
HDMI_WIDTH = 1280
HDMI_HEIGHT = 720
# Pillow < 9.1 exposes resampling filters directly on Image; newer releases
# place them under Image.Resampling.
RESAMPLE_BILINEAR = getattr(getattr(Image, "Resampling", Image), "BILINEAR")
EVENT = struct.Struct("llHHI")
EV_KEY = 0x01
EV_ABS = 0x03
ABS_X = 0x00
ABS_Y = 0x01
BTN_TOUCH = 0x14A

KEYBOARD_ROWS = (
    tuple("QWERTYUIOP"),
    tuple("ASDFGHJKL"),
    tuple("ZXCVBNM"),
    tuple("1234567890"),
)


def keyboard_key_boxes(editing_field: str) -> list[Tuple[str, str, Tuple[int, int, int, int]]]:
    """Return keyboard key values, labels and touch boxes for the native UI."""
    keys: list[Tuple[str, str, Tuple[int, int, int, int]]] = []
    left, right = 20, 780
    for row_index, row in enumerate(KEYBOARD_ROWS):
        top = 205 + row_index * 43
        width = (right - left) / len(row)
        for index, value in enumerate(row):
            box = (round(left + index * width), top, round(left + (index + 1) * width) - 4, top + 38)
            keys.append((value, value, box))
    separator = " " if editing_field == "name" else "-"
    separator_label = "空格" if editing_field == "name" else "-"
    actions = (
        ("CANCEL", "取消", (20, 382, 130, 462)),
        ("CLEAR", "清空", (140, 382, 250, 462)),
        (separator, separator_label, (260, 382, 425, 462)),
        ("BACKSPACE", "退格", (435, 382, 575, 462)),
        ("DONE", "完成", (585, 382, 780, 462)),
    )
    keys.extend(actions)
    return keys


def keyboard_key_at(x: int, y: int, editing_field: str) -> Optional[str]:
    for value, _label, (left, top, right, bottom) in keyboard_key_boxes(editing_field):
        if left <= x <= right and top <= y <= bottom:
            return value
    return None


def map_touch(raw_x: int, raw_y: int, max_x: int = 800, max_y: int = 480) -> Tuple[int, int]:
    x = max(0, min(LOGICAL_WIDTH - 1, round(raw_x * (LOGICAL_WIDTH - 1) / max_x)))
    y = max(0, min(LOGICAL_HEIGHT - 1, round(raw_y * (LOGICAL_HEIGHT - 1) / max_y)))
    return x, y


class NativeUIRenderer:
    """Pure Pillow renderer; usable in offline tests without PYNQ."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.regular = self._font_path("NotoSansSC-Regular.otf")
        self.bold = self._font_path("NotoSansSC-Bold.otf")
        self.f18 = self._font(18)
        self.f16 = self._font(16)
        self.f22 = self._font(22)
        self.f28 = self._font(28, bold=True)
        self.f38 = self._font(38, bold=True)
        self.f52 = self._font(52, bold=True)

    def _font_path(self, name: str) -> Path:
        candidates = (self.root / name, self.root.parent / "board_package" / name)
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        raise FileNotFoundError(f"display font not found: {name}")

    def _font(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(str(self.bold if bold else self.regular), size)

    @staticmethod
    def _center(draw: ImageDraw.ImageDraw, box: Tuple[int, int, int, int], text: str, font: Any, fill: str) -> None:
        left, top, right, bottom = box
        bounds = draw.textbbox((0, 0), text, font=font)
        width, height = bounds[2] - bounds[0], bounds[3] - bounds[1]
        draw.text(((left + right - width) / 2, (top + bottom - height) / 2 - bounds[1]), text, font=font, fill=fill)

    def _button(self, draw: ImageDraw.ImageDraw, box: Tuple[int, int, int, int], text: str, primary: bool = False) -> None:
        blue = "#0878d1"
        draw.rounded_rectangle(box, radius=8, fill=blue if primary else "#ffffff", outline=blue, width=2)
        self._center(draw, box, text, self.f22, "#ffffff" if primary else blue)

    def _fit_center(
        self,
        draw: ImageDraw.ImageDraw,
        box: Tuple[int, int, int, int],
        text: str,
        fill: str,
        maximum: int = 52,
        minimum: int = 20,
        bold: bool = True,
    ) -> None:
        """Center one line and shrink it until it stays inside the box."""
        left, top, right, bottom = box
        available_width = right - left - 12
        available_height = bottom - top - 8
        for size in range(maximum, minimum - 1, -2):
            font = self._font(size, bold=bold)
            bounds = draw.textbbox((0, 0), text, font=font)
            if bounds[2] - bounds[0] <= available_width and bounds[3] - bounds[1] <= available_height:
                self._center(draw, box, text, font, fill)
                return
        # Extremely long labels are split into two balanced lines.
        midpoint = max(1, len(text) // 2)
        lines = text[:midpoint] + "\n" + text[midpoint:]
        font = self._font(minimum, bold=bold)
        bounds = draw.multiline_textbbox((0, 0), lines, font=font, align="center", spacing=2)
        width, height = bounds[2] - bounds[0], bounds[3] - bounds[1]
        draw.multiline_text(
            ((left + right - width) / 2, (top + bottom - height) / 2),
            lines,
            font=font,
            fill=fill,
            align="center",
            spacing=2,
        )

    def render(
        self,
        page: str,
        state: Dict[str, Any],
        enrollment: Dict[str, Any],
        local_id: str,
        local_name: str,
        users: Optional[list[Dict[str, Any]]] = None,
        selected_user_id: str = "",
        delete_confirm: bool = False,
        editing_field: str = "",
        show_local_values: bool = True,
    ) -> Image.Image:
        image = Image.new("RGB", (LOGICAL_WIDTH, LOGICAL_HEIGHT), "#f7faff")
        draw = ImageDraw.Draw(image)
        navy, blue, muted, line = "#101b34", "#0878d1", "#667694", "#d5dde8"
        draw.rounded_rectangle((4, 4, 796, 476), radius=8, fill="#ffffff", outline=line, width=1)

        if page == "users":
            users = users or []
            draw.text((20, 16), "用户管理", font=self.f28, fill=navy)
            draw.text((505, 16), "用户详情", font=self.f28, fill=navy)
            draw.line((490, 0, 490, 480), fill=line, width=1)
            draw.line((0, 60, 800, 60), fill=line, width=1)
            visible = users[:4]
            for index, user in enumerate(visible):
                top = 72 + index * 68
                selected = str(user.get("id", "")) == selected_user_id
                draw.rounded_rectangle(
                    (18, top, 472, top + 58), 6,
                    fill="#eaf5ff" if selected else "#ffffff",
                    outline=blue if selected else line,
                    width=2 if selected else 1,
                )
                draw.text((30, top + 14), str(user.get("id", ""))[:14], font=self.f18, fill=navy)
                draw.text((190, top + 14), str(user.get("name", "未命名"))[:10], font=self.f18, fill=navy)
                draw.text((350, top + 14), "✓ 已录入", font=self.f18, fill="#0a9f42")
            selected_user = next((user for user in users if str(user.get("id", "")) == selected_user_id), None)
            if selected_user:
                self._center(draw, (510, 85, 780, 145), str(selected_user.get("name", "未命名"))[:12], self.f28, navy)
                draw.text((525, 165), f"编号：{selected_user.get('id', '')}", font=self.f18, fill=navy)
                registered = str(selected_user.get("registeredAt", ""))[:19].replace("T", " ")
                draw.text((525, 205), f"注册：{registered or '—'}", font=self.f16, fill=muted)
                hint = "再次点击确认删除" if delete_confirm else "删除后可人工恢复"
                self._center(draw, (505, 255, 785, 305), hint, self.f16, "#cf202f" if delete_confirm else muted)
            else:
                self._center(draw, (505, 110, 785, 250), "请选择用户", self.f28, muted)
            draw.text((22, 350), f"共 {len(users)} 条记录", font=self.f18, fill=muted)
            self._button(draw, (18, 405, 190, 462), "返回注册")
            self._button(draw, (205, 405, 375, 462), "返回识别")
            self._button(draw, (505, 405, 635, 462), "确认删除" if delete_confirm else "删除用户")
            self._button(draw, (650, 405, 782, 462), "刷新列表", primary=True)
            return image

        if page == "enroll":
            shown_name = local_name if show_local_values else str(enrollment.get("name") or local_name)
            shown_id = local_id if show_local_values else str(enrollment.get("id") or local_id)
            draw.text((20, 16), "注册身份", font=self.f28, fill=navy)
            draw.line((0, 60, 800, 60), fill=line, width=1)
            draw.text((28, 90), "姓名", font=self.f22, fill=navy)
            draw.rounded_rectangle((118, 78, 330, 122), 6, fill="#f8fafc", outline=blue if editing_field == "name" else line, width=2 if editing_field == "name" else 1)
            draw.text((132, 86), shown_name, font=self.f22, fill=navy)
            draw.text((28, 150), "用户编号", font=self.f22, fill=navy)
            draw.rounded_rectangle((118, 138, 330, 182), 6, fill="#f8fafc", outline=blue if editing_field == "id" else line, width=2 if editing_field == "id" else 1)
            draw.text((132, 146), shown_id, font=self.f22, fill=navy)
            if editing_field:
                title = "输入英文姓名" if editing_field == "name" else "输入用户编号"
                self._center(draw, (350, 72, 775, 190), title, self.f22, blue)
                for value, label, box in keyboard_key_boxes(editing_field):
                    primary = value == "DONE"
                    draw.rounded_rectangle(box, 6, fill=blue if primary else "#f8fafc", outline=blue if primary else line, width=2 if primary else 1)
                    font = self.f18 if len(label) <= 2 else self.f16
                    self._center(draw, box, label, font, "#ffffff" if primary else navy)
                return image
            draw.text((385, 84), "声纹录入", font=self.f28, fill=navy)
            samples = int(enrollment.get("samples", 0))
            for index in range(3):
                box = (380 + index * 125, 140, 485 + index * 125, 198)
                draw.rounded_rectangle(box, 7, fill="#eaf5ff" if index < samples else "#ffffff", outline=blue if index < samples else line, width=2)
                self._center(draw, box, f"{index + 1}  {'已录入' if index < samples else '未录入'}", self.f18, blue if index < samples else muted)
            message = str(enrollment.get("message", "填写人员信息后开始录入"))
            self._center(draw, (350, 220, 775, 300), message[:30], self.f18, muted)
            self._button(draw, (20, 320, 330, 375), "前往用户管理")
            self._button(draw, (20, 398, 245, 458), "返回识别")
            busy = enrollment.get("status") in ("recording", "processing")
            self._button(draw, (270, 398, 775, 458), "录入中" if busy else "开始录入", primary=True)
            return image

        identity = state.get("identity", {})
        command = state.get("command", {})
        arm = state.get("arm", {})
        phase = str(state.get("phase", "idle"))
        denied = phase in ("denied", "fault")
        draw.text((18, 16), "身份识别结果", font=self.f28, fill=navy)
        draw.text((505, 16), "命令识别结果", font=self.f28, fill=navy)
        draw.line((490, 0, 490, 480), fill=line, width=1)
        draw.line((0, 60, 800, 60), fill=line, width=1)
        draw.ellipse((155, 70, 335, 250), fill="#edf3fa", outline=blue if identity.get("name") else "#aebaca", width=3)
        avatar = (str(identity.get("name") or "声纹")[:2])
        self._center(draw, (155, 70, 335, 250), avatar, self.f38, blue if identity.get("name") else muted)
        name = str(identity.get("name") or state.get("headline") or "尚未确认身份")
        self._fit_center(draw, (45, 252, 445, 294), name[:16], "#cf202f" if denied else navy, maximum=36, minimum=22)
        message = str(state.get("message", "等待声纹识别程序返回结果"))
        draw.rounded_rectangle((28, 298, 462, 329), 6, fill="#eaf5ff", outline="#b9ddfa", width=1)
        self._fit_center(draw, (32, 299, 458, 328), message, muted, maximum=17, minimum=12, bold=False)
        score = identity.get("score")
        score_text = "—" if score is None else f"{float(score) * 100:.1f}%"
        self._center(draw, (50, 330, 440, 355), f"声纹匹配程度  {score_text}", self.f16, muted)
        self._fit_center(draw, (505, 80, 785, 215), str(command.get("text") or "待机"), "#cf202f" if denied else navy)
        draw.text((512, 238), "机械臂运动状态", font=self.f28, fill=navy)
        self._center(draw, (505, 286, 785, 370), str(arm.get("status") or "待机")[:10], self.f38, "#cf202f" if denied else blue)
        threshold = float(identity.get("threshold", 0.67))
        draw.text((55, 365), "识别阈值", font=self.f16, fill=navy)
        draw.rounded_rectangle((150, 373, 410, 383), 5, fill="#d9e1eb")
        knob_x = 150 + round(max(0.0, min(1.0, threshold)) * 260)
        draw.rounded_rectangle((150, 373, knob_x, 383), 5, fill=blue)
        draw.ellipse((knob_x - 12, 366, knob_x + 12, 390), fill=blue, outline="#ffffff", width=3)
        draw.text((420, 363), f"{threshold * 100:.0f}%", font=self.f18, fill=navy)
        self._button(draw, (20, 408, 230, 464), "注册用户")
        busy = phase in ("listening", "executing")
        self._button(draw, (250, 408, 470, 464), "识别中" if busy else "开始识别", primary=True)
        return image


class NativeDisplayRuntime:
    """Own VDMA/display/touch while sharing an already-loaded Overlay."""

    def __init__(self, root: Path, config: Dict[str, Any], overlay: Any, controller: Any, state: Any, enrollment: Any) -> None:
        self.root = Path(root)
        self.config = config
        self.overlay = overlay
        self.controller = controller
        self.state = state
        self.enrollment = enrollment
        self.renderer = NativeUIRenderer(self.root)
        display_cfg = config.get("display", {})
        self.touch_path = Path(display_cfg.get("touch_device", "/dev/input/event0"))
        self.touch_max_x = int(display_cfg.get("touch_max_x", 800))
        self.touch_max_y = int(display_cfg.get("touch_max_y", 480))
        self.local_name = str(display_cfg.get("default_enrollment_name", "现场用户"))
        self.local_prefix = str(display_cfg.get("default_enrollment_id_prefix", "SA"))
        self.local_id = self._new_local_id()
        self.page = "recognize"
        self.selected_user_id = ""
        self.delete_confirm = False
        self.editing_field = ""
        self._edit_original = ""
        self.show_local_values = True
        self._stop = threading.Event()
        self._dirty = threading.Event()
        self._dirty.set()
        self._threads: list[threading.Thread] = []
        self._display = None
        self._channel = None
        self._hpd = None
        self._vdma = None

    def _new_local_id(self) -> str:
        return f"{self.local_prefix}{datetime.now().strftime('%m%d%H%M')}"

    def start(self) -> None:
        if not self.touch_path.exists():
            raise FileNotFoundError(f"touch input not found: {self.touch_path}")
        from pynq import DefaultIP
        from pynq.lib.video import PIXEL_RGB, VideoMode
        from pynq.lib.video.dma import AxiVDMA
        import pynq.lib._video as _video

        print("DISPLAY 1/7 asserting HDMI HPD", flush=True)
        hpd = self.overlay.hdmi_out_hpd_gpio
        self._hpd = hpd
        hpd.write(0x04, 0x00000000)
        hpd.write(0x00, 0x00000001)
        time.sleep(0.2)
        print("DISPLAY 2/7 constructing display and synchronous VDMA channel", flush=True)
        self._display = _video._display(
            self.overlay.ip_dict["vtc_out_0"]["phys_addr"],
            self.overlay.ip_dict["axi_dynclk_0"]["phys_addr"],
            1,
        )
        desc = self.overlay.ip_dict["axi_vdma_0"]
        vdma = DefaultIP(desc)
        self._vdma = vdma
        vdma.framecount = int(desc["parameters"]["C_NUM_FSTORES"])
        self._channel = AxiVDMA.MM2SChannel(vdma, interrupt=None, memory=self.overlay.device.default_memory)
        print("DISPLAY 3/7 configuring pixel pipeline", flush=True)
        color_convert = self.overlay.color_convert_0
        pixel_unpack = self.overlay.pixel_unpack_0
        color_convert.colorspace = PIXEL_RGB.out_color
        pixel_unpack.bits_per_pixel = 24
        self._display.mode(2)
        self._channel.mode = VideoMode(HDMI_WIDTH, HDMI_HEIGHT, 24, fps=60)
        print("DISPLAY 4/7 starting HDMI timing", flush=True)
        self._display.start()
        time.sleep(0.2)
        print("DISPLAY 5/7 starting VDMA", flush=True)
        self._channel.start()
        print("DISPLAY 6/7 allocating and drawing first frame", flush=True)
        self._frame = self._channel.newframe()
        # Draw once synchronously so font/Pillow/framebuffer errors fail app
        # startup instead of silently killing a background thread.
        self._render_current()
        time.sleep(0.2)
        print(
            "DISPLAY_DIAG "
            f"hpd_data=0x{self._hpd.read(0x00):08x} "
            f"hpd_tri=0x{self._hpd.read(0x04):08x} "
            f"vdma_cr=0x{self._vdma.read(0x00):08x} "
            f"vdma_sr=0x{self._vdma.read(0x04):08x} "
            f"park=0x{self._vdma.read(0x28):08x} "
            f"vsize={self._vdma.read(0x50)} "
            f"hsize={self._vdma.read(0x54)} "
            f"stride=0x{self._vdma.read(0x58):08x}",
            flush=True,
        )
        print("DISPLAY 7/7 first frame submitted", flush=True)
        self._threads = [
            threading.Thread(target=self._render_loop, name="native-display", daemon=True),
            threading.Thread(target=self._touch_loop, name="native-touch", daemon=True),
        ]
        for thread in self._threads:
            thread.start()

    def _render_current(self) -> None:
        users: list[Dict[str, Any]] = []
        if self.page == "users":
            users = list(self.controller.list_users().get("users", []))
            if users and not any(str(user.get("id", "")) == self.selected_user_id for user in users):
                self.selected_user_id = str(users[0].get("id", ""))
        image = self.renderer.render(
            self.page,
            self.state.get(),
            self.enrollment.get(),
            self.local_id,
            self.local_name,
            users,
            self.selected_user_id,
            self.delete_confirm,
            self.editing_field,
            self.show_local_values,
        )
        hdmi = image.resize((HDMI_WIDTH, HDMI_HEIGHT), RESAMPLE_BILINEAR)
        self._frame[:] = np.asarray(hdmi, dtype=np.uint8)
        self._frame.flush()
        self._channel.setframe(self._frame)

    def _render_loop(self) -> None:
        last_key: Optional[Tuple[Any, ...]] = None
        while not self._stop.is_set():
            state = self.state.get()
            enrollment = self.enrollment.get()
            key = (
                self.page,
                state.get("revision"),
                enrollment.get("revision"),
                self.local_id,
                self.local_name,
                self.selected_user_id,
                self.delete_confirm,
                self.editing_field,
                self.show_local_values,
            )
            if key != last_key or self._dirty.is_set():
                # Pre-render at the panel's native aspect ratio, then transport
                # it through the supported 1280x720 HDMI timing.
                self._render_current()
                last_key = key
                self._dirty.clear()
            self._stop.wait(0.08)

    def _touch_loop(self) -> None:
        raw_x = raw_y = None
        with self.touch_path.open("rb", buffering=0) as stream:
            while not self._stop.is_set():
                readable, _, _ = select.select([stream], [], [], 0.25)
                if not readable:
                    continue
                payload = stream.read(EVENT.size)
                if len(payload) != EVENT.size:
                    continue
                _sec, _usec, kind, code, value = EVENT.unpack(payload)
                if kind == EV_ABS and code == ABS_X:
                    raw_x = value
                elif kind == EV_ABS and code == ABS_Y:
                    raw_y = value
                elif kind == EV_KEY and code == BTN_TOUCH and value == 0 and raw_x is not None and raw_y is not None:
                    self._tap(*map_touch(raw_x, raw_y, self.touch_max_x, self.touch_max_y))

    def _tap(self, x: int, y: int) -> None:
        try:
            if self.page == "recognize":
                if 20 <= x <= 230 and 408 <= y <= 479:
                    self.page = "enroll"
                    self.show_local_values = True
                    self._dirty.set()
                elif 250 <= x <= 470 and 408 <= y <= 479:
                    self.controller.start_recognition({})
                elif 140 <= x <= 425 and 345 <= y <= 400:
                    threshold = max(0.0, min(1.0, (x - 150) / 260.0))
                    self.state.update({"identity": {"threshold": round(threshold, 2)}})
            elif self.page == "enroll":
                if self.editing_field:
                    key = keyboard_key_at(x, y, self.editing_field)
                    if key is None:
                        return
                    attribute = "local_name" if self.editing_field == "name" else "local_id"
                    value = str(getattr(self, attribute))
                    if key == "CANCEL":
                        setattr(self, attribute, self._edit_original)
                        self.editing_field = ""
                    elif key == "CLEAR":
                        setattr(self, attribute, "")
                    elif key == "BACKSPACE":
                        setattr(self, attribute, value[:-1])
                    elif key == "DONE":
                        if value.strip():
                            setattr(self, attribute, value.strip())
                            self.editing_field = ""
                    elif len(value) < 24:
                        setattr(self, attribute, value + key)
                    self._dirty.set()
                    return
                if 118 <= x <= 330 and 78 <= y <= 122:
                    self.editing_field = "name"
                    self._edit_original = self.local_name
                    self.show_local_values = True
                    self._dirty.set()
                elif 118 <= x <= 330 and 138 <= y <= 182:
                    self.editing_field = "id"
                    self._edit_original = self.local_id
                    self.show_local_values = True
                    self._dirty.set()
                elif 20 <= x <= 245 and 398 <= y <= 479:
                    self.page = "recognize"
                    self._dirty.set()
                elif 20 <= x <= 330 and 315 <= y <= 382:
                    self.page = "users"
                    self.delete_confirm = False
                    self._dirty.set()
                elif 270 <= x <= 775 and 398 <= y <= 479:
                    current = self.enrollment.get()
                    if current.get("status") not in ("recording", "processing"):
                        name = self.local_name.strip()
                        user_id = self.local_id.strip()
                        self.controller.start_enrollment({"name": name, "id": user_id})
                        self.show_local_values = False
                        self.local_id = self._new_local_id()
            elif self.page == "users":
                if 18 <= x <= 190 and 405 <= y <= 479:
                    self.page = "enroll"
                    self.delete_confirm = False
                    self.show_local_values = True
                    self._dirty.set()
                elif 205 <= x <= 375 and 405 <= y <= 479:
                    self.page = "recognize"
                    self.delete_confirm = False
                    self._dirty.set()
                elif 650 <= x <= 799 and 405 <= y <= 479:
                    self.delete_confirm = False
                    self._dirty.set()
                elif 505 <= x <= 635 and 405 <= y <= 479 and self.selected_user_id:
                    if self.delete_confirm:
                        self.controller.delete_user({"id": self.selected_user_id})
                        self.selected_user_id = ""
                        self.delete_confirm = False
                    else:
                        self.delete_confirm = True
                    self._dirty.set()
                elif 18 <= x <= 472 and 72 <= y <= 344:
                    users = list(self.controller.list_users().get("users", []))[:4]
                    index = (y - 72) // 68
                    if 0 <= index < len(users):
                        self.selected_user_id = str(users[index].get("id", ""))
                        self.delete_confirm = False
                        self._dirty.set()
        except Exception as exc:
            if self.page == "enroll":
                self.enrollment.update({"status": "fault", "message": f"{type(exc).__name__}: {exc}"})
            else:
                self.state.update({"phase": "fault", "headline": "启动失败", "message": f"{type(exc).__name__}: {exc}"})

    def close(self) -> None:
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=1.0)
        if self._channel is not None:
            self._channel.stop()
        if self._display is not None:
            self._display.stop()

