# FPGA-8A: V7 + PYNQ-Z2 HP+MIC

本目录只创建 FPGA-8A Vivado 工程：复用已验证的 `unified_v7` IP，并加入 PYNQ-Z2 ADAU1761 音频控制通路。当前版本不包含 HDMI，不执行综合、实现或 bitstream 生成。

目标器件为 `xc7z020clg400-1`，工具为 Vivado 2025.2，V7 PL 时钟保持 100 MHz。

创建命令：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_create_project.ps1
```

成功后工程位于：

```text
vivado/v8_audio_final/v8_audio.xpr
```

创建阶段证据位于 `reports/project_creation.txt`。只有 `validated=true`，且工程中存在 `unified_0`、`audio_codec_ctrl_0`、三个 HP 内存互连和音频 XDC，才算工程创建完成。该状态不代表综合、时序、bitstream 或板端验证通过。

音频 IP 与引脚约束来自 Xilinx/PYNQ `v3.0.1`，固定提交 `93ddd21ab623883590a8c8b07f0b157b2855da4b`。
