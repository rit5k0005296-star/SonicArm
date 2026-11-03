我正在做“基于PYNQ-Z2的声纹鉴权与指令识别智能机械臂系统”，当前继续优化CAM++的FPGA加速。请接续已有工程，在FPGA-6中实际完成第六版设计、电脑端验证和手动上板测试包，不要只给概念方案。

一、任务、技能与边界

项目根目录：C:\Users\Lenovo\Desktop\SonicArm
第六版目录：C:\Users\Lenovo\Desktop\SonicArm\pynq_voiceprint\CAM-pretrained_models\FPGA-6
第六版目前只有交接文档，尚未完成设计、仿真、综合、实现或上板验证。先检查实际目录，不覆盖可能新增的用户文件。

先读项目根目录AGENTS.md。默认使用fpga-development和FPGA-Agent技能集：RTL设计/审查优先fpga-development；根据任务读取vitis-hls-synthesis、vivado-sim、vivado-synth、vivado-constraints、vivado-impl、vivado-analysis、vivado-timing-closure、vivado-tcl等对应SKILL.md，均位于C:/Users/Lenovo/.codex/skills/<技能名>/SKILL.md。器件是xc7z020clg400-1，当前基线PL时钟100MHz，工具为Vivado/Vitis 2025.2。

未经我明确要求，不连接或操作开发板：不SSH、不远程执行、不加载Overlay、不写Samba。优先用已有电脑端结果副本分析。只在电脑端设计、构建、验证和打包，之后由我手动运行板端Notebook。保留FPGA-1至FPGA-5、原始模型及所有历史结果。新设计与自己的构建产物放FPGA-6，板端包最终由我手动放到SonicArm/test_1的独立子目录。不要假设现有fpga_v5包可直接移到test_1上一级：当前ARM端依赖查找按父目录test_1设计，移动需另行适配。

二、先读这些已有文件

V5根目录（下文V5）：
C:\Users\Lenovo\Desktop\SonicArm\pynq_voiceprint\CAM-pretrained_models\FPGA-5

本次用户真实上板运行编号：run_4c5e10fec13d43d9a055a4042888adb5。
最新分析及九份原始结果的电脑端副本：
V5\analysis\run_4c5e10fec13d43d9a055a4042888adb5\
重点读其中“实验结果分析.md”、analysis.json、cpu_hotspot_graphs.json、performance.json、raw_samples.json、profile_raw.json、profile_layers.csv、hardware_correctness.json、setup.json、initialization.json。

设计/接口/测试：
V5\src\pointwise.cpp、fcm.cpp、packed.h及头文件
V5\rtl\axi_perf_monitor.v、axi_perf_wrapper.v
V5\board_package\fpga_v5\v5_runtime.py、run_v5.py、README.md、BUILD_STATUS.md
V5\tests\tb_pointwise.cpp、tb_fcm.cpp、test_packed.cpp、make_rtl_harness.py、desktop_workflow_check.py
V5\tests\check_bus_connectivity.py、check_ip_sources.py、check_packed_mutation.py、audit_implementation.py、audit_manual_package.py
V5\verify_local_evidence.py、make_board_package.py
V5\run_hls.ps1、run_vivado.ps1、run_local_checks.ps1及相应cfg/Tcl
V5\reports\local_validation.json、implementation_acceptance.json、routed_summary.json、utilization_routed.rpt

注意：V5部分README、build_status或包清单的“尚未上板/actual_hardware=false”是交付时的本地构建快照。后来用户已手动完成真实板端测试；最新结论以本次run的正式结果为准。setup.actual_hardware=false、过程快照completed=false也不表示正式测试失败，不能只看单个False下结论。

三、历史背景及V5架构

V3覆盖55个1×1点卷积；V4增加12个FCM二维卷积。早期整网切图/CPU优化关闭时，混合推理反而比完整INT8 CPU慢。后来已完成静态CPU子图优化。V5在此基础上真正修改了HLS卷积内核，已经取得本轮实测的整网时延改善。V6的主要对照是当前V5及同板优化INT8 CPU，不能仅与早期较慢的未优化V3/V4比较。

V5仍为57个CPU会话、55个点卷积和12个FCM逻辑硬件调用，没有完成跨层融合或整网PL部署。当前Overlay是卷积测速最小系统，未集成完整音频/视频外设；正式测试从冻结的完整Fbank开始。

V5点卷积：8输出通道×8时间位置，MAC循环II=1；128输出通道权重块跨时间复用，时间块64。最大Cin=1024、Cout=512、单次T=2048。
V5 FCM：8×8并行MAC，MAC循环II=1；频率块4、时间块32；Cin/Cout≤32、频率≤80、K=1/3、频率步长1/2、单次T≤2048。长录音沿时间分块并保留halo；CPU上下文/注意力仍处理完整录音。
数据接口为64位m_axi密集字节布局，三个64位HP通路共享同一DDR。不要把多HP或II=1当作实际带宽/整网提速证明。

