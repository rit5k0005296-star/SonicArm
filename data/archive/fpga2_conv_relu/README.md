# CAM++ 第二次加速：conv_relu（V2-A）

本目录参照第一版 conv1x1 的文件布局。目标为 PYNQ-Z2 / xc7z020clg400-1，工具 Vitis/Vivado 2025.2，100 MHz。完整后续方案见 ../CAM_ACCELERATION_PLAN.md。

2026-10-14 当前进度：参考数据、五组 C Simulation、C Synthesis、三次 RTL Co-Simulation、IP Package 均已完成。独立 Vivado 工程已创建、Validate Design 通过、Output Products 与 HDL Wrapper 已生成。直接从第七步开始运行 Vivado 综合/实现/位流；尚未生成 bitstream，尚未上板。本次 PS7/DDR 配置沿用第一版，仍有与原配置一致的负 DQS-to-clock skew 提示；未擅自改变板级 DDR 参数。换板后核对器件/板型并上板验证。

## 文件布局

```text
conv_relu/
  prepare_conv_relu.py       ONNX 参数、256 项后处理表、五组融合参考
  conv_relu.h/.cpp           HLS 顶层，4×4=16 路乘加
  tb_conv_relu.cpp           独立整数/FP64参考、真实与边界输入测试
  layer_params.h             自动生成的固定层参数
  *.bin                     默认歌唱输入及参考，格式同第一版
  reference_report.json      原模型与参考数据哈希、精确比较记录
  validation_report.json     本次综合/仿真/IP/BD 检查及源码哈希
  test_audio/                第一版五段录音的副本，音频哈希一致
  hls_config.cfg             Vitis 2025.2 配置，Vivado IP flow
  run_hls.ps1                csim/synth/cosim/package 分阶段执行
  export_ps_config.py        只读复制第一版的 PS7 配置
  ps7_config.tcl             自动生成的 PS7 配置副本
  create_vivado.tcl          只创建本目录的新工程和 BD
  collect_deploy.tcl         位流完成后收集配对 bit/hwh 与报告
  hls_workspace/conv_relu/   已创建的 HLS component
  vivado_workspace/          本目录自己的 Vivado 工程/报告
  deploy/
    cases/case_001..005/     五组数据、metadata、文件哈希
    test_conv_relu_pynq.py   桌面预检查与未来上板正确性测试
    conv_relu_cpu.c          同范围单线程 ARM C 基线源代码
    benchmark_conv_relu.py  未来上板性能脚本，预热3次/测量20次
```

PC 用 libconv_relu_cpu_pc.dll 仅用于 CPU C 正确性，不是 Linux/ARM 库；上传时排除它。上板 benchmark 会在板卡重新编译 libconv_relu_cpu.so。

## 运算边界

输入 [1,128,150] 的 INT8，时间维连续；权重 [128,128,1] INT8、ZP=0。INT32 累加和偏置→原 Q40/Q1（scale 0.06564070284366608、ZP=-15）→256 项 LUT→最终 Q2（scale 0.03660203143954277、ZP=-128）。Q1 的舍入和饱和必须保留。

输出停在 /xvector/block1/tdnnd1/nonlinear2/relu/Relu_output_0_QuantizeLinear_Output。后续原 DQ2 与所有 CAM 消费者仍由 CPU 处理；本目录不是完整网络部署。后置 BN 已在原导出卷积参数中折叠，此处不再重复折叠。

## 第一步：路径与参考数据

在 PowerShell 中：

```powershell
Set-Location 'C:\Users\Lenovo\Desktop\SonicArm\pynq_voiceprint\CAM-pretrained_models\FPGA-2\conv_relu'
& 'E:\condaData\envs_dirs\python3.11\python.exe' -B .\prepare_conv_relu.py
```

预期打印五组 PASS 和 256-entry LUT PASS。程序使用第一版已验证的内部 INT8 输入，没有重新执行音频前处理；只向本目录写数据。原始量化 ONNX 不修改。已生成的数据无需重复生成。

