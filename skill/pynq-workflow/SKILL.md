---
name: pynq-workflow
description: >-
  Route PYNQ Overlay audit, IP-driver generation, data-path diagnosis, and evidence validation while preserving hardware safety and verification boundaries.
---
# PYNQ Workflow

Use for multi-stage PYNQ integration or when the correct specialist is unclear. Do not use it as an RTL/HLS/Vivado replacement or as permission to program hardware.

## Route

1. Record board, device, PYNQ/Python/Vivado versions, input files, and requested validation stage.
2. Overlay identity/IP map -> `pynq-overlay-audit`; contract/host API -> `pynq-ip-driver`; buffers/transfers -> `pynq-data-path`; golden/performance/build evidence -> `pynq-validation`.
3. Select inspection mode for artifact analysis or deployment mode for an explicitly requested runtime operation.
4. Emit concise `PASS` or `FAIL` results with the failing check and corrective action.

Acceptance records inputs, commands, outputs, hashes where applicable, and the completed validation stage. On failure, retry after a specific correction and keep hardware-project changes explicit.
