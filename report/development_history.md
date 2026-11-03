# Development History

## FPGA-1: quantization and first operator

完成 CAM++ INT8 量化探索，提取首个 1x1 卷积算子和 C testbench。

## FPGA-2: fused convolution path

形成卷积、ReLU 和重定标融合路径，建立第一版 HLS/Vivado 与板端测试规划。

## FPGA-3: pointwise operator

建立 pointwise HLS 核及 C testbench，验证单算子接口与计算正确性。

## FPGA-4: FCM operator

加入 FCM 算子、桌面验证与板端集成准备，补齐声纹网络后段计算路径。

## FPGA-5: dual kernels

将 pointwise 与 FCM 分离为两个加速核，引入 AXI 接口、性能监视和桌面验证脚本。

## FPGA-6: reproducible validation

补充 HLS/RTL/实现证据收集、版本交接和发布检查，明确仿真、综合估计与实现结果的边界。

## FPGA-7: unified kernel

将 pointwise/FCM 路径整合进统一计算核，为单 Overlay 集成准备共享数据通路。

## FPGA-8: audio and overlay integration

接入 PYNQ-Z2 音频接口、统一核和 Overlay 工程，形成 PS 端声纹与界面系统的硬件基础。

## V9: PS application integration

整合音频采集、CAM++ 声纹运行时、触控/Web 界面和板端流程，并保留旧 KWS 兼容路径。

## FPGA-10: complete SonicArm system

升级到 TC-ResNet3，统一 HDMI/VDMA、触摸、用户管理和安全状态机；随后通过 USB-UART 接入机械臂，增加上电自动复位、语音复位、3 秒录音窗口及 0.70 指令执行阈值。

历史文件位于 `data/archive/`。当前正式源码以 `src/ps/`、`src/models/` 和 `src/ip/` 为准。

