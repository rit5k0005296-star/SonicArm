# Current release baseline

整理日期：2026-11-02。

当前权威源码来自 `FPGA-10/integration_fpga10`，核心正式配置如下：

- `speech_seconds=3.0`
- `identity_threshold=0.67`
- `kws_threshold=0.85`
- `kws_execution_enabled=true`
- `dry_run=false`
- `arm.execution_enabled=true`
- `arm.auto_reset_on_startup=true`
- `arm.voice_reset_enabled=true`

2026-10-30 的电脑端离线回归记录为 28 项测试通过。此结论只覆盖软件逻辑和本机 HTTP 回环测试，不替代板端声纹质量、指令准确率、机械臂运动安全、供电或时序签核。

2026-11-02 已使用 Vivado 2025.2 对 `xc7z020clg400-1` 执行一次干净完整构建：综合、实现、布线和 bitstream 生成完成，WNS +0.324 ns、TNS 0 ns、WHS +0.015 ns、THS 0 ns，50,229 条可布线网络全部完成。完整证据及方法学警告边界见 `final_board_acceptance.md` 与 `build/reports/`。