本次使用 W: 短路径，避免 Windows 260 字符限制。V: 保留给第一版。

```powershell
subst W: 'C:\Users\Lenovo\Desktop\SonicArm\pynq_voiceprint\CAM-pretrained_models\FPGA-2\conv_relu'
```

run_hls.ps1 会自动创建 W: 映射；若 W: 已指向其他目录，它会报错，不覆盖。重启后映射可能需要重建。Vitis 和 Vivado 都从 W: 打开工程。

## 第二步：Vitis C Simulation

HLS 顶层：conv_relu。Design source 只选 conv_relu.cpp；其所在目录的 conv_relu.h、layer_params.h 被 include。Testbench source 只选 tb_conv_relu.cpp。头文件和 .bin 都不能作为 design source 编译。

已有 HLS component 位于 W:/hls_workspace/conv_relu，可在 Vitis 中以 W:/hls_workspace 为工作区打开现有组件。若手动新建 HLS component，选择 Vivado IP flow、器件 xc7z020clg400-1、clock=10ns、上述 top/source，并按 hls_config.cfg 的绝对路径配置测试参数。

C Simulation arguments：W:/deploy/cases --all。测试程序直接从绝对路径读数据；因此不用把全部二进制复制到 simulator 的工作目录。运行 C Simulation 后查看 console 最后 CSim done with 0 errors。

对应的已验证命令入口：

```powershell
& .\run_hls.ps1 -Stage csim
```

覆盖五组真实输入、256 项 LUT、2048 个 Q40 随机乘积、正负半整数、饱和、零中心输入、变化权重/偏置和末尾时间 lane。

## 第三步：Vitis C Synthesis

在 Flow Navigator 运行 C Synthesis，或：

```powershell
& .\run_hls.ps1 -Stage synth
```

重点查看 hls_workspace/conv_relu/hls/syn/report/conv_relu_csynth.rpt 和三个 Pipeline 子报告：input_channels_frame_blocks、store_debug_channels_store_debug_frames、store_output_channels_store_output_frames。

本次初始综合通过：239088 cycles（2.391 ms）；DSP 22、BRAM_18K 57、LUT 8365、FF 5765；上述三个循环 achieved II=1。第一版综合 704784 cycles（7.048 ms）。这是 HLS 估计，不是板端调用延迟。

## 第四步：C/RTL Co-Simulation

选择 Verilog / XSIM，arguments=W:/；运行 C/RTL Co-Simulation，或：

```powershell
& .\run_hls.ps1 -Stage cosim
```

协同仿真使用默认歌唱输入，以及零中心输入、变化权重的边界输入，共3次 top 调用；五组真实输入均已在 C Simulation 中覆盖。验收报告 hls/sim/report/conv_relu_cosim.rpt 必须为 Verilog Pass。

本次 RTL 协同仿真已通过：277393 cycles（100 MHz 对应 2.774 ms），不是板端实测。原版 RTL 为764945 cycles；两版输出范围不同，不能把这个比值作为最终同范围 CPU/FPGA 加速比。

## 第五步：Package IP

Flow Navigator 运行 Package，格式选 Vivado IP Catalog，或：

```powershell
& .\run_hls.ps1 -Stage package
```

检查 W:/hls_workspace/conv_relu/hls/impl/ip/component.xml；IP 名称应为 xilinx.com:hls:conv_relu:1.0。Vivado IP repository 添加该 ip 文件夹，而不是 .cpp 所在根目录，也不使用第一版 conv1x1 的 IP。

## 第六步：Vivado 创建第二版工程

推荐新建工程位于 W:/vivado_workspace/conv_relu_vivado。FPGA-2 父目录已有的 vivado_workspace 不参与本次流程。

先读取并复制第一版 PS7 参数（已提供生成文件）：

```powershell
& 'E:\condaData\envs_dirs\python3.11\python.exe' -B .\export_ps_config.py
```

