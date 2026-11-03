#!/usr/bin/env python3
"""Start the single-owner FPGA-10 audio, inference, HDMI, touch and web runtime."""
from __future__ import annotations

import argparse
import json
from http.server import ThreadingHTTPServer
from pathlib import Path

from board_runtime import BoardRuntime
from controller import SonicArmController
from native_display import NativeDisplayRuntime
from ui import server as ui_server


ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    config = json.loads(args.config.resolve().read_text(encoding="utf-8"))
    if not config["decision"]["dry_run"] or config["decision"]["kws_execution_enabled"]:
        raise RuntimeError("web-control validation must remain dry-run with execution disabled")

    print("STARTUP 1/6 configuration loaded", flush=True)
    print("STARTUP 2/8 loading FPGA-10 Overlay", flush=True)
    hardware = BoardRuntime(ROOT, config, defer_runtime=True)
    print("STARTUP 3/8 Overlay ready; reserving HDMI framebuffer before inference buffers", flush=True)
    controller = SonicArmController(
        ROOT,
        config,
        hardware,
        ui_server.STATE,
        ui_server.ENROLLMENT,
    )
    ui_server.configure_control_backend(controller)
    print("STARTUP 4/8 controller and shared state ready", flush=True)
    ui_server.STATE.update(
        {
            "mode": "FPGA-10本地显示联调（禁止动作）",
            "identity": {
                "threshold": float(config["decision"]["identity_threshold"]),
                "threshold_calibrated": bool(config["decision"]["identity_threshold_calibrated"]),
            },
            "connections": {
                "microphone": True,
                "voiceprint": True,
                "arm_serial": False,
                "display": False,
            },
        }
    )
    display = None
    server = None
    try:
        display = NativeDisplayRuntime(
            ROOT, config, hardware.overlay, controller, ui_server.STATE, ui_server.ENROLLMENT
        )
        print("STARTUP 5/8 initializing HDMI/VDMA and touch", flush=True)
        display.start()
        print("STARTUP 6/8 first HDMI frame and touch thread ready", flush=True)
        ui_server.STATE.update({"connections": {"display": True}})
        print("STARTUP 7/8 initializing audio, CAM++ and TC-ResNet3", flush=True)
        hardware.initialize_runtime()
        print("STARTUP 8/8 audio, CAM++ and TC-ResNet3 ready", flush=True)
        server = ThreadingHTTPServer((args.host, args.port), ui_server.SonicArmHandler)
        print("FPGA-10 Overlay, HDMI/VDMA, touch, codec, CAM++ and TC-ResNet3 initialized once", flush=True)
        print(f"SonicArm UI v4 debug mirror: http://{args.host}:{args.port}", flush=True)
        print("Dry-run gate active: no serial command can be sent", flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if server is not None:
            server.server_close()
        if display is not None:
            display.close()
        hardware.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
