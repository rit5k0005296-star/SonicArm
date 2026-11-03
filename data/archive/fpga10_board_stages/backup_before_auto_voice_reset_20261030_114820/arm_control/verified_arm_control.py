"""CH340 arm-controller interface extracted from the validated board notebook.

Motion groups must already be present in the arm controller.  This module never downloads
or overwrites INI/group data and never retries a timed-out movement.
"""
from __future__ import annotations

import glob
import threading
import time
from typing import Optional

import serial


BAUDRATE = 115200
PROBE_COMMAND = b"$GETA!"
PROBE_RESPONSE = b"AAA"
GROUP_DONE = b"@GroupDone!"

PICK_ACTIONS = {
    (1, 1): ("$DGT:1-2,1!", 10.0),
    (1, 2): ("$DGT:3-4,1!", 8.0),
    (2, 1): ("$DGT:5-6,1!", 9.0),
    (2, 2): ("$DGT:7-8,1!", 9.0),
}
PLACE_RIGHT = ("$DGT:9-13,1!", 25.0)
RESET_UPRIGHT = "$DGT:14-14,1!"

ser: Optional[serial.Serial] = None
arm_state = "UNKNOWN"
picked_cell = None
_lock = threading.Lock()


def _open_candidate(port: str) -> serial.Serial:
    return serial.Serial(
        port=port,
        baudrate=BAUDRATE,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=0.1,
        write_timeout=1.0,
        rtscts=False,
        dsrdtr=False,
    )


def _probe(candidate: serial.Serial) -> bool:
    candidate.reset_input_buffer()
    candidate.write(PROBE_COMMAND)
    candidate.flush()
    time.sleep(0.5)
    return PROBE_RESPONSE in candidate.read_all()


def initialize_arm() -> None:
    """Select the CH340 arm controller by protocol response, never by ttyUSB index."""
    global ser, arm_state, picked_cell
    with _lock:
        if ser is not None and ser.is_open:
            return
        errors = []
        for port in sorted(glob.glob("/dev/ttyUSB*")):
            candidate = None
            try:
                candidate = _open_candidate(port)
                time.sleep(2.0)
                if _probe(candidate):
                    ser = candidate
                    arm_state = "UNKNOWN"
                    picked_cell = None
                    print(f"机械臂控制板已连接：{port}")
                    return
            except BaseException as exc:
                errors.append(f"{port}: {type(exc).__name__}: {exc}")
            if candidate is not None:
                try:
                    candidate.close()
                except BaseException:
                    pass
        detail = "; ".join(errors) if errors else "no /dev/ttyUSB* devices"
        raise RuntimeError(f"arm controller probe failed: {detail}")


def close_arm() -> None:
    global ser
    with _lock:
        if ser is not None:
            try:
                ser.close()
            finally:
                ser = None


def _require_serial() -> serial.Serial:
    if ser is None or not ser.is_open:
        raise RuntimeError("arm controller serial is not initialized")
    return ser


def _controller_alive_unlocked(link: serial.Serial) -> bool:
    return _probe(link)


def _run_group_unlocked(link: serial.Serial, command: str, timeout: float) -> bool:
    if not command.startswith("$DGT:") or not command.endswith("!"):
        raise ValueError("invalid arm-controller DGT command")
    link.reset_input_buffer()
    link.write(command.encode("ascii"))
    link.flush()
    deadline = time.monotonic() + float(timeout)
    received = bytearray()
    while time.monotonic() < deadline:
        data = link.read(256)
        if data:
            received.extend(data)
            if GROUP_DONE in received:
                return True
        time.sleep(0.02)
    print(f"机械臂动作等待超时，禁止自动重发：{command}; received={bytes(received)!r}")
    return False


def arm_reset_upright() -> bool:
    global arm_state, picked_cell
    with _lock:
        link = _require_serial()
        # Startup and authenticated voice reset both use the verified upright
        # action group.  Repeated reset from READY is intentionally permitted.
        if arm_state == "BUSY":
            print(f"拒绝复位：当前状态为 {arm_state}")
            return False
        arm_state = "BUSY"
        link.reset_input_buffer()
        link.write(RESET_UPRIGHT.encode("ascii"))
        link.flush()
        time.sleep(3.0)
        if not _controller_alive_unlocked(link):
            arm_state = "FAULT"
            return False
        arm_state = "READY"
        picked_cell = None
        return True


def arm_pick(row: int, col: int) -> bool:
    global arm_state, picked_cell
    with _lock:
        link = _require_serial()
        key = (int(row), int(col))
        if arm_state != "READY" or key not in PICK_ACTIONS:
            print(f"拒绝夹取：state={arm_state}, cell={key}")
            return False
        arm_state = "BUSY"
        command, timeout = PICK_ACTIONS[key]
        if _run_group_unlocked(link, command, timeout):
            arm_state = "GRIPPED"
            picked_cell = key
            return True
        arm_state = "FAULT"
        return False


def arm_place_right() -> bool:
    global arm_state
    with _lock:
        link = _require_serial()
        if arm_state != "GRIPPED":
            print(f"拒绝右放：当前状态为 {arm_state}")
            return False
        arm_state = "BUSY"
        command, timeout = PLACE_RIGHT
        if _run_group_unlocked(link, command, timeout):
            arm_state = "PLACED"
            return True
        arm_state = "FAULT"
        return False


def arm_stop() -> None:
    global arm_state
    with _lock:
        link = _require_serial()
        link.write(b"$DST!")
        link.flush()
        arm_state = "FAULT"

