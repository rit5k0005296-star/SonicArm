# TC-ResNet2 PYNQ PS测试包

本目录是NumPy-only识别测试包，不依赖PyTorch，不发送机械臂命令。

要求输入为16 kHz、单声道、PCM16 WAV。新版使用4秒窗口、活动段裁切、峰值0.8归一化，以及训练集mean/std特征标准化。

板端先运行：

```bash
cd /home/xilinx/jupyter_notebooks/SonicArm/test_1/tc_resnet2_ps
python3 tc_resnet_selftest.py
```

看到 `status: passed` 后测试WAV：

```bash
python3 tc_resnet_infer_wav.py /home/xilinx/jupyter_notebooks/SonicArm/test_1/fpga_v8/v8_test_20221022_230410_16k_mono.wav
```
