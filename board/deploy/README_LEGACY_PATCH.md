# FPGA-10 自动复位与语音复位补丁

目标目录：`/home/xilinx/jupyter_notebooks/SonicArm/test_1/fpga_10`

变更内容：

1. `app.py`完成Overlay、显示、音频和模型初始化后，在HTTP服务开始接单前自动执行一次机械臂竖直复位。
2. 通过声纹阈值和短语阈值的“复位”命令会以已确认复位方式交给`ArmDispatcher`。
3. `verified_arm_control.py`允许在非BUSY状态下重复执行已验证的竖直复位动作组。
4. `config.json`新增`auto_reset_on_startup=true`和`voice_reset_enabled=true`。
5. “复位”使用单独短语阈值`0.85`；身份阈值仍为`0.67`。
6. 注册和识别的现场语音采集时长由4秒统一改为3秒；TC-ResNet3仍补齐到5.2秒模型输入窗口。
7. 保留单任务锁、身份鉴权、拒绝标签、重复语句阻止、FAULT状态和动作超时不自动重发。

验证：

- Python语法编译通过。
- 28项离线回归测试通过。
- 未连接开发板，自动复位和语音复位仍需用户在真实机械臂上验证。

部署前必须在串口终端按`Ctrl-C`停止当前`app.py`，并清空机械臂运动范围。运行`deploy_to_board.ps1`会先将四个被替换文件备份到板端时间戳目录，再复制并核对SHA256。
