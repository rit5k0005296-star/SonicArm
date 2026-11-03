# PYNQ Agent Skill Suite

本套件基于 SonicArm——基于 PYNQ-Z2 的声纹鉴权与指令识别机械臂系统——实际开发过程中积累的 Overlay 管理、PS/PL 接口适配、数据通路调试和分层验证经验总结提炼而成。在保留真实工程经验与问题溯源的基础上，套件已去除声纹模型、语音指令和机械臂控制等具体业务依赖，形成可供其他 PYNQ 项目直接复用的通用 Agent Skill。

This project-local, removable suite helps FPGA/PYNQ teams audit Overlay artifacts, generate explicit MMIO drivers, classify data paths, run golden comparisons, and produce validation reports.

## Skills and relationship to prior work

- `pynq-workflow`: routes tasks and enforces safety/evidence states.
- `pynq-overlay-audit`: HWH/bit/manifest/IP-address audit and reusable Overlay session.
- `pynq-ip-driver`: interface-contract validation and MMIO skeleton generation.
- `pynq-data-path`: AXI DMA, HLS `m_axi`, AXI-Stream, and VDMA checks plus DMA/cache wrapper.
- `pynq-validation`: golden comparison and performance/timing/resource report generation.

`fpga-development` supplies RTL/evidence discipline; `xilinx-suite` supplies vendor-tool guidance; `verilog-generator` inspired staged negative testing. This suite independently implements the PYNQ runtime gap and contains no copied third-party runtime.

## Platforms and dependencies

CLI: standard-library Python 3.10+ (tested here on 3.13.9). Tests use `unittest`; pytest is optional. Runtime wrappers target the documented PYNQ `Overlay`, `ip_dict`, `register_map`, `allocate`, Buffer cache-sync, and AXI DMA channel APIs. PYNQ-Z2 is Zynq-7000 `xc7z020clg400-1`; SonicArm uses PYNQ 3.0.1 and Vivado/Vitis 2025.2. Other boards are supported through explicit board, address, and interface contracts.

## Five-minute quick start

From `skill/`:

```sh
python pynq-ip-driver/scripts/generate_driver.py --contract pynq-ip-driver/examples/add_ip_contract.json --output-dir quickstart_generated --json
python -m py_compile quickstart_generated/add_ip_driver.py
python pynq-validation/scripts/validate_evidence.py --actual pynq-validation/examples/actual.json --expected pynq-validation/examples/expected.json --level STATIC --output quickstart_result.json --json
python evals/run_evaluation.py
```

Expected machine status is `PASS`; generated code runs with injected `MockMMIO`. Re-running the generator into an existing directory intentionally fails to prevent overwrite.

## Install and invoke in Codex

Keep `skill/` in the project and ask Codex to use `$pynq-workflow` or one specialist by its folder path. For a local install, copy only the desired folder into a project-scoped `.codex/skills/`; remove it to uninstall. Do not run third-party installers or overwrite global `AGENTS.md`.

## Runtime integration

Use `OverlaySession` to open an Overlay, verify required IP names, retrieve an IP instance, and access its `register_map`. Use `DmaTransfer` for receive-before-send sequencing, alignment checks, cache synchronization, and timeout diagnostics. The wrappers accept injected backends, so the same host-side logic can be tested with fakes and used with PYNQ objects unchanged.

## Scope, failures, and observed basis

Overlay audit catches malformed HWH, missing IP, overlap, and hash mismatch. Driver generation rejects undocumented or invalid registers. Data-path checks cover length, alignment, cache contracts, channel availability, and timeout conditions. Validation covers numeric tolerance, benchmark statistics, timing summaries, and utilization reports. These rules derive from SonicArm integration issues involving artifact/version mismatches, HP/DDR versus DMA ambiguity, Overlay reloads, buffer synchronization, and repeatable result collection.

## Migration examples

Case A applies the static auditor to SonicArm FPGA-10 artifacts. Case B is an independent `add_ip` contract using the same generator, mock, and golden checker. Together they demonstrate reuse across two unrelated application contracts. Change board/device/profile and contracts rather than hard-coding an IP name or address.

## Evidence, licensing, and competition mapping

Results are under `evals/results/`. See [validation status](docs/validation_status.md), [traceability](docs/contest_traceability.md), [portability](docs/portability_matrix.md), and [provenance](docs/provenance_and_license.md). The suite focuses on reusable PYNQ integration: Overlay management, interface-contract host code, DMA/cache handling, golden comparison, and automated report generation.
