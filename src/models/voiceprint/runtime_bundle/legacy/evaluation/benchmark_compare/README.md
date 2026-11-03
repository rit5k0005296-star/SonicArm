# 四种完整CAM++实现的同板效率对照

先在电脑解压 `cpu_v3_v4_compare.zip`，将完整的 `benchmark_compare` 文件夹放进板卡现有 `full_model_test/evaluation/`。
保持原full_model_test内容与test_results不变，不需要执行解压代码。无需音频线、联网pip、PyTorch或Python ONNX Runtime；复用已有ARMv7原生ORT和PYNQ。

打开 `06_cpu_v3_v4_compare.ipynb` 顺序执行四个代码格：校验/建结果目录→第四版独立硬件检查→完整模型接入检查→正式测速。每格成功后再进入下一格，结果写本文件夹results。第一次独立硬件检查会加载第四版双IP并验证原V3代表层、48组FCM、两段递归FCM和分块接缝；随后针对三段未经截取的完整规范Fbank重新检查V3/V4全部实际中间张量，不能用独立样例冒充整网。

四种完整模型配置：

| 配置 | 运算方式 | CPU优化 |
|---|---|---|
| cpu_fp32 | 完整FP32在板载ARM运行，作为原始精度参考 | ORT_ENABLE_ALL，1线程 |
| cpu_int8 | 完整INT8 QDQ在同一ARM运行，作为FPGA主基线 | ORT_ENABLE_ALL，1线程 |
| v3 | 完整混合模型，55个1×1卷积实际调用原V3 IP | 复用已验证CPU分段图，原策略优化关闭 |
| v4 | 完整混合模型，12个FCM卷积及残差后处理+55个1×1均实际调用双IP | 同样CPU分段策略；只切除CPU中的FCM |

所有版本采用相同的52个无显式padding AveragePool兼容语义，避免旧ORT1.17.1池化问题造成不公平基线。FP32兼容副本的权重保持不变，原始文件不改；来源与改动在assets/provenance.json。FP32与INT8的倍率包含精度策略变化，主结论应优先看cpu_int8/v3和cpu_int8/v4；cpu_fp32另外报告。

统一计时范围：固定完整原始Fbank→整个CAM++→192维向量L2→与独立注册录音的余弦分数。包括剩余CPU算子、CPU/FPGA切换、寄存器地址与尺寸更新、DDR复制、缓存同步、硬件轮询、返回和后处理。排除采集等待、读取/解码音频、Fbank生成、逐层整数参考、文件写出、模型/Overlay/参数初始化。初始化另报，是运行库已预载的进程内会话初始化，不是假称断电冷启动。RTF用原WAV真实时长计算，表示模型处理实时系数，不含采集和前处理。

先有CPU分图重建通过、整网硬件INT8/INT32逐层相等、硬件与各自整数模型最终向量逐点相等后，才做时延。原相似度/相对L2/分数漂移门限保持.99999/.01/.001，是否通过单独记录；数值漂移失败不会被改写成精度通过。阈值未校准，不输出身份接受/拒绝，也不把三段示例写成EER评测。

正式测速：20次/模式/查询，两条查询，分两轮并反转执行顺序；每轮每条先预热3次。一次只加载一个完整运行时，所有计时外验证及调试INT32关闭。V4的参数驻留DDR、共享scratch，初始化分配不放进循环；12层间及残差分支仍经DDR，实测包含这些开销。V3使用原已验证驱动和bit；V4使用新配对bit/hwh并共享一次Overlay加载，不在每层或每个IP之间重配置FPGA。

输出summary.csv、summary.md、performance.json、raw_samples.json、initialization.json、integration.json。每条查询分别列中位数/P95、RTF、INT8_CPU/V3、INT8_CPU/V4、V3/V4，以及FP32参考倍率。倍率>1为分母更快，<1为更慢；不预设第四版一定更快。保存每次推理输出稳定性、实调硬件次数、CPU频率/governor/内存/温度只读快照，不改频率也不声称锁频。

等待每次推理进度，In[*]期间不要重复启动，不并行运行其他Overlay。发生异常先停止并返回完整输出。硬件超时或运行中中断时保持当前kernel直到板卡断电重启；不要kill子进程或立刻释放活动DDR。本Notebook直接在持久kernel运行。没有助手上板执行记录，桌面软件/模拟MMIO测试不算板卡验证。

先前full_model_test的正确性、03b诊断和04a评分评测都不应当拿总耗时当测速。原03b含整数参考/硬件调试；04a含逐层审计。另有benchmark_v3测速草案，本统一入口替代它进行本次正式四方对照，保留旧文件和历史结果。
