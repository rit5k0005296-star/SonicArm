# FPGA-10 与机械臂控制板集成

## 已完成的软件接线

`同一段录音 → CAM++声纹门控 → TC-ResNet3最终标签 → 四格白名单 → 单次ID去重 → 机械臂状态机 → 已验证板端控制模块`

只映射以下标签：

- `抓取第一行第一列/第二列`
- `抓取第二行第一列/第二列`
- `松开`
- `复位`

模型中的第三行、`抓握`、`急停`、`unknown` 和 `silence` 均不会驱动机械臂。

## 板端已有模块的接口要求

本交付已将板上Notebook的已验证动作组整理为：

`arm_control/verified_arm_control.py`

部署时将它保存为：

`/home/xilinx/jupyter_notebooks/SonicArm/test_1/fpga_10/arm_control/verified_arm_control.py`

该文件必须提供：

```python
def arm_pick(row, col) -> bool: ...
def arm_place_right() -> bool: ...       # 等待 @GroupDone!，超时不少于25秒
def arm_reset_upright() -> bool: ...
```


## 安全启用流程

默认 `config.json` 保持：

```json
"kws_execution_enabled": false,
"dry_run": true,
"arm": { "execution_enabled": false }
```

这是可测试但不动作的状态。完成声纹/KWS阈值验收、确认板端模块路径并清空机械臂工作区后，人工将三项改为：

```json
"kws_execution_enabled": true,
"dry_run": false,
"arm": { "execution_enabled": true }
```

启动后状态为 `UNKNOWN`。复位属于危险动作，语音识别本身不会自动视为人工确认。维护人员清空工作区并现场确认后，通过本机受控接口启动复位：

```bash
curl -X POST http://127.0.0.1:8080/api/arm/reset \
  -H 'Content-Type: application/json' \
  -d '{"confirm":true}'
```

复位成功后才进入 `READY`。任何异常进入 `FAULT`，系统不会自动重发。

## 供电

- PYNQ：独立稳定12V圆孔电源，J9=REG。
- 显示屏：独立5V2A；USB-C TOUCH只连接PYNQ USB Host的数据路径。
- 机械臂：使用原配独立电源；不要由PYNQ USB Host为舵机供电。
- 机械臂控制板只能由 PYNQ 或电脑中的一个主机控制，不得同时连接两个主机。
