# 小规模声纹评测

解压后，将压缩包中的evaluation文件夹放入板卡现有full_model_test。
打开evaluation/04a_cnceleb_score_pilot.ipynb，依次运行三个代码格，先CPU、后FPGA。
第一格会将以前散落在full_model_test根目录的五项评测专用文件收拢到evaluation/legacy_root_upload，保留原件。
模型、运行库、V3硬件及之前的验证结果继续复用；不用重跑前面的Notebook。

目录：
- 04a_cnceleb_score_pilot.ipynb：评测入口
- quality_pilot.py：评测脚本
- data/eval：12条完整音频与32条官方试验列表
- data/features：对应完整录音的原始canonical Fbank
- data/subset.json：固定选择规则、音频/特征哈希和来源
- results/pilot_编号/cpu、fpga：本次日志、缓存、原始向量、分数和指标
- legacy_root_upload：第一次运行时收拢的旧评测文件（如果有）

4名说话人、每人2条测试录音；完整注册音频不裁剪，官方标签和试验顺序保留。
长录音的NumPy前处理未通过原门限，因此本轮使用随包冻结的原始Fbank，隔离模型替换影响。
不测试板卡前处理、采集或端到端速度；EER/minDCF仅作小子集诊断，不作完整准确率结论。
正式鉴权阈值仍未校准，不根据本子集选择部署阈值。
每条音频完成即保存校验缓存，中断后重跑同一格可继续。每阶段最多7200秒，硬件30秒超时阈值不变。
