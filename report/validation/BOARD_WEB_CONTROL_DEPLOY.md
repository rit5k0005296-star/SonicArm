# V9 电脑网页控制注册与识别：板端更新说明

本版本把 `UI/v4` 和 TC-ResNet3 接入常驻板端业务服务。电脑浏览器只发送开始录入/开始识别请求；PYNQ负责录音、CAM++声纹和PS端TC-ResNet3。机械臂串口继续禁用。

## 1. 保留目录

不要覆盖或删除：

```text
/home/xilinx/jupyter_notebooks/SonicArm/test_1/fpga_v8/
/home/xilinx/jupyter_notebooks/SonicArm/test_1/tc_resnet2_ps/
/home/xilinx/jupyter_notebooks/SonicArm/test_1/integration_v9/data/
/home/xilinx/jupyter_notebooks/SonicArm/test_1/integration_v9/results/
```

`app.py`启动时只加载一次匹配的FPGA-10 `fpga10_audio_hdmi.bit/.hwh`，并在同一进程内持有音频、声纹、短语识别、HDMI/VDMA与触控。实体屏和网页按钮都不会重新下载Overlay，也不需要Vivado重新综合。

## 2. 更新前停止旧进程

关闭正在使用V8 Overlay或音频Codec的Notebook内核；在运行旧UI服务的终端按 `Ctrl+C`。确认8080端口没有旧服务：

```bash
ss -ltnp | grep ':8080' || true
```

如有输出，只结束其中明确属于旧 `ui/server.py` 的PID，不要批量结束其他Python进程。

## 3. 从Windows复制文件

在Windows PowerShell执行：

```powershell
$src = 'C:\Users\Lenovo\Desktop\SonicArm\integration_v9'
$dst = '\\192.168.2.99\xilinx\jupyter_notebooks\SonicArm\test_1\integration_v9'

Copy-Item -LiteralPath "$src\app.py" -Destination "$dst\app.py" -Force
Copy-Item -LiteralPath "$src\board_runtime.py" -Destination "$dst\board_runtime.py" -Force
Copy-Item -LiteralPath "$src\controller.py" -Destination "$dst\controller.py" -Force
Copy-Item -LiteralPath "$src\diagnose_audio_run.py" -Destination "$dst\diagnose_audio_run.py" -Force
Copy-Item -LiteralPath "$src\v9_audio.py" -Destination "$dst\v9_audio.py" -Force
Copy-Item -LiteralPath "$src\v9_core.py" -Destination "$dst\v9_core.py" -Force
Copy-Item -LiteralPath "$src\config.json" -Destination "$dst\config.json" -Force
Copy-Item -Path "$src\tc_resnet3_ps" -Destination "$dst" -Recurse -Force
Copy-Item -Path "$src\ui\*" -Destination "$dst\ui" -Recurse -Force
Copy-Item -Path "$src\tests\*.py" -Destination "$dst\tests" -Force
```

上述命令不会删除板端 `data/` 和 `results/`。不要把整个板端 `integration_v9` 目录先删除再复制。

## 4. 板端只读预检

```bash
cd /home/xilinx/jupyter_notebooks/SonicArm/test_1/integration_v9
/usr/local/share/pynq-venv/bin/python3 -m py_compile app.py board_runtime.py controller.py native_display.py diagnose_audio_run.py ui/server.py
python3 tc_resnet3_ps/tc_resnet3_selftest.py
python3 -m unittest discover -s tests -v
test -f /home/xilinx/jupyter_notebooks/SonicArm/test_1/fpga_v8/cam_v8_audio.bit
test -f /home/xilinx/jupyter_notebooks/SonicArm/test_1/fpga_v8/cam_v8_audio.hwh
test -f /home/xilinx/jupyter_notebooks/SonicArm/test_1/ui_audio_voiceprint/assets/frontend_constants.npz
```

最后三个 `test -f` 无输出且返回码为0才表示文件存在。自检不加载Overlay。

## 5. 启动顺序

1. PYNQ启动时不要插耳麦。
2. 等待Linux和Jupyter完全启动。
3. 插入HP+MIC耳麦。
4. 关闭此前占用Overlay/Codec的Notebook内核。
5. 在板端终端启动唯一服务：

```bash
cd /home/xilinx/jupyter_notebooks/SonicArm/test_1/integration_v9
/usr/local/share/pynq-venv/bin/python3 app.py --host 0.0.0.0 --port 8080
```

出现以下三类信息后再打开网页：

```text
FPGA-10 Overlay, HDMI/VDMA, touch, codec, CAM++ and TC-ResNet3 initialized once
SonicArm UI v4 debug mirror: http://0.0.0.0:8080
Dry-run gate active: no serial command can be sent
```

电脑浏览器访问：

```text
http://192.168.2.99:8080/
```

## 6. 首次跑通步骤

1. 注册页填写姓名和仅含字母、数字、`-`、`_`的用户编号，例如 `SA-002`。
2. 点击“开始录入”。按照页面提示依次完成2秒安静基线和三段4秒语音。
3. 页面显示三段已录入后，模板应位于：

```text
integration_v9/data/users/SA-002/profile.npy
integration_v9/data/users/SA-002/profile.json
```

4. 点击“完成并进入识别”。
5. 点击“开始识别”。注册后5分钟内会复用最近静音基线，直接倒计时录制4秒完整命令；服务重启、没有缓存或缓存超过5分钟时，才会先重新采集2秒静音。
6. 页面应先显示声纹结果；只有声纹超过当前滑杆阈值才执行TC-ResNet3并显示短语。3秒录音会由TC-ResNet3前端裁剪有效语音并补零到5.2秒模型窗口。
7. 注册页可进入“用户管理”，列表读取板端真实 `data/users`；删除前会确认编号和姓名，录入或识别忙碌时拒绝删除，成功后移入 `data/deleted_users/` 可恢复目录。
8. 结果文件位于 `integration_v9/results/enroll_*` 和 `integration_v9/results/recognize_*`。

## 7. 当前安全边界

- `dry_run=true`，`kws_execution_enabled=false`。
- 代码没有打开串口，也不会向机械臂发送动作。
- 声纹阈值0.67和短语阈值0.80仍未正式校准。
- 削波门限暂按实测从0.1%放宽到2.0%，只用于当前联调，后续仍需结合更多现场录音复核。
- 图片仍只在浏览器本地预览，尚未上传和持久化。
- 该阶段只验证电脑浏览器控制，不证明PYNQ HDMI实体屏链路。

## 8. 常见故障

- `Address already in use`：8080端口仍被旧UI服务占用。
- `live web control must run on PYNQ ARM Linux`：误在Windows运行了真实 `app.py`。
- `V8 bit/HWH identity mismatch`：板端bit/HWH不是此前已验证配对，停止测试，不要绕过哈希。
- `audio gate failed`：本段不会写入模板；检查耳麦插入时机、距离、音量和环境噪声后重试。
- `no web-enrolled voiceprint profile`：先完成网页三段注册。
- 页面显示离线：确认 `app.py` 仍在运行且电脑可访问 `http://192.168.2.99:8080/api/health`。

新版每段最多自动重录3次，并在页面显示实际失败指标。分析已经保存的最近一次录音可执行：

```bash
cd /home/xilinx/jupyter_notebooks/SonicArm/test_1/integration_v9
latest=$(ls -dt results/enroll_* | head -n 1)
python3 diagnose_audio_run.py "$latest"
```

先根据输出判断是 `speech_over_quiet_db`、`rms_dbfs` 还是 `clip_percent` 失败，不要在没有测量数据时直接降低全部门限。

