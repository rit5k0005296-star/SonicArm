# SonicArm 从零复现指南

本文给出从全新 Windows 开发环境到 PYNQ-Z2 运行 SonicArm 的完整操作顺序。所有命令均从仓库根目录执行；建议把仓库放在纯英文短路径，例如 `C:\work\SonicArm`。

## 1. 复现目标

完成本指南后，应得到以下结果：

1. 电脑端 28 项回归测试全部通过；
2. 获得匹配的 `fpga10_audio_hdmi.bit` 与 `fpga10_audio_hdmi.hwh`；
3. 生成包含 PS 程序、模型运行时、Overlay、字体、界面和校验清单的板端目录；
4. 在 PYNQ-Z2 上启动 FPGA-10 Overlay、HDMI/VDMA、触摸、音频、CAM++、TC-ResNet3 和机械臂控制服务；
5. 完成身份通过、身份拒绝、正确指令、错误指令、复位和动作执行检查。

## 2. 硬件与软件准备

### 2.1 硬件

- PYNQ-Z2（`xc7z020clg400-1`）；
- 写入 PYNQ 3.0.1 镜像的 SD 卡；
- PYNQ 独立 12 V 圆孔电源，电源选择跳帽置于 `REG`；
- 有线耳机麦克风，接入 PYNQ-Z2 音频接口；
- HDMI 触控屏：HDMI 接 PYNQ HDMI OUT，触摸 USB 接 PYNQ USB-A Host，显示屏独立供电；
- 机械臂及原配独立电源，控制板通过 USB-UART 接入 PYNQ；
- 电脑与 PYNQ 的网线或 USB 转网口连接。

机械臂、显示屏和 PYNQ 分别使用匹配的独立电源。首次启动前清空机械臂运动范围，并保证可以立即断电。

### 2.2 电脑软件

- Windows 11 与 PowerShell 5.1 或更新版本；
- Python 3.10 或更新版本；
- Git；
- Vivado 2025.2 / Vitis 2025.2；
- PYNQ 3.0.1 官方源码中的 `boards/ip` 目录，用于 FPGA-10 工程内的 `axi_dynclk`、`rgb2dvi`、`color_swap`、`pixel_unpack` 和 `color_convert` IP。

安装仓库的电脑端 Python 依赖：

```powershell
cd C:\work\SonicArm
python -m pip install -r .\requirements.txt
python --version
```

## 3. 获取源码并检查目录

```powershell
git clone https://github.com/rit5k0005296-star/SonicArm.git C:\work\SonicArm
cd C:\work\SonicArm
git status --short
```

提交压缩包可直接解压到 `C:\work\SonicArm`。仓库根目录至少应包含：

```text
README.md  requirements.txt  src  sim  build  board  report  skill
```

GitHub 版本的 BIT/HWH 作为发布附件提供。将以下两个文件放入 `board/artifacts/`：

```text
fpga10_audio_hdmi.bit
fpga10_audio_hdmi.hwh
```

提交压缩包已经包含这组文件，也可以按第 5 节从源码重新生成。

## 4. 电脑端回归测试

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\sim\run_tests.ps1
```

预期结尾：

```text
Ran 28 tests
OK
```

随后检查正式 Overlay 文件哈希：

```powershell
Get-FileHash .\board\artifacts\fpga10_audio_hdmi.bit -Algorithm SHA256
Get-FileHash .\board\artifacts\fpga10_audio_hdmi.hwh -Algorithm SHA256
Get-Content .\board\artifacts\SHA256.json
```

正式发布配对为：

```text
bit  82ff1d058923f019236a10a13650cd1c4c6a1915ae747c2ebb121e9cdc67054d
hwh  af4d2dfbae3e69125c608378fbe07323fe5f43551ee74b3c3ed8ba95e95f6681
```

## 5. 从源码重建 FPGA-10

只使用发布附件时可以跳到第 6 节。需要重建时，把 PYNQ 3.0.1 源码中的 `boards/ip` 设为 `PYNQ_IP_ROOT`，把 Vivado 2025.2 可执行文件设为 `VIVADO_BIN`：

```powershell
$env:VIVADO_BIN = "C:\AMDDesignTools\2025.2\Vivado\bin\vivado.bat"
$env:PYNQ_IP_ROOT = "C:\work\PYNQ-3.0.1\boards\ip"

