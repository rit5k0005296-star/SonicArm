# PYNQ runtime

这里保存 SonicArm 当前正式 PS 端源码。源码在 GitHub 中按功能拆分，打包脚本会将下列目录转换为板端布局：

- `src/ps/arm` -> 板端包中的 `arm_control`
- `src/ps/ui` -> 板端包中的 `ui`
- `models/kws/tc_resnet3/runtime` -> `tc_resnet3_ps`（当前为 `Jingyuan_v5_20261026`，兼容3秒采集）
- `models/kws/tc_resnet2/runtime` -> `tc_resnet2_ps`
- `board/artifacts/*.bit|*.hwh` -> 板端根目录

`config.json` 是当前正式配置；`config.example.json` 是同一配置的公开模板副本。板端仍从相邻 `fpga_v8/v8_runtime.py` 和既有前端常量文件复用 CAM++ 运行依赖。

`models/kws/history/` 保留v2、v3和v4模型证据，不进入当前板端构建。模型运行目录中的 `decision_config.json` 只描述分类包边界；机械臂是否执行仍由正式配置与安全状态机决定。