数值契约：INT8输入和权重，输入减zero-point后用INT16承载，INT32累加、64位重定量化乘积、ties-to-even舍入、饱和、LUT、残差及原量化边界。不得通过修改舍入、阈值、输入长度或换小模型来制造提速。

四、本轮正式测速基线（已经实测）

录音1=speaker1_b_cn_16k.wav，时长约4.9067秒；录音2=speaker2_a_cn_16k.wav，约5.3120秒。
以下均为同板、同一完整Fbank输入、CPU单线程、预热后每条每模式10次、两轮反序的模型中位时延：

模式               录音1/秒    录音2/秒
FP32 CPU           8.740       9.504
优化完整INT8 CPU   5.892       6.330
V4静态CPU图+硬件   6.591       7.290
V5                 5.237       5.613

V5相对V4加速比：1.259×、1.299×，时延降低20.54%、23.01%。
V5相对INT8 CPU：1.125×、1.128×，时延降低11.12%、11.33%。
V5相对FP32 CPU：1.669×、1.693×。
V5 RTF：1.067、1.057，尚未达到模型RTF<1。
V5 P95：5.320、6.012秒；最大值5.322、6.316秒。
V5运行时初始化约23.14/21.65秒，不是板卡上电时间，不计入推理时延。

正式口径：完整Fbank→完整CAM++→L2→余弦评分，包含剩余CPU、硬件执行、主机控制、拷贝/缓存同步。不含采集、WAV读取、Fbank、初始化、整数审计、结果保存。详细PL计数关闭。CPU未锁频；只有2条查询录音、每组10次，不能当作全数据集或长期稳定性结论。

正式计时分项的中位数：
剩余CPU：录音1 V4 3.062→V5 3.083秒；录音2 3.306→3.303秒。
硬件层回调合计：录音1 3.494→2.120秒；录音2 3.948→2.275秒。
CPU约占V5整网59%；此次收益主要来自硬件路径，CPU基本未变。分项中位数之和不要求严格等于整网中位数。

五、已经定位的瓶颈

逐层剖析每条/模式3次，以下为主机回调累计中位数，含搬运/控制/等待，且剖析有额外开销，不能称为纯MAC时间：
55个点卷积：录音1 V4 1.837→V5 0.669秒；录音2 2.165→0.704秒，回调加速比2.75～3.08×。
12个FCM：录音1 1.656→1.491秒；录音2 1.782→1.608秒，约1.11×。
V5 PL窗口合计：点卷积0.494/0.530秒，FCM 1.355/1.464秒。FCM约占全部PL窗口73%。

明确退步点：/head/conv1/Conv。
输入1×80×T，输出32×80×T，Cin=1，输出量大。
录音1 V4回调124.17ms，V5 265.08ms，V5 PL窗口241.83ms。
录音2 V4回调133.43ms，V5 287.25ms，V5 PL窗口261.49ms。
首层V5约慢到V4的2.13～2.15倍。不能把整个版本提速解释成每层都提速。

V5 store先逐字节重定量化，再通过packed.h/write_fragment写64位片段。T=489/529等非8倍数时存在非对齐读改写。FCM写总线字节11.52/12.46MB，逻辑INT8输出6.10/6.60MB，约1.89倍；点卷积也有类似放大。这个现象与重复整字写回吻合，但还未单独证明首层全部退步都由它造成。优先研究连续打包、跨片段合并写回、持续重定量化流水和Cin=1专用调度；任何新布局的主机重排成本也必须计入正式测速。

CPU热点：test_1/assets/v3/cpu_106.onnx、cpu_072.onnx、cpu_070.onnx等，每个热点子图约80～88ms，部分接口有约1MB FP32增长特征。已核对同指纹本地ONNX：每个示例有3个CAM卷积（linear_local、linear1、linear2）、ReduceMean、AveragePool、Concat、Q/DQ等共76个原始节点。尚未得到这些子图内部ORT优化后的逐算子耗时，不能将全部时间归咎于Concat或某个Conv。CPU约3秒不是全都Python/寄存器调用开销。

PL计数器覆盖启动控制写握手→完成中断，包含DDR/互连等待，不是纯MAC时间。六个端口的等待周期可重叠，不能直接当PE利用率/DDR利用率。写字节=64位数据拍字节，未按WSTRB折算；没有ARLEN直方图，也没有V4对应PL计数，不能声称实测了V4→V5流量降幅。计数器arm后依赖立即写ap_start的既有驱动顺序，不任意插入控制写。

六、正确性、质量和实现资源