Test-Path $env:VIVADO_BIN
Test-Path "$env:PYNQ_IP_ROOT\axi_dynclk_v1_0\component.xml"
Test-Path "$env:PYNQ_IP_ROOT\rgb2dvi_v1_2\component.xml"
```

三个检查均应返回 `True`。创建工程并完成综合、实现、布线、时序分析和 bitstream 生成：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build\tcl\run_create_project.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build\tcl\run_build.ps1
```

主要输出：

```text
build/vivado/fpga10_audio_hdmi/fpga10_audio_hdmi.xpr
build/export/fpga10_audio_hdmi.bit
build/export/fpga10_audio_hdmi.hwh
build/reports/impl_timing_summary.rpt
build/reports/impl_utilization.rpt
build/reports/impl_drc.rpt
build/reports/impl_route_status.rpt
```

检查构建结果：

```powershell
Select-String -Path .\build\reports\impl_timing_summary.rpt -Pattern "WNS|TNS|WHS|THS"
Select-String -Path .\build\reports\impl_route_status.rpt -Pattern "Fully Routed"
Get-FileHash .\build\export\fpga10_audio_hdmi.bit -Algorithm SHA256
Get-FileHash .\build\export\fpga10_audio_hdmi.hwh -Algorithm SHA256
```

使用新构建版本部署时，将 `build/export/` 中的 BIT/HWH 复制到 `board/artifacts/`，保持文件名一致，并同步更新 `board/artifacts/SHA256.json` 与 `src/ps/config.json` 中的 `expected_sha256`。

## 6. 生成板端运行目录

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build\scripts\build_board_package.ps1
```

脚本会在 `board/generated/fpga_10_<时间戳>/` 生成完整目录，并写入 `SHA256_MANIFEST.json`。确认关键文件存在：

```powershell
$pkg = Get-ChildItem .\board\generated -Directory -Filter "fpga_10_*" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

Test-Path "$($pkg.FullName)\app.py"
Test-Path "$($pkg.FullName)\config.json"
Test-Path "$($pkg.FullName)\fpga10_audio_hdmi.bit"
Test-Path "$($pkg.FullName)\fpga10_audio_hdmi.hwh"
Test-Path "$($pkg.FullName)\tc_resnet3_ps\model_weights.npz"
Test-Path "$($pkg.FullName)\SHA256_MANIFEST.json"
```

以上检查均应返回 `True`。

## 7. 配置电脑与 PYNQ 网络

本项目固定使用：

| 设备 | IPv4 地址 | 子网掩码 |
| --- | --- | --- |
| 电脑以太网口 | `192.168.2.100` | `255.255.255.0` |
| PYNQ-Z2 | `192.168.2.99` | `255.255.255.0` |

默认网关和 DNS 留空。PYNQ 上电并完成启动后，在电脑执行：

```powershell
ping 192.168.2.99
Test-NetConnection 192.168.2.99 -Port 9090
Test-NetConnection 192.168.2.99 -Port 445
```

Jupyter 地址为 `http://192.168.2.99:9090`，默认账户为 `xilinx`。需要查看串口启动信息时：

```powershell
python -m serial.tools.miniterm COM8 115200
```

将 `COM8` 替换为设备管理器中实际出现的串口号。

## 8. 复制板端目录

在文件资源管理器地址栏输入：

```text
\\192.168.2.99\xilinx\jupyter_notebooks
```

若 Windows 要求重新认证：

```powershell
net use \\192.168.2.99\IPC$ /user:xilinx *
```

把第 6 节生成目录中的全部内容复制到：

```text
\\192.168.2.99\xilinx\jupyter_notebooks\SonicArm\test_1\fpga_10
```

复制完成后，通过 Jupyter Terminal 进入目录：

```bash
cd /home/xilinx/jupyter_notebooks/SonicArm/test_1/fpga_10
```

校验 Python 文件和模型自检：

```bash
/usr/local/share/pynq-venv/bin/python3 -m py_compile \
  app.py board_runtime.py controller.py native_display.py \
  arm_integration.py diagnose_audio_run.py ui/server.py

/usr/local/share/pynq-venv/bin/python3 tc_resnet3_ps/tc_resnet3_selftest.py
```

## 9. 接线与启动顺序

