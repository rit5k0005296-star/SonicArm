# Build and Packaging

## Board package

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build\scripts\build_board_package.ps1
```

该命令从 `src/` 和 `board/artifacts/` 组装板端扁平目录，输出到 `board/generated/`，并生成逐文件 SHA-256 清单。

## Vivado project

`build/tcl/create_fpga10.tcl` 需要 Vivado 2025.2、PYNQ-Z2 器件支持及官方 PYNQ video IP。为避免重复提交第三方仓库，官方 IP 不包含在本仓库中。执行前设置：

```powershell
$env:PYNQ_IP_ROOT = "C:\path\to\PYNQ\boards\ip"
```

然后运行 `build/tcl/run_create_project.ps1` 与 `build/tcl/run_build.ps1`。工程生成到 `build/vivado/`，报告生成到 `build/reports/`，导出的 BIT/HWH 位于 `build/export/`。


