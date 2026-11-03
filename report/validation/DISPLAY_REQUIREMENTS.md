# FPGA-9实体触控屏集成边界

## 最终连接

```text
PYNQ-Z2 HDMI OUT -> 触控显示屏 HDMI IN
PYNQ-Z2 USB-A Host -> USB Hub -> 显示屏触摸USB
                              -> 后续机械臂USB串口
```

HDMI只传输图像，USB触摸由Linux HID输入子系统处理。USB Hub和触摸本身通常不进入Vivado；HDMI OUT在PYNQ-Z2上依赖PL显示通路。

## FPGA-9硬件要求

必须从V8建立独立FPGA-9，保留：

- `unified_v7` CAM++加速核；
- `audio_codec_ctrl_0`及ADAU1761约束；
- PS7与现有HP内存互连；

并加入与目标PYNQ/PYNQ 3.0.1驱动匹配的：

- HDMI/VDMA视频输出通路；
- 所需像素时钟、AXI互连和复位；
- HDMI输出引脚约束；
- 与PS软件一致的HWH元数据。

新设计必须重新执行综合、布局布线、时序、DRC和bit/HWH配对检查。V8的资源/时序结果不能作为FPGA-9结果。

## PS显示软件要求

加入HDMI/VDMA只提供视频数据通路，**不会自动把HTML网页显示到屏幕**。最终还必须选择并验证一种PS渲染方式：

1. Linux桌面/浏览器直接使用可用的DRM或framebuffer输出；或
2. 用Python/OpenCV/PIL将当前UI设计渲染为视频帧，写入PYNQ HDMI输出缓冲区。

在确认PYNQ镜像是否具有可用的X11/Chromium/DRM输出之前，不把“Chromium kiosk”写成已可用结论。若没有通用桌面输出，优先采用Python原生HMI渲染，并从`/dev/input/event*`读取USB HID触摸事件。

## 最终验收

- FPGA-9 bit/HWH哈希匹配；
- HDMI画面实际出现在实体屏；
- USB触摸能点击注册和识别控件；
- HDMI、触摸、耳麦录音和CAM++可同时工作；
- 同一录音完成声纹与TC-ResNet3；
- UI显示身份、短语及机械臂dry-run状态；
- USB Hub重插后设备能恢复或给出明确故障；
- 电脑浏览器画面不得代替实体屏验收。
