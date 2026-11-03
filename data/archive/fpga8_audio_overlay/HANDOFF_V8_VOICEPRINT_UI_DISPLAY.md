# FPGA-8 声纹、UI与显示屏交接

## 1. 已完成状态

- PYNQ-Z2 / `xc7z020clg400-1`，PL 100 MHz。
- FPGA-8 同一 Overlay 已完成 HP+MIC 录音与 CAM++ 声纹推理；板测实际调用 `pointwise=55`、`FCM=12`。
- 已完成三条语音注册、中心模板保存、测试语音余弦相似度和阈值判定。
- 单次网络推理约 3.6～5.9 s；阈值 `0.67` 仅为联调值，尚未正式校准。
- 耳麦必须在开发板启动完成后再插入，然后初始化 Codec/选择麦克风。

## 2. 声纹相关材料

### 电脑端

FPGA-8 日常开发、打开 Vivado 和继续修改的目录：

`C:\Users\Lenovo\Desktop\SonicArm\v8_short\`

对应的实体存储目录：

`C:\Users\Lenovo\Desktop\SonicArm\pynq_voiceprint\CAM-pretrained_models\FPGA-8\`

`v8_short` 是指向 FPGA-8 实体目录的 NTFS Junction，不是另一份工程。后续描述和操作统一使用 `v8_short`，以避免 Vivado 长路径问题；无需迁移或重复复制。

板测软件包：

`C:\Users\Lenovo\Desktop\SonicArm\FPGA-8-AUDIO-TEST\`

主要文件：

- `v8_runtime.py`：FPGA-8 CAM++ 运行时。
- `FPGA8_enroll3_and_verify.ipynb`：三条注册及身份核验。
- `FPGA8_microphone_voiceprint_test.ipynb`：音频质量与单次声纹诊断。

已验证 bit/HWH SHA-256：

- bit：`86bf8d40f72efd5cef402536e42a780a14a85dcfe2457277d0071cd60f3a7328`
- HWH：`01842c056f8c05adf722b2f4cee621acdd27b839ec15883ed4a88b59f0d1a31e`

### 板端

部署目录：

`/home/xilinx/jupyter_notebooks/SonicArm/test_1/fpga_v8/`

核心文件：

- `cam_v8_audio.bit`
- `cam_v8_audio.hwh`
- `v8_runtime.py`
- 两个测试 Notebook

依赖 `test_1/static_runtime.py`、`test_1/fpga_context.py`、原模型参数和 `test_1/ui_audio_voiceprint/assets/frontend_constants.npz`。

注册结果：

- `fpga_v8/data/enrollment_profile_v8_3utt.npy`
- `fpga_v8/data/enrollment_profile_v8_3utt.json`

录音统一转为单声道 16 kHz PCM16，不做峰值归一化。下一版结果应写入独立 `results/run_<id>/`，不得覆盖 V8 历史文件。

## 3. UI材料

电脑端目录：

`C:\Users\Lenovo\Desktop\SonicArm\UI\`

当前不是 Vue，而是静态 HTML/CSS/JavaScript 加 Python 标准库服务器：

- `server.py`：静态文件与 HTTP 状态接口。
- `web/index.html`、`register.js/css`：人员信息与三段声纹注册。
- `web/auth.html`、`app.js`、`styles.css`：身份相似度、阈值、短语和机械臂状态界面。
- `README_PYNQ.md`：接口与部署说明。

现有接口：

- `GET/POST /api/enrollment`：注册进度。
- `GET/POST /api/state`：身份、阈值、短语和机械臂状态。
- `POST /api/reset`、`POST /api/enrollment/reset`：状态复位。

建议板端独立部署到：

`/home/xilinx/jupyter_notebooks/SonicArm/ui_v9/`

启动：

```bash
cd /home/xilinx/jupyter_notebooks/SonicArm/ui_v9
python3 server.py --host 0.0.0.0 --port 8080
```

当前服务器只管理内存状态，尚未真正触发录音、声纹、短语模型或持久化用户照片/模板；下一版需增加业务控制服务。

## 4. 下一版显示屏方案

推荐采用“统一 Overlay + PS 网页”的组合：

```text
HDMI显示屏 ← FPGA-9 HDMI/VDMA显示通路
USB触摸   → Linux HID → 本地浏览器
本地浏览器 → HTTP API → 录音/声纹/短语/机械臂服务
                         ↓
                    FPGA声纹加速核
```

- 网页、HTTP API、声纹调度和短语模型运行在 PS/Linux，不参与 Vivado 综合。
- HDMI/VDMA、音频 IP 和 CAM++ 加速核必须同时存在于同一个 FPGA-9 Overlay，不能加载 Base Overlay 替换声纹 Overlay。
- USB触摸作为 Linux HID 设备，通常不进入 Vivado；HDMI和USB支持热插拔，但程序需要处理重新初始化。
- FPGA-8 没有完整 HDMI 通路，因此实体屏直连 PYNQ HDMI OUT 并与声纹同时工作时，需要在 FPGA-9 加入显示通路并重新综合、实现、时序检查及生成匹配 bit/HWH。
- 若仅在电脑浏览器访问 `http://<PYNQ-IP>:8080`，无需加入 HDMI IP，也无需重新综合。

## 5. 下一版集成顺序

1. 复制 FPGA-8 为独立 FPGA-9 基线，保留 V8 不修改。
2. 先在 PS 端接通 UI按钮 → 录音 → 声纹 → HTTP状态返回。
3. 接入短语模型：同一份 16 kHz 录音分别进入 CAM++ 和短语模型，声纹通过后才接受短语结果。
4. 再将 HDMI/VDMA 合并进 FPGA-9 Overlay，并重新完成实现验证。
5. 最后验证 HDMI画面、USB触摸、耳麦录音、声纹、短语和UI全链路。

新窗口先读取项目根目录 `AGENTS.md`、`HANDOFF_V8_TO_V9_KWS.md` 和本文件。默认不连接或修改开发板。