V5用户板端hardware_correctness.json：actual_hardware=true、integer_exact=true、debug_on_off_exact=true。
3条完整录音通过67层当前输入INT8/INT32检查及调试开/关完整向量一致性；2051帧FCM halo两次实际调用、非整齐点卷积、保护区通过。debug=False仅表示关闭调试/逐层审计，不能当成验证失败。
当前样例中V5与V4完整向量和评分一致，没有发现相对V4的新增输出差异。
但原始QDQ严格漂移和相对优化INT8 CPU的质量门限仍失败，accuracy_matched_claim=false。V5−INT8 CPU余弦评分差为-0.007833、+0.010113。鉴权阈值未校准，只比较向量/分数；不能称为精度等价加速或正式鉴权验收。之前小CN-Celeb子集结果也不能替代全数据集EER/minDCF。
原冻结参考为test_1/results/run_2d8b1cfeaf0c47bfac486cd2a09e49f0；V5测试沿用该参考。新版本应同时保持整数正确性与独立质量评估，不能为了通过而放宽门限。

V5本地Vivado最终实现：100MHz，WNS +0.329ns、WHS +0.013ns、WPWS +3.750ns，TNS/THS/TPWS=0；完整路由、零路由错误、零DRC错误，约束覆盖检查通过。资源：LUT 46,500/53,200（87.41%）、DSP 206/220（93.64%）、BRAM Tile 110.5/140、FF 49,166/106,400、Slice 13,173/13,300（99.05%）。资源已较满，不能直接照搬增加一套完整引擎或盲目提高并行度。
仍保留FIFO LUTAR-1/PDCN-1569、BRAM复位控制REQP-1839、DSP流水等警告，以及PS7 DDR DQS参数提示。零DRC错误不等于零警告，production_signoff=false。普通推理通过不等于已经完成复位/重载/长期DDR稳定性和产品签核。

七、V6实施要求与可复用验证

优先保留V5已有效的点卷积收益，在资源预算内针对FCM首层及输出/重定量化/访存做有依据的实际硬件优化；再根据CPU内部算子耗时决定CAM算子复用或局部融合。目标是进一步降低整网时延，争取模型RTF<1；不要预先承诺固定加速倍率。若暂时不改CPU图，应冻结该部分，使收益归因清楚。

先简洁说明所选改动、资源与数值契约，然后直接在FPGA-6实作。只复制必要源码、配置、脚本、测试和资产引用，不整体复制V5庞大的Vivado/HLS缓存；V6工程、IP、bit/HWH和产物指纹必须匹配V6当前源码，不能拿V5旧bit/DCP冒充。

V5可复用证据：110个真实点卷积C用例、48个真实FCM C用例、两个内核C/RTL协同仿真、8个独立AXI背压RTL用例、1152个未对齐/保护字节用例、故障注入反例检查、计数器RTL测试、桌面原生C++/ORT完整录音回归。V6修改后要运行与改动对应的验证，不能沿用旧PASS充当新设计结果。覆盖T=489/529及下采样245/265等真实非整齐长度、尾通道、残差、LUT、舍入/饱和、调试开关、长录音halo和有限FIFO背压。

历史教训：FCM residual与input共享bundle曾让HLS合并DATAFLOW进程并死锁；必须检查真实生成的进程/FIFO行为。可变64位移位后减1的字节掩码曾导致宽进位链和负时序，V5已改直接译码。旧增量检查点曾导致时钟缓冲位置冲突和Out-of-date元数据；V6先用自己的普通综合/实现，不通过弱化时序约束或手工清除过期标记掩盖问题。

顺序：C参考/边界检查→HLS综合→C/RTL与AXI背压验证→匹配IP接入→Vivado综合/实现/完整时序及约束检查→匹配bit/HWH与包清单→我手动板端正确性→逐层/PL剖析→关闭剖析的同板整网测速。区分每个阶段的真实完成状态，编译/综合估计不能替代实际板端速度。

板端包需与优化INT8 CPU、V5同场比较，FP32/V4可保留为补充；使用相同完整输入、线程及计时口径。若融合减少了硬件调用，明确新调用计划及内部参考边界，不照抄55+12作为永远固定的次数，也不能省略真实性检查。

电脑工具：
D:\AMDDesignTools\2025.2\Vivado\bin\vivado.bat
D:\AMDDesignTools\2025.2\Vitis\bin\vitis-run.bat、v++.bat
D:\msys64\ucrt64\bin\g++.exe
E:\condaData\envs_dirs\python3.11\python.exe
板端CPU后端是ARMv7原生ONNX Runtime 1.17.1 C API/ctypes，不依赖Windows ORT wheel。桌面该Python目前未装onnx，已有analysis/inspect_onnx_nodes.py可读节点元数据。
V5脚本使用W:短路径和进程内TEMP/TMP；W:可能仍映射V5。V6须先核对映射并选独立可用短路径，同步修改配置；不覆盖别的盘符映射，不改系统时间/全局环境。按实际权限运行本地工具，遇到限制明确报告。

请从读取上述本地结果和V5关键源码开始，在FPGA-6持续完成可验证的新设计。保留真实失败、阶段证据、资源和性能限制；未经我明确要求不要上板。
