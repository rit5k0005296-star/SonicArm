# SonicArm FPGA-8 → FPGA-9 短语识别交接

## 1. FPGA-8 当前结论

- 板卡：PYNQ-Z2 / `xc7z020clg400-1`；Vivado 2025.2；PL 100 MHz。
- 同一 Overlay 已实现 HP+MIC 录音与 CAM++ 声纹推理；板端实测 `pointwise=55`、`FCM=12`，证明 V8 加速核实际执行。
- 三条语音可生成 192 维中心模板；一次非本人测试相似度 `0.6152 < 0.67`，正确拒绝。该结果只证明当前流程可用，`0.67` 仍未经过正式 FAR/FRR 校准。
- 单次网络推理约 3.6～5.9 s，尚未达到说完后 1 s 返回。
- HP+MIC 启动顺序必须为：开发板先上电并启动完成，再插耳麦，然后加载 Overlay/选择麦克风。
- V8 工程加入音频，但当前不包含完整 HDMI 显示通路。

## 2. 实现与资源证据

FPGA-8 日常开发和 Vivado 工程入口：

`C:\Users\Lenovo\Desktop\SonicArm\v8_short\`

对应的实体存储目录：

`C:\Users\Lenovo\Desktop\SonicArm\pynq_voiceprint\CAM-pretrained_models\FPGA-8\`

`v8_short` 是指向上述 `FPGA-8` 实体目录的 Windows NTFS Junction，不是第二份副本。两个路径中的文件完全相同；后续统一从 `v8_short` 打开和修改 Vivado 工程，以规避 Windows/Vivado 长路径问题。必须保留该 Junction，无需迁移或重复复制工程。

实现后资源：

| 资源 | 使用量 | 占用率 |
|---|---:|---:|
| LUT | 22,611 / 53,200 | 42.50% |
| FF | 24,204 / 106,400 | 22.75% |
| Slice | 8,213 / 13,300 | 61.75% |
| BRAM Tile | 86 / 140 | 61.43% |
| DSP | 102 / 220 | 46.36% |

时序：WNS `+0.426 ns`、TNS `0`、WHS `+0.020 ns`、THS `0`；41,313 条网络全部布通，routing error 为 0。仍有 `TIMING-4`、`TIMING-27` 方法学 Critical Warning，因此不是无保留生产签核。

匹配产物 SHA-256：

- bit：`86bf8d40f72efd5cef402536e42a780a14a85dcfe2457277d0071cd60f3a7328`
- HWH：`01842c056f8c05adf722b2f4cee621acdd27b839ec15883ed4a88b59f0d1a31e`

## 3. 文件部署与存储

本地板测包：

`C:\Users\Lenovo\Desktop\SonicArm\FPGA-8-AUDIO-TEST\`

主要文件：

- `FPGA8_enroll3_and_verify.ipynb`：三条注册及测试。
- `FPGA8_microphone_voiceprint_test.ipynb`：音频诊断与单次核验。
- `v8_runtime.py`：复用已加载 Overlay 的 V8 运行时。

板端目录：

`/home/xilinx/jupyter_notebooks/SonicArm/test_1/fpga_v8/`

板端必须同目录保存：

- `cam_v8_audio.bit`
- `cam_v8_audio.hwh`
- `v8_runtime.py`
- 测试 Notebook

依赖父目录中的 `static_runtime.py`、`fpga_context.py`、模型参数，以及 `ui_audio_voiceprint/assets/frontend_constants.npz`。

注册结果：

- `fpga_v8/data/enrollment_profile_v8_3utt.npy`
- `fpga_v8/data/enrollment_profile_v8_3utt.json`

录音文件保存在 `fpga_v8/`；模型输入统一为单声道、16 kHz、PCM16，不做峰值归一化。V9 应把每轮结果写入独立 `results/run_<id>/`，不要覆盖 V8、旧模板或历史录音。

## 4. FPGA-9 建议边界

先在 PS 端加入短语识别，不必立即修改 HLS/Vivado：

`一次麦克风录音 → VAD/有效语音裁剪 → CAM++ 声纹 → 通过后执行短语识别 → 输出身份相似度和短语类别`

- CAM++ 与短语模型复用同一份 16 kHz 单声道录音，但分别使用各自前端；短语模型不能读取声纹 embedding 代替声学输入。
- 先测 PS 端短语模型准确率、混淆矩阵和耗时，再决定是否值得放入 PL。
- 仅增加 PS 端模型/网页接口：沿用 V8 bit/HWH，无需重新综合。
- 若新增 KWS PL IP、HDMI/VDMA 或改变 Block Design/XDC：建立独立 `FPGA-9`，重新完成综合、布局布线、时序、DRC、bit/HWH 和板端验证。
- 保留已知边界：认证阈值未正式校准，原 INT8 QDQ 精度漂移未关闭，单次结果不能称为准确率。

## 5. 新窗口起点

先读取项目根目录 `AGENTS.md` 和本文件；默认不连接开发板。首先盘点短语模型的模型文件、标签、采样率、输入特征、运行依赖及现有准确率，再创建独立 FPGA-9 目录和测试包。