1. PYNQ 断电，机械臂断电，显示屏断电；
2. 耳机麦克风接入 PYNQ 音频接口；
3. PYNQ HDMI OUT 接显示屏 HDMI IN；
4. 显示屏触摸 USB 接 PYNQ USB-A Host，显示屏接独立 5 V/2 A 电源；
5. 机械臂控制板通过 USB-UART 接 PYNQ，机械臂使用原配电源；
6. 网线连接电脑和 PYNQ；
7. 先启动 PYNQ，系统就绪后再启动显示屏和机械臂电源；
8. 确认机械臂运动范围无人、无障碍物，再启动应用。

启动完整系统：

```bash
cd /home/xilinx/jupyter_notebooks/SonicArm/test_1/fpga_10
/usr/local/share/pynq-venv/bin/python3 -u app.py --host 0.0.0.0 --port 8080
```

正常启动日志依次出现：

```text
STARTUP 1/6 configuration loaded
STARTUP 2/8 loading FPGA-10 Overlay
STARTUP 3/8 Overlay ready
STARTUP 4/8 controller and shared state ready
STARTUP 5/8 initializing HDMI/VDMA and touch
STARTUP 6/8 first HDMI frame and touch thread ready
STARTUP 7/8 initializing audio, CAM++ and TC-ResNet3
STARTUP 8/8 audio, CAM++ and TC-ResNet3 ready
```

电脑调试页面：

```text
http://192.168.2.99:8080
```

## 10. 功能验收

按以下顺序执行，每项记录输入、识别结果和动作结果：

1. HDMI 显示：界面完整显示，分辨率与触摸映射正常；
2. 触摸输入：主页、注册页和用户页可切换；
3. 音频：安静环境采集与 3 秒语音采集正常；
4. 用户注册：录入用户并生成声纹模板；
5. 身份通过：已注册用户得分达到 `0.67`；
6. 身份拒绝：未注册用户被拒绝；
7. 指令识别：普通动作指令达到 `0.85`，`松开` 和 `复位` 使用各自配置阈值；
8. 状态门控：身份通过且指令通过时才进入动作调度；
9. 机械臂：逐项检查复位、动作组、超时处理和停止流程；
10. 连续运行：重复执行身份和指令流程，确认界面、音频和动作状态同步更新。

按 `Ctrl+C` 停止服务，等待 HDMI、音频、Overlay 和机械臂接口完成关闭后再断电。

## 11. 常见问题

| 现象 | 检查方法 |
| --- | --- |
| `Vivado 2025.2 not found` | 设置 `VIVADO_BIN`，确认路径指向 `vivado.bat` |
| 找不到 `rgb2dvi` 或 `axi_dynclk` | 检查 `PYNQ_IP_ROOT` 是否指向 PYNQ 3.0.1 的 `boards/ip` |
| BIT/HWH 加载失败 | 确认两文件同名、位于板端目录根部，并核对 SHA-256 |
| 无法访问 `192.168.2.99` | 检查电脑静态 IP、网线、板卡启动状态及 `ping` |
| Samba 打不开 | 执行 `net use` 重新认证，再访问 `\\192.168.2.99\xilinx` |
| Jupyter 打不开 | 检查 9090 端口和 `http://192.168.2.99:9090` |
| HDMI 无画面 | 检查 HDMI OUT、显示屏输入源、独立供电及启动日志第 5/6 步 |
| 触摸无响应 | 检查 USB HID 连接及 `/dev/input/event0` 是否存在 |
| 音频初始化失败 | 检查耳麦接口、音频设备占用和 `diagnose_audio_run.py` 输出 |
| 机械臂不动作 | 检查独立供电、USB-UART、控制板连接和应用启动日志 |

## 12. 结果位置

- FPGA 时序和资源报告：`build/reports/`；
- FPGA 导出产物：`build/export/`；
- 正式 Overlay：`board/artifacts/`；
- 生成的板端目录：`board/generated/`；
- 软件回归入口：`sim/run_tests.ps1`；
- 技术报告：`report/sonicarm_technical_report.pdf`；
- 系统验收索引：`report/validation/final_board_acceptance.md`；
- AI 协作记录：`report/ai_collaboration_report.md`。

本指南参考早期过程记录中的板卡启动、静态网络、Jupyter/Samba、Vivado 构建和单算子验证经验，并以当前 FPGA-10 源码、脚本、目录结构和正式配置重新整理。
