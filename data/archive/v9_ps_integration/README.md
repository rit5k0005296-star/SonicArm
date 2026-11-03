# SonicArm V9 第一阶段集成验证

本目录是独立的 PS 侧预集成包，不修改 V8 Vivado 工程、既有 bit/HWH、声纹模板或 TC-ResNet2 原目录；新增 TC-ResNet3 目录并由配置切换。

**电脑浏览器只用于中间调试，不属于最终显示验收。** 最终 V9 必须使用 PYNQ HDMI OUT 连接实体触控屏，触摸USB经USB Hub连接PYNQ USB-A。

## 验证范围

```text
FPGA-8 HP+MIC录音
  -> 同一份16 kHz单声道波形
  -> CAM++声纹（V8 PL加速）
  -> 身份通过后运行TC-ResNet3（PS NumPy）
  -> HTTP更新UI
```

安全门禁固定为：

- `dry_run=true`
- `kws_execution_enabled=false`
- 不包含 `serial` / `pyserial` 导入
- 不打开任何 `/dev/ttyUSB*` 或 `/dev/ttyACM*`
- 所有结果的 `execute=false`

## 板端目录

将整个目录复制到：

```text
/home/xilinx/jupyter_notebooks/SonicArm/test_1/integration_v9/
```

不得覆盖相邻的：

```text
test_1/fpga_v8/
test_1/tc_resnet2_ps/
```

本包默认读取 `test_1/fpga_v8` 中已经核验的 bit/HWH。网页新注册模板独立保存到 `integration_v9/data/users/<用户编号>/`，不会覆盖V8历史模板。bit/HWH SHA-256不匹配时会在加载前停止。

## 推荐运行方式

当前推荐使用常驻网页控制入口，详细步骤见 `BOARD_WEB_CONTROL_DEPLOY.md`：

```bash
cd /home/xilinx/jupyter_notebooks/SonicArm/test_1/integration_v9
python3 app.py --host 0.0.0.0 --port 8080
```

`app.py`启动时只加载一次已核验的V8 Overlay、Codec、CAM++ Runtime和PS端TC-ResNet3；注册与识别按钮复用同一硬件上下文。以下Notebook/两终端方式仅保留用于旧的一次性诊断。

旧的一次性Notebook诊断方式如下：

1. 机械臂USB串口保持断开。
2. 开发板启动完成后插入耳麦。
3. 在 Jupyter 中打开 `V9_integration_validation.ipynb`。
4. 修改姓名和用户编号，然后按顺序执行单元。
5. 当前阶段可用电脑浏览器查看 `http://<PYNQ-IP>:8080/auth.html`，但该结果只算PS软件预集成。
6. 最新证据位于 `results/run_<时间>/result.json`。

## 页面切换和阈值

- 注册页：`/`。
- 识别页：`/auth.html`。
- 识别页“注册用户”按钮返回注册页；注册页“进入识别”或“完成并进入识别”返回识别页。
- 注册页“开始录入”调用 `/api/enrollment/start`；识别页“开始识别”调用 `/api/recognition/start`。
- `config.json` 中 `identity_threshold` 是声纹余弦相似度阈值，当前为 `0.67`。
- `config.json` 中 `kws_threshold` 是短语 softmax 门限，当前联调值为 `0.80`。
- 注册和识别录音均为 `4.0 s`；TC-ResNet3前端裁剪有效语音并居中补零到5.2秒/83200点模型窗口。
- 用户管理页读取 `data/users` 中的真实注册记录；删除前显示编号和姓名并要求确认，后端空闲时把用户目录移动到 `data/deleted_users/`，支持人工恢复。
- 静音基线只用于通道选择和音频门控：注册时采集并缓存5分钟，识别优先复用；缓存缺失或过期才重新采集。
- 当前削波门限临时为 `2.0%`，来自本轮约1.6%削波的板端日志，只作为联调值。
- 两个阈值目前都没有正式校准；修改后必须保留 `*_threshold_calibrated=false`，直到完成独立验证集标定。

只有排查旧的一次性流程时，才分别运行以下两个命令；此方式不是网页按钮控制入口：

```bash
cd /home/xilinx/jupyter_notebooks/SonicArm/test_1/integration_v9
python3 ui/server.py --host 0.0.0.0 --port 8080
```

另开一个终端：

```bash
cd /home/xilinx/jupyter_notebooks/SonicArm/test_1/integration_v9
python3 run_validation.py --name 张同学 --user-id SA-002
```

## 当前不能证明的内容

- 声纹阈值 `0.67` 尚未完成 FAR/FRR 校准。
- KWS阈值 `0.9` 尚未完成真人 unknown/silence 校准。
- 集成通过不代表机械臂安全或串口协议通过。
- 本阶段不包含 HDMI/VDMA，因此不证明PYNQ HDMI实体屏显示。
- 最终必须使用同一 FPGA-9 Overlay 同时承载音频/CAM++与HDMI/VDMA，不能加载Base Overlay替换声纹Overlay。
- USB触摸须在PYNQ Linux中作为HID读取，并与HDMI画面完成坐标和点击联调。
