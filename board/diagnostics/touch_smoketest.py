#!/usr/bin/env python3
"""Read raw Linux input events from the FPGA-10 USB touch screen."""

from __future__ import annotations

import argparse
import fcntl
import struct
import time
from pathlib import Path


EV_SYN = 0x00
EV_KEY = 0x01
EV_ABS = 0x03
SYN_REPORT = 0x00
BTN_TOUCH = 0x14A

ABS_NAMES = {
    0x00: "ABS_X",
    0x01: "ABS_Y",
    0x2F: "ABS_MT_SLOT",
    0x35: "ABS_MT_POSITION_X",
    0x36: "ABS_MT_POSITION_Y",
    0x39: "ABS_MT_TRACKING_ID",
}

CALIBRATION_POINTS = (
    "左上角",
    "右上角",
    "左下角",
    "右下角",
    "屏幕中心",
)


def abs_info(stream, code: int) -> tuple[int, int, int, int, int, int]:
    payload = bytearray(struct.calcsize("iiiiii"))
    request = 0x80000000 | (len(payload) << 16) | (ord("E") << 8) | (0x40 + code)
    fcntl.ioctl(stream.fileno(), request, payload, True)
    return struct.unpack("iiiiii", payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("device", nargs="?", default="/dev/input/event0")
    parser.add_argument("--calibrate", action="store_true")
    args = parser.parse_args()
    device = Path(args.device)
    if not device.exists():
        raise FileNotFoundError(device)

    event_struct = struct.Struct("llHHI")
    x = y = None
    touching = False
    released = False
    with device.open("rb", buffering=0) as stream:
        for code, name in ((0x00, "ABS_X"), (0x01, "ABS_Y")):
            try:
                _value, minimum, maximum, fuzz, flat, resolution = abs_info(stream, code)
                print(
                    f"AXIS_RANGE {name} min={minimum} max={maximum} "
                    f"fuzz={fuzz} flat={flat} resolution={resolution}"
                )
            except OSError as exc:
                print(f"AXIS_RANGE {name} unavailable={exc}")
        print(f"TOUCH_SMOKETEST_RUNNING device={device} event_size={event_struct.size}")
        if args.calibrate:
            point_index = 0
            print(f"CALIBRATE 请点击：{CALIBRATION_POINTS[point_index]}", flush=True)
        else:
            point_index = -1
            print("Touch the four corners and center; press Ctrl-C to stop.", flush=True)

        while True:
            payload = stream.read(event_struct.size)
            if len(payload) != event_struct.size:
                raise RuntimeError(f"short input event: {len(payload)} bytes")
            _sec, _usec, event_type, code, value = event_struct.unpack(payload)
            if event_type == EV_ABS:
                name = ABS_NAMES.get(code, f"ABS_0x{code:02x}")
                if code in (0x00, 0x35):
                    x = value
                elif code in (0x01, 0x36):
                    y = value
                elif code == 0x39:
                    touching = value != 0xFFFFFFFF
                print(f"{name}={value}", flush=True)
            elif event_type == EV_KEY and code == BTN_TOUCH:
                touching = bool(value)
                released = value == 0
                print(f"BTN_TOUCH={value}", flush=True)
            elif event_type == EV_SYN and code == SYN_REPORT:
                print(f"SYN_REPORT x={x} y={y} touching={int(touching)}", flush=True)
                if args.calibrate and released and x is not None and y is not None:
                    released = False
                    label = CALIBRATION_POINTS[point_index]
                    print(f"CAL_POINT label={label} x={x} y={y}", flush=True)
                    point_index += 1
                    if point_index == len(CALIBRATION_POINTS):
                        print("CALIBRATION_COMPLETE", flush=True)
                        return 0
                    time.sleep(0.4)
                    print(f"CALIBRATE 请点击：{CALIBRATION_POINTS[point_index]}", flush=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nTOUCH_SMOKETEST_STOPPED")