在 Vivado 2025.2 的 Tcl Console 执行：

```tcl
source W:/create_vivado.tcl
```

脚本只在本目录新建工程，不运行实现、不修改第一版。若工程已创建，直接 File → Open Project 打开 W:/vivado_workspace/conv_relu_vivado/conv_relu_vivado.xpr，不要再次执行创建脚本。

手动连线时与第一版一致：

- PS M_AXI_GP0 → axi_smc → conv_relu_0/s_axi_control。
- conv_relu_0 的 m_axi_gmem_input、m_axi_gmem_params、m_axi_gmem_output → 三输入 AXI Interconnect → PS S_AXI_HP0。
- PS FCLK_CLK0=100 MHz，连接 IP、互连、GP0/HP0 ACLK、reset slowest_sync_clk。
- FCLK_RESET0_N → proc_sys_reset；互连与外设使用对应的 active-low reset。使用稳定时钟，不将 reset 极性反接。
- PS 配置复用第一版 DDR/MIO 参数，启用 GP0 与 HP0。
- 控制地址0x40000000/64K；三个 m_axi 的 DDR 地址空间0x00000000/512M。
- 外部仅 DDR 与 FIXED_IO；本测试不需要 GPIO/PWM XDC。

脚本会 Validate Design、Generate Output Products、Create HDL Wrapper，顶层为 system_wrapper。新接口多了 post_lut 的 AXI-Lite 地址寄存器，上板脚本读取本版 HWH，不能照搬第一版寄存器常数。

## 第七步：综合、实现、位流

Vivado 中依次运行 Run Synthesis → Run Implementation → Generate Bitstream。遇到错误先读第一条 ERROR；不要通过降低 DRC 严重级别绕过连接/约束错误。

验收布线后 WNS≥0、TNS=0、WHS≥0、THS=0，无未约束内部端点，资源不超器件容量，bitstream 成功。HLS EstimatedClockPeriod 不替代布线后时序。

位流成功后，在该新工程的 Tcl Console 执行：

```tcl
source W:/collect_deploy.tcl
```

将配对文件复制到桌面 deploy/conv_relu.bit 与 deploy/conv_relu.hwh，同时生成 timing_routed.rpt、utilization_routed.rpt、drc_routed.rpt。只复制同一次工程生成的 bit/hwh。

## 第八步：换板后的上传、正确性与性能

本次不上传、不写 Samba。用户将 deploy 文件上传到独立新目录，例如 /home/xilinx/jupyter_notebooks/SonicArm/conv_relu_test，保留 conv1x1_test。排除 PC dll；不要把第一版 bit/hwh 混进该目录。

电脑预检查：

```powershell
& 'E:\condaData\envs_dirs\python3.11\python.exe' -B .\deploy\test_conv_relu_pynq.py --check-only
```

板端 Notebook：

```python
%run ./test_conv_relu_pynq.py --repeat 3
%run ./benchmark_conv_relu.py --warmup 3 --repeat 20
```

先正确性后性能。CPU 与 FPGA 均执行 Conv+Q1+LUT，均保留 INT32 输出，权重预先放 DDR。性能计时包括 CPU输入复制/调用，FPGA输入复制/缓存同步/启动轮询/结果同步及复制；编译、allocate、模型加载、测试用输出哨兵和比较不计入稳态调用耗时。该范围是固定融合段，不是完整 CAM++。

完整 CAM++ ARM 基线与真实模型 offload 接入按用户要求等换板后执行。未来关闭 INT32 调试输出时新建版本并同步修改 CPU 基线，重新综合及核验。

工具参考：[AMD 2025.2 命令说明](https://docs.amd.com/r/2025.2-English/ug1399-vitis-hls/vitis-v-and-vitis-run-Commands)、[Package](https://docs.amd.com/r/en-US/Vitis-Reference-Guide-UG1702/Packaging-the-RTL-Design)。
