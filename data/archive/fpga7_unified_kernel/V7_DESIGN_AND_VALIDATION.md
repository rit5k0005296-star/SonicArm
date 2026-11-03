# FPGA-7 统一卷积加速器设计与电脑端验证

## 设计目标与边界

FPGA-7 面向 PYNQ-Z2（`xc7z020clg400-1`），使用 Vivado/Vitis 2025.2，PL 时钟保持 100 MHz。目标是在保持 CAM++ 数值契约和现有 55 次 Pointwise、12 次 FCM 逻辑调用计划的前提下，减少 V6 两套互斥计算阵列占用的 PL 资源，并削减无效参数读取。V7 没有改变模型、输入长度、量化边界或正式计时范围。

数值契约仍为 INT8 输入与权重、INT16 中心化输入、INT32 累加、64 位重定量化乘积、ties-to-even 舍入、饱和、LUT、残差和原有量化边界。

## 实现

- `unified_v7` 是唯一的 HLS 计算 IP，`mode=0` 执行 Pointwise，`mode=1` 执行 FCM。
- 两种模式复用同一个 8 输出通道 × 8 时间位置 MAC 阵列，主 MAC 循环 II=1；综合出的共享阵列使用 64 个 DSP。
- 三个 64 位 AXI 主端口分别连接输入、参数和输出，对应 PS7 的 HP0、HP1、HP2。
- 参数加载按 `ceil(Cout/8)×8` 个输出通道进行。FCM 常用 `Cout=32` 时不再加载到固定 128 通道；Pointwise 小输出尾部也减少无效读取。
- 软件保留 Pointwise/FCM 两个兼容视图，在同一个物理 IP 上切换模式；连续同模式调用缓存静态模式寄存器，避免重复 AXI-Lite 写入。

## 验证结果

- 原生 C：110 个真实 Pointwise 用例、48 个真实 FCM 用例和边界用例通过。
- HLS CSim：两种模式通过。
- HLS 综合：估算周期 9.258 ns；93 DSP、190 RAMB18、30,763 FF、36,768 LUT；共享 MAC 为 64 DSP、II=1。
- RTL 协同仿真：Pointwise 3 个固定真实事务通过，FCM 8 个事务通过，未出现 DATAFLOW/FIFO 死锁。
- 参数加载优化的同用例 RTL 周期变化：FCM 合计 1,008,384 → 983,384（-2.48%）；Pointwise 合计 95,464 → 78,595（-17.67%），其中 `Cout=8` 事务 50,944 → 33,561（-34.12%）。两个大 Pointwise 事务约增加 1%，不能据此宣称整网提速。
- 桌面整网回归：用统一 `unified_0` 假 MMIO/CMA 和真实 C++ 内核跑通三条完整录音（370/489/529 帧），67 层整数逐层一致，debug 开关、2051 帧 halo、非整齐尾部、保护区和缓冲区释放通过。该回归的 Windows 耗时没有板端性能意义。
- Vivado 最终工程位于 `vivado/v7_final`，从新 IP 创建且未使用增量检查点。40,659/40,659 网络完整路由，路由错误 0，DRC Error 0。
- 100 MHz 路由后时序：WNS +0.121 ns、WHS +0.026 ns、WPWS +3.750 ns，TNS/THS/TPWS 均为 0。
- 路由后资源：22,317 LUT（41.95%）、23,739 寄存器（22.31%）、8,071 Slice（60.68%）、86 BRAM Tile（61.43%）、102 DSP（46.36%）。

相对 V6，LUT 约减少 51.8%，Slice 约减少 38.4%，DSP 约减少 51.7%，BRAM Tile 约减少 23.6%。这些是布局布线后的资源证据，不是板端性能证据。

## 待手动板测

本轮没有连接开发板，`actual_hardware=false`。请使用 `board_package/fpga_v7` 的 Notebook 依次执行硬件正确性、逐层/硬件窗口剖析，以及关闭详细剖析后的同板整网测速。V7 没有被动 PL 计数器，剖析中的硬件时间是主机观察到的 start-to-done 窗口。正式结论必须与 V6 正式运行及优化 INT8 CPU 在相同输入、线程和计时口径下比较。

原 QDQ 严格漂移、相对优化 INT8 CPU 的质量门限失败和未校准鉴权阈值继续保留。厂商 FIFO/BRAM 复位、LUTAR/PDCN 与 PS7 DDR 参数警告也继续记录；0 个 DRC Error 不代表产品签核。

## 板端包修订

首次手动运行中，三条完整录音的 `debug=True` 路径均打印 `V7 HARDWARE PASS`，随后 Jupyter 保存 Notebook 改变了 `.ipynb` 字节，旧清单在创建 `debug=False` Runtime 时误报 `V7 package changed`。该异常发生在包完整性检查阶段，不是 PL 计算错误，也未形成完整的 `hardware_correctness.json`。

修订后的清单将 Notebook 标记为可变交互文件：发布 ZIP 仍核对其初始哈希和代码单元可编译性，板端运行时仅检查它存在；Python 运行时、bit/HWH、构建状态、实现验收及既有 `test_1` 静态图继续进行强哈希校验。桌面回归同时证明 Notebook 元数据变化可继续运行，而 `v7_runtime.py` 的单字节级变更仍被拒绝。该包修订没有改动 HLS、Vivado 工程或 bit/HWH，因而不重述综合、实现或时序为新的硬件结果。
