# Historical Code Archive

本目录保存项目各阶段的核心源码、测试入口和交接说明，用于证明设计演进过程。历史代码不参与当前 FPGA-10 正式构建，也不代表所有阶段均已完成同等级板端验证。

| 目录 | 阶段 | 主要演进 |
|---|---|---|
| `fpga1_quantization` | FPGA-1 | CAM++ INT8 量化与首个 1x1 卷积算子 |
| `fpga2_conv_relu` | FPGA-2 | 卷积、ReLU 和重定标融合算子 |
| `fpga3_pointwise` | FPGA-3 | pointwise HLS 算子与 C testbench |
| `fpga4_fcm` | FPGA-4 | FCM 算子、板端集成准备与构建证据 |
| `fpga5_dual_kernel` | FPGA-5 | pointwise/FCM 双核、AXI 监视与验证脚本 |
| `fpga6_validated_kernels` | FPGA-6 | 双核验证、实现审计与版本交接 |
| `fpga7_unified_kernel` | FPGA-7 | pointwise/FCM 统一计算核与共享接口 |
| `fpga8_audio_overlay` | FPGA-8 | 音频、统一加速核和 Overlay 集成 |
| `v9_ps_integration` | V9 | PS 音频、声纹和界面集成 |
| `tc_resnet2` | 旧 KWS | TC-ResNet2 兼容运行时 |
| `fpga10_board_stages` | FPGA-10 | 机械臂接入、正式发布、自动/语音复位阶段备份 |

归档仅保留手写源码、顶层测试、构建入口和说明；排除 Vivado/HLS 缓存、自动生成目录、bitstream、日志、录音、用户资料和运行结果。所有控制板品牌或型号依赖已改成中性接口描述。

