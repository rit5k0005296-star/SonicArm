#!/usr/bin/env python3
"""Start the single-owner FPGA-10 audio, inference, HDMI, touch and web runtime."""
from __future__ import annotations

import argparse
import json
from http.server import ThreadingHTTPServer
from pathlib import Path

from board_runtime import BoardRuntime
from arm_integration import ArmDispatcher, VerifiedArmBackend
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
    arm_config = config.get("arm", {})
    arm_enabled = bool(arm_config.get("execution_enabled", False))
    if arm_enabled and config["decision"]["dry_run"]:
        raise RuntimeError("arm execution requires decision.dry_run=false")
    if arm_enabled and not config["decision"]["kws_execution_enabled"]:
        raise RuntimeError("arm execution requires decision.kws_execution_enabled=true")

    print("STARTUP 1/6 configuration loaded", flush=True)
    print("STARTUP 2/8 loading FPGA-10 Overlay", flush=True)
    hardware = BoardRuntime(ROOT, config, defer_runtime=True)
    print("STARTUP 3/8 Overlay ready; reserving HDMI framebuffer before inference buffers", flush=True)
    arm_backend = None
    arm_error = ""
    if arm_enabled:
        try:
            module_path = Path(arm_config["verified_module_path"])
            if not module_path.is_absolute():
                module_path = ROOT / module_path
            arm_backend = VerifiedArmBackend(module_path)
            arm_backend.initialize()
        except BaseException as exc:
            arm_error = f"{type(exc).__name__}: {exc}"
            print(f"ARM backend unavailable; execution remains blocked: {arm_error}", flush=True)
    arm = ArmDispatcher(backend=arm_backend, enabled=arm_enabled and arm_backend is not None)
    controller = SonicArmController(
        ROOT,
        config,
        hardware,
        ui_server.STATE,
        ui_server.ENROLLMENT,
        arm=arm,
    )
    ui_server.configure_control_backend(controller)
    print("STARTUP 4/8 controller and shared state ready", flush=True)
    ui_server.STATE.update(
        {
            "mode": "SonicArm正式运行",
            "identity": {
                "threshold": float(config["decision"]["identity_threshold"]),
                "threshold_calibrated": bool(config["decision"]["identity_threshold_calibrated"]),
            },
            "connections": {
                "microphone": True,
                "voiceprint": True,
                "arm_serial": arm.connected,
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
        if arm.enabled and bool(arm_config.get("auto_reset_on_startup", False)):
            print("ARM STARTUP RESET requested; keep the workspace clear", flush=True)
            reset_status = controller.run_startup_arm_reset()
            if reset_status["state"] == "READY":
                print("ARM STARTUP RESET complete; state=READY", flush=True)
            else:
                print(
                    "ARM STARTUP RESET failed; "
                    f"state={reset_status['state']} error={reset_status['last_error']}",
                    flush=True,
                )
        server = ThreadingHTTPServer((args.host, args.port), ui_server.SonicArmHandler)
        print("FPGA-10 Overlay, HDMI/VDMA, touch, codec, CAM++ and TC-ResNet3 initialized once", flush=True)
        print(f"SonicArm UI v4 debug mirror: http://{args.host}:{args.port}", flush=True)
        if arm.enabled:
            voice_reset = bool(arm_config.get("voice_reset_enabled", False))
            print(
                f"Arm adapter ready; voice reset={'enabled' if voice_reset else 'disabled'}; "
                f"state={arm.status()['state']}",
                flush=True,
            )
        else:
            print(f"Arm execution disabled{': ' + arm_error if arm_error else ''}", flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if server is not None:
            server.server_close()
        if display is not None:
            display.close()
        hardware.close()
        if arm_backend is not None:
            arm_backend.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
