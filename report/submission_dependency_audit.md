# 源码包外部目录依赖审计

## 结论

正式运行入口、板端发布包、模型文件、FPGA bit/HWH、声纹运行时依赖和机械臂控制模块均已收进本源码目录。配置采用相对路径，复制整个 `SonicArm` 目录后不再要求保留原电脑上的 `test_1`、`fpga_v8`、`full_model_test`、`UI-AUDIO-VOICEPRINT` 或固定盘符目录。

## 不属于“外部文件夹”的必要环境

- 板端运行仍需 PYNQ-Z2、PYNQ Linux、Python/NumPy/ONNX Runtime 及对应硬件设备节点。
- 重建 Vivado 工程仍需 Vivado 2025.2；脚本从 `VIVADO_BIN` 或 `PATH` 查找，不绑定某个盘符。
- `/dev/ttyUSB*`、触摸输入和 HDMI/音频 IP 是硬件接口，不是源码目录依赖。
- `data/archive` 与训练报告中的历史绝对路径只记录实验来源，不参与正式运行入口。

## 变更边界

- 删除未被程序读取的 `transport`、`motion_groups_owned_by_controller` 描述字段。
- 未改变串口实现、机械臂动作映射、FPGA 寄存器、模型权重、阈值或 bit/HWH。
- 本次仅做电脑端静态/离线检查，未连接开发板，板端整机功能仍需提交前人工复测。
