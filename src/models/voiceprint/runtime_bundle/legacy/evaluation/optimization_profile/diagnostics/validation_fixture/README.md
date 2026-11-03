# CPU 子图优化对照与逐层剖析

在电脑解压，把整个 `optimization_profile` 文件夹复制到开发板已有的：

`/home/xilinx/jupyter_notebooks/SonicArm/full_model_test/evaluation/`

它与 `benchmark_compare` 同级，不覆盖旧代码、模型、bitstream 或旧结果。不需要联网、pip install、重新综合或执行解压代码。依赖已经成功运行的 06 四路对照包。

打开本文件夹中的 `07_cpu_graph_optimization_profile.ipynb`，先关闭其他使用 FPGA 的 Notebook，并重启本 Notebook 的内核。按顺序执行。

第 2 版修复 Notebook 校验：保存输出、增删空行、修改注释和追加空单元格不会导致失败；首格的 `PROFILE_REPEATS`、`REPEATS`、`WARMUP` 可按要求调整为整数。执行语句和调用顺序仍受校验，其他 Python 文件仍按 SHA256 校验。覆盖升级后重启内核，重新运行首格创建新 RUN。若旧 RUN 已完成基线剖析，可以保留旧结果，跳过第二个代码单元格，直接运行 `correctness_report=correctness(RUN)`。

## 测什么

- 完整 INT8 CPU：ORT_ENABLE_ALL，1 线程。
- V3 OFF / ON：同一 V3 bitstream、55 个点卷积；CPU 会话分别关闭/开启 ORT 全部图优化。
- V4 OFF / ON：同一 V4 双 IP bitstream、12 个 FCM 与 55 个点卷积；CPU 会话分别关闭/开启 ORT 全部图优化。
- 保留 52 个池化兼容修改和原量化边界；不改权重或手动删除 Q/DQ。
- 三段原始完整 Fbank 用于正确性检查；两段查询用于测速和剖析。复用原注册录音进行余弦评分。

## 顺序与门控

1. `OPT_SETUP_PASS`：核对依赖指纹、旧的真实硬件接入报告、已完成测速报告以及原始特征。
2. `BASELINE_PROFILE_COMPLETED`：先测现有 CPU INT8、V3 OFF、V4 OFF 的逐层耗时。复用旧的真实硬件接入报告，每次向量还必须与旧的同模式向量完全相同。可先返回本阶段文件，再继续后续优化对照。
3. `OPT_ENGINEERING_READY`：四个混合模式分别运行当前输入的独立软件整数参考和真实 FPGA，检查所有层 INT8/INT32，最终向量必须与该模式的软件整数参考完全相同。
4. `OPT_PROFILE_COMPLETED`：分别记录优化前后 CPU 会话和 FPGA 每层耗时、输入输出数量/字节/尺寸，打印每个模式和查询最慢的八项。
5. `OPT_BENCHMARK_COMPLETED`：关闭详细剖析，预热后做两轮反序正式测速。默认共 10 次/模式/查询；需要与 06 相同样本数可改为 20，必须是偶数。

`optimization_drift_gate` 比较同版本 OFF 与 ON；`original_QDQ_drift_gate` 比较原完整 OFF QDQ CPU。门限沿用 cosine >=0.99999、relative L2 <=0.01、分数绝对变化 <=0.001，均为数值诊断门限。任何 false 都保留；硬件整数匹配通过只允许标为工程时延的测试，不能把该结果写成精度一致的加速比。阈值未校准，不输出身份通过/拒绝。

若数组不合法、硬件整数不一致、输出不稳定或初始化失败，停止该阶段并保留日志。不要继续下一单元格。硬件执行中超时或中断时，保持当前内核，先对开发板断电重启后再重启内核；不要在活跃硬件访问 DDR 时释放缓冲区或加载其他 Overlay。

## 输出

全部输出在 `optimization_profile/results/run_<编号>/`：

- `baseline_profile_raw.json` / `baseline_profile_summary.csv` / `baseline_profile_summary.json`：第一个剖析阶段的当前版本逐层明细和汇总；这组就是现在优先返回的文件。
- `correctness.json`：优化漂移、原模型漂移、硬件逐层一致性与评分。
- `profile_raw.json`：每个 CPU 会话的耗时、所有输入/输出张量名称、尺寸、dtype 和字节，总数量/总字节及最大的 8 个张量；每个 FPGA 层的 INT8 输入输出尺寸和字节，以及寄存器、输入、启动至完成、输出、拼接时间。
- `profile_summary.csv` / `profile_summary.json`：按模式、录音、层汇总中位数和 P95，可按 `median_ms` 排序。
- `performance.json` / `summary.csv`：未开启详细剖析的正式测速。
- `raw_samples.json`：每个正式样本；每次完成后持久化。
- `*_failed.json`：错误和硬件可能仍活跃的状态。

CPU 时间包含原 native C API 桥的张量封装和输出复制；不是仅算子内核时间。V3 是 56 个 CPU 会话；V4 将首个会话拆成 FCM 输入和尾部，实际为 57 个 CPU 会话。FCM runner 的 Python 外围逻辑还有少量未包含在逐层 callback 内的开销，因此不能把逐层时间简单相加当正式整网结果。

FPGA 启动至完成的时间包含 PL DDR 访问与主机轮询，不能称为纯 MAC 时间。显式拷贝时间小，也不代表 PL 内部访存没有瓶颈。详细剖析本身增加开销，`profiled_wall_ms` 只用于诊断。正式计时范围为固定 Fbank → 完整模型 → L2 → 余弦，排除采集、读 WAV、Fbank、模型/Overlay 初始化、整数审计、日志写入。初始化单独记录。

开发板 512 MiB，CPU 会话继续沿用关闭独立内存 arena/memory pattern 的设置，一次只保留一个模式。完整 ORT 优化仍可能改变内存占用，实际板卡能否加载及收益以本轮日志为准。

本包不含 Linux 或 Windows 运行库，不向开发板安装软件。桌面验证不是 ARM/FPGA 正确性或性能证明。
