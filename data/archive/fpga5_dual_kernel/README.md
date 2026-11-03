# FPGA-5：CAM++ 分块卷积与 PL 计数

本版与 FPGA-3、FPGA-4 并列。新文件只放在本目录。原始模型、旧内核、旧 bit/HWH 和历史测试只读引用；`reports/baseline_pins.json` 保存旧源码和参考用例指纹。

目标芯片为 PYNQ-Z2 的 `xc7z020clg400-1`，目标 PL 时钟100MHz。卷积使用 C++ HLS 生成 Verilog；性能计数器使用手写 Verilog。是否已完成布局布线，以 `reports/routed_summary.json` 与对应报告为准；本版尚无实际板端速度、能耗或准确率验收结果。

当前Overlay是PS、卷积内核和计数器的最小测试系统，使用既有录音的冻结特征；没有集成板载音频/视频外设。实时音频系统需在模型验证后接回相应外设并单独验证。

Vivado日志保留了沿用PS7预设时的DDR DQS负延时警告，没有人为将参数置零来消除提示。时序/DRC验收不能替代板端连续数据和正确性测试；本包保持手动验证流程。

## 内核变化

| 项目 | 本版实现 |
|---|---|
| 点卷积 | 8个输出通道×8个时间位置，MAC主循环II=1；按128个输出通道缓存权重块，在时间块间复用；输入按64帧分块 |
| FCM卷积 | 8个输出通道×8个时间位置，MAC主循环II=1；频率块4、时间块32，缓存带边界的输入窗口和当前层权重 |
| 数据接口 | 保留原密集字节布局，使用64位m_axi访问；处理未对齐行、通道/时间尾部，输出部分字节通过读改写保留相邻数据 |
| 数据流 | 每个卷积内核包含读取、计算、存储阶段与有限FIFO；FCM残差读取归属存储阶段的gmem_output，避免与输入读取共享端口导致串行死锁 |
| PS连接 | 3个64位HP通路承载输入、参数、输出；共享同一DDR，并不等于获得3倍DDR带宽 |
| PL计数 | 手写AXI-Lite计数器，记录启动至完成的PL周期、64位数据拍、读写等待；独立RTL仿真验证 |

点卷积最大Cin=1024、Cout=512、单次T=2048；FCM最大Cin/Cout=32、频率80、单次T=2048，K=1/3、频率步长1/2。长FCM录音沿时间分块并保留halo；CPU上下文/注意力仍处理完整录音。权重块复用不代表整个CAM++权重已经放进BRAM。

保持既有INT8输入、INT32累加、64位乘积、ties-to-even重定量化、饱和与量化边界。没有把CAM++换成小CNN，也没有修复此前与原始QDQ整网的数值漂移；这些质量失败继续单独保留。

## 本地证据

2026-10-17当前源码的完整普通实现已完成，运行状态为`write_bitstream Complete!`，无过期输入。100MHz下WNS=+0.329ns、WHS=+0.013ns、WPWS=+3.750ns，TNS/THS/TPWS均为0；未约束内部端点、缺失时钟和缺失I/O延时检查均为0，完整路由、DRC零错误。资源为46,500/53,200 LUT、206/220 DSP、110.5/140 BRAM Tile、49,166/106,400寄存器；Slice占用13,173/13,300。资源已较满，不能据此直接增加更多并行硬件。

最终工程候选为`deploy/fpga_v5_manual_tests.zip`。电脑端已核对9个压缩包成员的字节身份、空输出Notebook和匹配HWH寄存器映射，详见`reports/manual_package_audit.json`。当前仍是手动上板测试候选，保留工具警告和原QDQ漂移失败，没有V5实际加速倍率。

`reports/local_validation.json`区分以下证据：

- 点卷积110个真实层用例、FCM48个真实层用例的C测试，以及舍入/饱和、非整齐尺寸、LUT、残差、最大长度与调试关闭等边界。
- 两个内核各自的C/RTL协同仿真。
- FCM额外8个使用独立AXI内存模型、施加背压的RTL用例。
- 手写计数器的AXI-Lite协议与计数测试。
- 1,152个未对齐片段读写与相邻保护字节用例，覆盖全部0～8字节长度和8种字节偏移。
- Windows原生ORT与真实C++内核驱动模拟MMIO/CMA的整网回归，包括3条完整录音、67层当前输入整数核对、2051帧接缝和调试开关。

