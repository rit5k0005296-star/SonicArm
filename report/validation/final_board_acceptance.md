# 最终板端验收索引

本页是 SonicArm 提交工程的统一验收入口。它区分电脑端构建、离线测试、已有板端记录与仍需操作者完成的现场检查，避免把软件调度成功等同于机械臂物理动作成功。

## 1. 固定配置

- 目标板卡：PYNQ-Z2
- FPGA 器件：`xc7z020clg400-1`
- 工具版本：Vivado / Vitis 2025.2
- PL 主时钟：100 MHz
- 正式 Overlay：FPGA-10

## 2. 电脑端干净构建（2026-11-02）

在纯英文短路径映射下，从 `build/tcl/create_fpga10.tcl` 创建工程，并由 `build/tcl/build_fpga10.tcl` 完成综合、实现、布线、静态时序报告与 bitstream 生成。构建退出码为 0。

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| Vivado | v2025.2，Build 6299465 | `build/reports/project_creation.txt`、各综合/实现报告 |
| 器件 | `xc7z020clg400-1` | `build/reports/impl_drc.rpt` |
| 布线 | 50,229/50,229 可布线网络完全布线，0 routing error | `build/reports/impl_route_status.rpt` |
| Setup | WNS +0.324 ns，TNS 0 ns，0 failing endpoint | `build/reports/impl_timing_summary.rpt` |
| Hold | WHS +0.015 ns，THS 0 ns，0 failing endpoint | `build/reports/impl_timing_summary.rpt` |
| DRC | Fully Routed；0 Error，141 Warning 检查项 | `build/reports/impl_drc.rpt` |
| 资源 | LUT 26,250/53,200；FF 30,968/106,400；BRAM 88/140；DSP 111/220 | `build/reports/impl_utilization.rpt` |
| 导出产物 | BIT 与 HWH 均已生成 | `build/export/` |

干净构建导出文件的 SHA-256：

```text
EFC32D08886FD413076480DB8864BCC0207B837AB2B85CC69D6106CEA15E6E33  build/export/fpga10_audio_hdmi.bit
E5E2FF6224F224033538418DC2A8A601883BB10357A1A0A86C132E4E106C76A4  build/export/fpga10_audio_hdmi.hwh
```

Vivado 方法学报告仍记录 HDMI `rgb2dvi` 生成时钟相关的 `TIMING-4/27/36`，以及外部音频/HPD 端口缺少板级 I/O delay 的 `TIMING-18`。这些项目不影响本次 bitstream 生成和已约束路径的正时序余量，但意味着不能把“所有外部接口均完成板级时序签核”作为结论；详见 `build/reports/impl_methodology.rpt` 与 `build/reports/impl_check_timing.rpt`。

## 3. 正式板端部署产物

`board/artifacts/` 保留已有板端记录所对应的正式 BIT/HWH 配对，不以本次未上板的重构建产物自动替换：

```text
82FF1D058923F019236A10A13650CD1C4C6A1915AE747C2EBB121E9CDC67054D  board/artifacts/fpga10_audio_hdmi.bit
AF4D2DFBAE3E69125C608378FBE07323FE5F43551EE74B3C3ED8BA95E95F6681  board/artifacts/fpga10_audio_hdmi.hwh
```

部署前以 `board/artifacts/SHA256.json` 校验二者，随后运行 `build/scripts/build_board_package.ps1` 生成完整板端目录。增量补丁仅用于已有基线，具体路径见 `board/deploy/README.md`。

## 4. 软件与历史板端证据

- 电脑端离线回归：28/28 通过，入口为 `sim/run_tests.ps1`。
- HDMI 彩条与触控外设的既有实板记录：见 `report/validation/FPGA10_STATUS_20261027.md`。
- 详细系统测试、声纹/KWS 指标与实现说明：见 `report/sonicarm_technical_report.pdf`。
- 大模型协作记录：见 `report/ai_collaboration_report.md`。

离线测试、HTTP 回环或动作指令下发成功不等于机械臂已经完成物理动作；板端历史记录也不替代提交现场的最终复核。

## 5. 现场最终验收顺序

1. 校验 `board/artifacts/SHA256.json`，确认 BIT/HWH 为同一正式配对。
2. 按 `build/README.md` 生成板端目录，并按 `board/README.md` 手动部署。
3. 上电后确认 Overlay 加载、音频采集、HDMI 显示和触控输入正常。
4. 使用固定测试语音分别验证声纹通过/拒绝与 KWS 正确/错误分支。
5. 清空机械臂运动范围，在急停可用的条件下逐项验证动作组、复位与拒绝门控。
6. 保存现场日志、输入编号、预测结果、动作完成情况与异常说明；物理动作完成必须由人工观察确认。

完成上述现场步骤后，才可对特定提交产物声明板端整机验收通过。
