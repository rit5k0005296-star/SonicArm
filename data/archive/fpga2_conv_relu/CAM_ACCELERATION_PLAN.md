# CAM++ 后续加速方案

工作范围：只在桌面 SonicArm 中开发。第一版 FPGA-1/conv1x1 保留；本次从 FPGA-2/conv_relu 开始。更换板卡后再做板端基线和性能测量，当前目标仍为 PYNQ-Z2 / xc7z020clg400-1 / 100 MHz。

## 已确认的计算分布

对当前 Chinese-common 权重，以 [1,300,80] 输入执行完整 PyTorch 前向，按每个 Conv/Linear 的实际输出形状统计 MAC：总计 1,688,721,408 MAC。FCM Conv2D 占 42.43%；52 个瓶颈 1×1 卷积占 34.85%；三个 transition 卷积占 10.48%；CAM 局部卷积占 5.68%；注意力卷积占 4.73%。第一版固定层占 0.146%。这些比例不含 BN、池化、Q/DQ、搬运，不能代替 ARM 耗时 profile。

## 阶段 A：本次实施，固定连续段与 16 路乘加

- 目录：FPGA-2/conv_relu。
- 输入：原 /xvector/block1/tdnnd1/linear1/Conv 的 INT8 输入 [1,128,150]。
- 范围：INT32 Conv → 原 Q1 饱和/舍入 → DQ1 → ReLU → Q2；停止于 CAM 分支之前。
- 输出：[1,128,150] INT8，scale=0.03660203143954277，zero_point=-128。接回原图时由 CPU 执行原 DQ2，供给 local Conv、ReduceMean、AveragePool 等全部消费者。
- 并行：4 时间位置 × 4 输出通道；输入通道串行，输入广播复用。
- 数值：沿用原 Q40 和 INT32 偏置；后处理为穷举 ONNX 的 256 项表。保留原 Q1 的舍入和饱和，不能直接从 accumulator 量化到 Q2。
- 首轮保留 INT32 调试写回。不同类型输出分开成连续写循环。
- 参考数据使用第一版五组已验证内部输入，在当前原始 ONNX 上生成融合参考；没有重新执行音频前处理。默认根目录数据沿用歌唱 case_004。
- 验收：五组 C 仿真、LUT 全域、舍入/饱和/变化输入；RTL 真实输入+零中心输入+变化权重；100 MHz 时序；后续五组上板逐点核验。

阶段 A 证明实现方法，不代表完整模型有显著提升。上板后比较 CPU 同一融合段与 FPGA 调用延迟；关闭调试输出必须让两端输出范围一致。

## 阶段 B：多层复用的 1×1 引擎

先完成本次 Vivado/上板验证，再另建 FPGA-2/pointwise_engine，不修改阶段 A。

1. 固定一组计算硬件，运行时配置 Cin/Cout/T、输入/输出 zero point、逐通道 bias/scale、后处理模式。逐层加载 DDR 权重，不为 52 层复制硬件。
2. 引入输出通道/时间/输入通道分块；片上缓存大小固定，避免把大通道整段激活放进 BRAM。支持如 128→128、256→128、992→128、1024→512 等真实模型形状。
3. 先选择少量真实层逐点验证，再覆盖 52 个瓶颈层和 3 个 transition 层。这两类约占 45.33% MAC。
4. 每层量化参数独立；当前 uint32 Q40 的倍率范围有限，不能假定其他层全部适用。逐层检查动态范围、INT32 部分和边界；必要时设计并验证通用乘数+移位格式。
5. 只对经图检查证实等价的模式融合。残留 BN、ReLU、CAM 的浮点乘法不能直接按原层的表处理；尤其没有 INT8 输入边界的 BN 不能强行套 256 项表。
6. 在完整模型执行器中替换真实子图，保留所有 CAM/Concat 支路与缓存生命周期。仅有 .bit 不会自动让 ONNX Runtime 调用 IP。

阶段 B 先保证真实模型调用与精度；是否继续按单层交接，还是形成多算子连续段，由板端 profile 判断。BN 与 CPU/PL 交接可能成为下一瓶颈。

## 阶段 C：FCM 二维卷积

另建 FPGA-2/fcm_engine。实现 3×3 Conv2D、步长和边缘 padding、原图合法的残差/激活/量化。使用行缓冲与分块缓存，权重/大激活在 DDR，避免整张特征图驻留片上。对残差两路的 scale、zero point、相加时的 dtype 和饱和逐项检查。

先验证一个真实残差块，再扩展全部 12 个 FCM 卷积。FCM 与阶段 B 两类卷积合计覆盖约 87.76% MAC；覆盖率不是整网耗时占比，也不是预期加速比。

## 阶段 D：剩余热点与整网交付

- 根据 ARM profile 决定是否加入 k=3/5、dilation=1/2 的 Conv1D、CAM 注意力及池化。
- CAM 含全局和分段池化，不能假定完整网络可以从首帧到最终声纹向量无等待地流式输出。
- 不改变原模型/录音条件，测量完整 Fbank→192 维 embedding 的 PS-only 与 PS+PL 中位数/P95、RTF、内存、资源及时序。
- 设计目标为完整 CAM++ ≥2×，争取 3–4×；这是规划目标，不是本次仿真结论。模型输入长度需分别报告，不能将固定 300 帧实验替代完整 CN-Celeb 评测。
- FPGA 输出与原 INT8 模型对照，重新验证 embedding、EER/minDCF 和固定阈值 FAR/FRR。加速不自动提高识别精度。

## 工具流程和阶段门

每阶段均按：ONNX 图/参数核验 → 独立软件参考 → Vitis C Simulation → C Synthesis/II/资源 → C/RTL Co-Simulation → Package Vivado IP → Vivado PS/AXI 集成 → 综合/实现/时序/DRC → .bit/.hwh 配对 → 用户上传并上板逐点比较 → 同范围 ARM 性能比较。

本次逐步操作见 conv_relu/README.md。板端基线和上板性能按用户要求留待换板后执行。原项目的 PC/GPU profile 不代替 PYNQ ARM profile。
