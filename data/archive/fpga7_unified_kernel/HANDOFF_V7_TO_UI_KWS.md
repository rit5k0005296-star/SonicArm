# SonicArm V7 → 显示UI与短语识别交接

## 1. 当前状态

- 板卡：PYNQ-Z2，`xc7z020clg400-1`；Vivado/Vitis 2025.2；PL 100 MHz。
- V7使用一个共享HLS IP `unified_v7`，复用8输出通道×8时间位置MAC阵列，执行55次Pointwise和12次FCM；剩余57个CPU Session仍在PS运行。
- 正式板测 `run_59b828961c834e1da0c7005232acb42e`：`actual_hardware=true`、`integer_exact=true`、`debug_on_off_exact=true`。
- 两条正式录音中位时延4.170/4.516 s，RTF均约0.850；相对优化INT8 CPU为1.406～1.426×，相对V6为1.034～1.049×。CPU剩余部分约占75%～76%，继续只优化PL收益有限。
- CN-Celeb软件参考：FP32 EER 4.7029%、MinDCF 0.31210；INT8 QDQ EER 4.8719%、MinDCF 0.32230。V7三条板测录音证明硬件计算正确，不等于完整V7 EER；鉴权阈值仍未校准。

## 2. V7资源与实现

| 资源 | 使用量 | 占用率 | 剩余 |
|---|---:|---:|---:|
| LUT | 22,317 / 53,200 | 41.95% | 30,883 |
| FF | 23,739 / 106,400 | 22.31% | 82,661 |
| Slice | 8,071 / 13,300 | 60.68% | 5,229 |
| BRAM Tile | 86 / 140 | 61.43% | 54 |
| DSP | 102 / 220 | 46.36% | 118 |

路由后WNS +0.121 ns、WHS +0.026 ns，0时序/路由/DRC错误。仍保留FIFO/BRAM复位等工具警告，`production_signoff=false`。

## 3. 文件与部署位置

电脑端根目录：
`C:\Users\Lenovo\Desktop\SonicArm\pynq_voiceprint\CAM-pretrained_models\FPGA-7`

- 最终工程：`vivado/v7_final/`
- HLS与源码：`hls/`、`src/`
- 板端源包：`board_package/fpga_v7/`
- 完整手动包：`deploy/fpga_v7_manual_tests.zip`
- bit/HWH：`deploy/cam_v7.bit`、`deploy/cam_v7.hwh`
- 正式结果副本：`run_59b828961c834e1da0c7005232acb42e/`

板端目录：
`/home/xilinx/jupyter_notebooks/SonicArm/test_1/fpga_v7/`

结果写入 `fpga_v7/results/run_<编号>/`。保留FPGA-1～FPGA-7、模型和历史结果，不覆盖。Notebook允许保存后改变；运行时仍强校验Python代码、bit/HWH和静态图。

## 4. UI与短语识别建议

- 短语识别先部署在PS，优先轻量BC-ResNet-1（TC-ResNet-8也可比较），无需先修改RTL/Vivado。它读取原始音频/独立声学特征，不能读取CAM++声纹embedding作为指令输入。
- 目标类别可采用9个坐标抓取、抓取、松开、复位、急停，再加入`unknown`和背景噪声；声纹鉴权通过后才执行指令。
- 推荐流程：一次录音缓存 → CAM++鉴权 → 短语识别 → 指令/坐标解析 → 安全状态机 → 机械臂控制。
- 当前V7测试Overlay没有完整显示、音频和机械臂外设。若UI只在PS管理且使用已有兼容显示通路，可独立开发；若使用PYNQ-Z2 HDMI OUT并要求与V7同时运行，需要把HDMI/VDMA等视频通路集成到同一个新Overlay，不能加载另一个Overlay替换V7。此时新建FPGA-8目录并重新综合、实现、时序检查及生成匹配bit/HWH。
- 端口建议：Micro USB PROG/UART保留电脑控制台；HDMI OUT传画面；USB-A Host连接USB HID触摸。屏幕原生分辨率、HDMI输入模式和缩放能力需分别核对。
- UI中单次结果显示“相似度/识别置信度”，不要显示为“准确率”。

## 5. 新窗口执行边界

先读取项目根目录 `AGENTS.md` 和本文件。默认不SSH、不加载Overlay、不写Samba；先在电脑端完成UI/KWS代码、模型、数据标签、接口协议和测试包。只有新增PL视频、音频、UART/PWM等逻辑时才进入FPGA工程，并继续使用`fpga-development`及对应FPGA-Agent技能。