桌面回归不是开发板实测；其中计数器值是测试桩数据，时延不用于FPGA性能结论。HLS资源/Fmax估计也不等于Vivado布局布线结果。

早期FCM候选的DATAFLOW被合并成单进程，有限输出FIFO导致死锁；该候选已停止，失败日志保留在reports。修复后综合日志明确检测到3个进程，C/RTL及独立AXI测试通过。此前UVM仿真器异常不能替代这个根因诊断。

首轮输出字节掩码由可变64位移位后减1生成，RTL转为宽位进位链；100MHz布线报告最差设置裕量为-0.245ns。当前源代码改为直接译码字节使能，保留密集布局和读改写语义；旧源码、生成RTL与失败报告保存在`reports/carry_mask_candidate/`。最终时序仍以当前`reports/routed_summary.json`及对应报告为准，未通过的候选不用于部署。

旧掩码候选后来经布线后优化达到0.069ns设置裕量，相关bit/HWH及报告已归档；该检查点曾用于增量实现尝试，不能作为当前修改后源码的部署证据。

## 复现

在本目录用PowerShell执行。脚本将当前版本映射到空闲W盘，若W盘属于其他目录则拒绝操作。TEMP/TMP仅在脚本进程内临时设置；不修改系统时间、系统环境或其他版本工程。

```powershell
python -B prepare_project.py
foreach ($kernel in @('pw','fcm')) {
    foreach ($stage in @('csim','synth','cosim','package')) {
        .\run_hls.ps1 -Kernel $kernel -Stage $stage
    }
}
.\run_vivado.ps1 -Stage create
.\run_local_checks.ps1 -Stage all
python -B tests/check_packed_mutation.py
.\run_vivado.ps1 -Stage build
python -B verify_local_evidence.py
python -B tests/audit_implementation.py
python -B make_board_package.py
python -B tests/audit_manual_package.py
```

工具版本：Vitis/Vivado 2025.2。`create`只用于首次创建；已有有效V5工程使用`build`继续，或`gui`打开本版工程。不要把旧失败候选工程当作最终工程。

`close_timing`只从已布线检查点重启布线后物理优化；改变内核RTL/IP后应重新生成整机，不能用旧检查点替代新逻辑的综合与布线。

曾尝试用归档检查点进行增量实现，但重放的时钟缓冲优化产生位置冲突，已停用该参考；相关日志保存在`reports/incremental_clock_*`。当前流程使用普通布局布线，`restart_placement`可保留当前新RTL的综合结果、清除增量参考并从布局阶段重启。

仅从布局阶段重启会保留旧的LaunchIncrCheckpoint元数据，可能让已完成的结果被标记为Out-of-date。`restart_full_implementation`保留时序通过的候选后，从init_design重跑整套普通实现；不手动清除NEEDS_REFRESH，也不使用时钟专用布线豁免。最终导出要求运行状态完成且无过期输入。

`make_board_package.py`要求RTL协同仿真、当前实现的正建立/保持/脉宽裕量、零时序违例、完整约束覆盖、完整路由及DRC零错误证据，并核对报告与产物指纹。手动工程测试候选为`deploy/cam_v5.bit`及同名`cam_v5.hwh`，并通过包清单固定指纹。

DRC零错误不等于零警告。FIFO Generator异步复位、BRAM控制、DSP流水与无负载信号等提示继续保留，分类见`board_package/fpga_v5/BUILD_STATUS.md`；`implementation_acceptance.json`明确记录`production_signoff=false`。本包用于后续手动工程验证，不称为完成产品签核或实际加速验收。

`tests/audit_manual_package.py`在电脑端只读核对最终zip的文件指纹、空输出Notebook与HWH寄存器契约；它不加载Overlay，也不连接开发板。

## 手动上板

使用`deploy/fpga_v5_manual_tests.zip`，将其中`fpga_v5`目录手动复制到已有`SonicArm/test_1/`。按Notebook顺序执行正确性、逐层/PL剖析和关闭剖析后的正式测速。详见`board_package/fpga_v5/README.md`。代理不SSH、不执行板端代码、不写Samba共享。

正式主基线为同板优化INT8 CPU，同时保留FP32 CPU和V4静态图。只有实际结果中的`INT8_CPU_over_V5 > 1`才能说明相应查询上V5更快；已有数值漂移未通过时，不能称为精度一致的加速。

所提供论文及两个开源项目的适用性核查见[REFERENCES.md](REFERENCES.md)。
