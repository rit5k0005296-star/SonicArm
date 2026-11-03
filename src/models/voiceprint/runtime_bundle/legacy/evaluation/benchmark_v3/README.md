# 第三版完整模型测速

将压缩包中的benchmark_v3文件夹放入现有full_model_test/evaluation。
打开05_v3_model_latency.ipynb，依次运行两个代码格，返回V3_LATENCY_RATIO和BENCHMARK_COMPLETED。
不重跑之前的正确性/评测Notebook，不安装依赖；复用同版本03b硬件通过记录。

基线：同一PYNQ-Z2、ORT1.17.1完整兼容模型、单线程，分别开启/关闭图优化。
候选：完整兼容模型中55处卷积调用第三版IP，关闭INT32调试输出。
范围：固定原始Fbank→完整模型→L2→已注册声纹匹配。包含CPU剩余计算、CPU/FPGA切换、数据复制/同步。
不含音频采集/解码/Fbank、模型/Overlay/参数初始化；后者另记session_overlay_parameter_init_ms，运行库已预加载验证。
每种模式每条查询20次测量，分两块反序执行，每块预热3次；每块另有计时外验证和注册。
一次只加载一个运行时。结果可能需较长时间；Notebook实时输出进度。

已知严格QDQ漂移门控未通过，accuracy_matched始终False；本次只提供带精度差异说明的工程时延。
不放宽原质量门控，不声称同精度或音频端到端加速，不把软件整数参考时间用作CPU基线。
测速全部结果在本文件夹results。CPU频率不作修改，不声称锁频。
