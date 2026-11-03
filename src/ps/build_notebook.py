#!/usr/bin/env python3
"""Generate the small operator notebook for manual PYNQ validation."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def markdown(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def code(text: str) -> dict:
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": text.splitlines(keepends=True)}


cells = [
    markdown("""# SonicArm V9 第一阶段软件预集成\n\n本 Notebook 使用既有 FPGA-8 Overlay，将同一段16 kHz录音送入 CAM++ 声纹和 PS TC-ResNet2，并更新网页 UI。\n\n**安全边界：不导入串口库、不打开串口、`execution_enabled=false`，机械臂应保持断开。**\n\n本阶段的电脑浏览器仅用于调试，不是最终显示验收。最终必须在FPGA-9同一Overlay下完成PYNQ HDMI实体屏与USB HID触摸验证。\n"""),
    code("""from pathlib import Path\nimport json, subprocess, sys, time\n\nHERE = Path.cwd().resolve()\nassert (HERE / 'run_validation.py').is_file(), '请在 integration_v9 目录打开本 Notebook'\nNAME = '张同学'\nUSER_ID = 'SA-002'\nprint('工作目录:', HERE)\nprint('请按实际人员修改 NAME 和 USER_ID；机械臂保持断开。')\n"""),
    markdown("""## 启动本地 UI\n\n若 UI 已经在8080端口运行，请不要重复执行本单元。\n"""),
    code("""ui_log = open(HERE / 'ui_server.log', 'a', encoding='utf-8')\nui_process = subprocess.Popen(\n    [sys.executable, str(HERE / 'ui' / 'server.py'), '--host', '0.0.0.0', '--port', '8080'],\n    cwd=str(HERE / 'ui'), stdout=ui_log, stderr=subprocess.STDOUT\n)\ntime.sleep(1.0)\nprint('UI PID:', ui_process.pid)\nprint('中间调试可访问 http://<PYNQ-IP>:8080/auth.html；这不构成最终实体屏验收')\n"""),
    markdown("""## 执行一轮集成验证\n\n依次采集2秒安静基线和5秒完整命令。身份通过后才运行短语模型，但任何结果都不会发送到机械臂。\n"""),
    code("""completed = subprocess.run(\n    [sys.executable, str(HERE / 'run_validation.py'), '--name', NAME, '--user-id', USER_ID],\n    cwd=str(HERE), text=True\n)\nprint('返回码:', completed.returncode)\nif completed.returncode != 0:\n    print('请查看 results/run_<时间>/result.json 和 ui_server.log')\n"""),
    markdown("""## 查看最新结果\n"""),
    code("""runs = sorted((HERE / 'results').glob('run_*'))\nassert runs, '尚无运行结果'\nlatest = runs[-1] / 'result.json'\nprint(latest)\nprint(latest.read_text(encoding='utf-8'))\n"""),
    markdown("""## 完成后停止 UI 服务\n"""),
    code("""if 'ui_process' in globals() and ui_process.poll() is None:\n    ui_process.terminate()\n    ui_process.wait(timeout=5)\nif 'ui_log' in globals() and not ui_log.closed:\n    ui_log.close()\nprint('UI服务已停止；Overlay不会在此单元重新加载。')\n"""),
]

notebook = {
    "cells": cells,
    "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python", "version": "3"}},
    "nbformat": 4,
    "nbformat_minor": 5,
}
(ROOT / "V9_integration_validation.ipynb").write_text(json.dumps(notebook, ensure_ascii=False, indent=1), encoding="utf-8")
