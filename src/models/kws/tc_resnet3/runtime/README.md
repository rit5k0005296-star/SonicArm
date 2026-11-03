# TC-ResNet3 v5 PYNQ PS runtime

This is the active SonicArm phrase-recognition runtime. The model assets come from `TCResNet_Jingyuan_v5_20261026`; the SonicArm adapter and safety gate remain part of the existing PS runtime.

- Input: 16 kHz mono waveform.
- Active capture: 3.0 seconds from `src/ps/config.json`.
- Model window: 5.2 seconds / 83,200 samples.
- Adaptation: active-speech trim, peak normalization and center padding.
- Classes: 15 in the unchanged label order.
- Model output: classification only. Robot execution is decided by the system configuration and safety state machine, not by `decision_config.json` in this directory.

Run `python tc_resnet3_selftest.py` for an offline NumPy smoke test. This does not establish board, microphone, accuracy or end-to-end evidence.
