# CAM++ 第四版：FCM二维卷积与残差后处理

本工程位于独立的 FPGA-4/fcm_engine，不修改前三版。工程进度与实际结果以 deploy/desktop_build_evidence.json、diagnostics/desktop_validation.json 为准；上板结果必须由用户手动执行产生。尚未完成第四版完整CAM++接入、整网精度验收或测速。

## 范围与接口

同一可配置FCM IP覆盖原模型全部12个Conv2D：10个3×3和2个残差投影1×1。输入/输出NCHW，batch=1，Cin/Cout≤32，频率≤80，单次时间≤2048。kernel为1或3，频率stride为1或2、时间stride为1，same对称padding。频率80→40→20→10，最终按原布局reshape为[1,320,T]。

INT8输入/权重、权重零点0、INT32偏置与累加。输入padding填原输入零点，实际缓存为减零点后的0。逐输出通道uint32乘数、按层Q38/39/40等可变移位，最近偶数舍入、加输出零点和INT8饱和。主机证明所有INT32部分和安全。

flags：bit0启用后处理LUT；bit1写INT32；bit2启用残差二维LUT且要求bit0。原Conv Q1的舍入/饱和先发生，再查表，不跳过或重排量化边界。非残差ReLU/DQ/Q使用256项表；残差DQ/Add/ReLU/Q使用65536项二维表，索引来自两支独立INT8域。用原scale、zero-point和FP32原图穷举生成，未将不同量化域的INT8直接相加，也未重折叠BN。相关表在NumPy FP32、Windows ORT1.31、1.17.1之间逐项检查；这不是ARM执行结果。

每次调用权重全部缓存片上；输入tile为4频点×32帧，包含真实窗口halo；8输出通道×4时间点形成32个MAC通路。LUT在调用开始缓存片上，后处理读一项输出一项。残差分支和层间结果当前仍经过DDR，未实现完整残差块的片上驻留。长录音每次≤2048帧，K3调用携带真实左右各1帧halo、仅回填有效区域，禁止直接分块补零造成接缝错误。

AXI：8个DDR指针，10个标量；3个m_axi数据bundle，GP0控制，HP0访问DDR，100MHz。HWH解析寄存器，不沿用旧偏移。新双IP设计同时保留原V3 pointwise_0和新增fcm_0。V3打包IP与PS7配置只读复制并留SHA256清单；不能因为复制旧IP就宣称新bit已通过全部55层。

## 验证数据与数值边界

原QDQ模型SHA256：c0c4103c23301e26aa58e106933bbeaefbfdc7d0708052729b3155f7f824560f。

使用两段原始规范Fbank的300/67帧前缀做设计验证：每段12组原图独立输入和12组递归整数输入，共48组。前缀截取仅用于算子设计，不更改评测协议。Python FP64 GEMM参考可精确表示所有有界整数部分和，再由独立C++ INT64嵌套循环核对；HLS必须逐点等于整数参考。

整数重建与原浮点QDQ仍有差异：300帧完整FCM输出212/96000元素不同，最大5LSB；67帧样例一致。原第三版0.001评分漂移失败结论仍保留。这些设计样例不能证明整网EER、minDCF或鉴权准确率；正式阈值未校准。

RTL验证：5个真实全通道/原频率维度用例，每个5帧，覆盖首层、降采样、投影、残差、末层；3个合成事务覆盖通道/空间/tile尾部、T=2048、F=80及debug关闭，共8笔。完整300/67帧、48组数据通过C仿真，实际板卡仍需用户验证。MAXI depth只用于RTL测试台，不表示硬件最大运行时地址尺寸。

## 重现流程

工具为已安装Vitis HLS/Vivado2025.2，器件xc7z020clg400-1。与第三版一样使用普通Windows权限启动，避免受限环境中已有的xcd析构崩溃；不需要管理员运行。第四版单独使用V:短路径，不改P:或第三版工程。V:已被其他路径占用时脚本拒绝覆盖。必须从V:路径打开xpr，避免Windows长路径子综合问题。

```powershell
cd 'C:\Users\Lenovo\Desktop\SonicArm\pynq_voiceprint\CAM-pretrained_models\FPGA-4\fcm_engine'
& E:\condaData\envs_dirs\python3.11\python.exe -B prepare_fcm.py
& E:\condaData\envs_dirs\python3.11\python.exe -B prepare_integration.py
.\run_hls.ps1 -Stage csim
.\run_hls.ps1 -Stage synth
.\run_hls.ps1 -Stage cosim
.\run_hls.ps1 -Stage package
.\run_vivado.ps1 -Stage create   # 只新建一次，已有工程不要重复create
.\run_vivado.ps1 -Stage build
```

重新打开使用 `.\run_vivado.ps1 -Stage gui`，工程为 `V:/vivado_workspace/fcm_vivado/fcm_vivado.xpr`。只有实际RTL通过、布局布线setup/hold非负、DRC无错误且bit/hwh配对后，才冻结证据并打包：

```powershell
& E:\condaData\envs_dirs\python3.11\python.exe -B freeze_evidence.py
& E:\condaData\envs_dirs\python3.11\python.exe -B make_board_package.py
& E:\condaData\envs_dirs\python3.11\python.exe -B validate_desktop.py
```

本地驱动测试用真实C++核心和模拟MMIO/DDR，验证48组、debug开关、2051帧接缝、参数类型、内存guard及超时保留缓冲区，不算实际硬件通过。保留PS7原DDR负skew警告和AXI协议转换位宽警告，不通过随意改DDR参数消除提示。

## 手动上板与后续

用户在电脑解压 board_test_package/fcm_v4_test.zip，完整上传新fcm_v4_test文件夹到板卡SonicArm同级目录；打开00_fcm_first_test.ipynb依次执行校验、冒烟、完整FCM。无需音频线或联网安装依赖。不要覆盖pointwise_test/full_model_test，不并行运行其他Overlay。IP超时/中断后保持kernel直到断电重启，禁止马上释放可能仍被硬件访问的DDR。

上板测试包括两段各12层真正连续调用、2051帧小通道K3分块、一个原V3代表层共存回归；返回smoke.json与correctness.json。通过后才进入完整CAM++的FCM+55层接入、对原CPU/V3的向量和评分变化、同板整网时延对照。当前不提供第四版整网加速倍率或精度接受结论。
