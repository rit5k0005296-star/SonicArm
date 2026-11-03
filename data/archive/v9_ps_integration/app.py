#!/usr/bin/env python3
"""Start the persistent V8 Overlay runtime and the UI v4 web controller."""
from __future__ import annotations

import argparse
import json
from http.server import ThreadingHTTPServer
from pathlib import Path

from board_runtime import BoardRuntime
from controller import SonicArmController
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

    hardware = BoardRuntime(ROOT, config)
    controller = SonicArmController(
        ROOT,
        config,
        hardware,
        ui_server.STATE,
        ui_server.ENROLLMENT,
    )
    ui_server.configure_control_backend(controller)
    ui_server.STATE.update(
        {
            "mode": "V9网页联调（禁止动作）",
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
    server = ThreadingHTTPServer((args.host, args.port), ui_server.SonicArmHandler)
    print("V8 Overlay, codec, CAM++ and TC-ResNet3 initialized once", flush=True)
    print(f"SonicArm UI v4: http://{args.host}:{args.port}", flush=True)
    print("Dry-run gate active: no serial command can be sent", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        hardware.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
