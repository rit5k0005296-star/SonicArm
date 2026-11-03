# 第四版 FCM 初版桌面构建结果

已实现12个Conv2D、原量化边界后处理与4个残差分支；新工程同时保留原V3 pointwise IP。

| 验证 | 实际结果 |
|---|---|
| HLS C仿真 | 48组真实数据、6组合成边界用例通过 |
| RTL协同仿真 | 5组真实全通道/5帧及3组合成事务通过 |
| 目标时钟 | 100 MHz |
| 布线后WNS | 0.445 ns |
| 布线后WHS | 0.007 ns |
| DRC | 0 Errors |
| 双IP总LUT | 18818 / 53200 |
| 双IP总寄存器 | 23291 / 106400 |
| 双IP总BRAM36等效 | 66.5 / 140 |
| 双IP总DSP | 119 / 220 |

配对产物：deploy/fcm_v4.bit、deploy/fcm_v4.hwh；全部SHA256见desktop_build_evidence.json。
上板包：board_test_package/fcm_v4_test.zip，用户解压上传新fcm_v4_test文件夹、打开00_fcm_first_test.ipynb。
助手未执行板卡。完整300/67帧48组、两段递归FCM、分块接缝和新bit中的V3代表层仍需实际上板检查。

300帧整数FCM与原浮点QDQ有212/96000元素不同、最大5LSB，67帧样例一致；未将此改写为精度通过。
完整CAM++接入、扩大质量评测及同板CPU/V3/V4整网时延对照尚未完成，不提供第四版整网加速倍率或鉴权结论。
