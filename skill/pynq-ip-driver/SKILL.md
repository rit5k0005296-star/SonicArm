---
name: pynq-ip-driver
description: >-
  Validate explicit PYNQ IP interface contracts and generate mock-testable MMIO driver skeletons without guessing registers.
---
# PYNQ IP Driver

Use when a documented AXI-Lite/register interface needs a PYNQ Python skeleton. Do not infer algorithm semantics, control protocol, buffer shapes, or undocumented registers from HWH alone.

Read [contract schema](references/contract_schema.md), then run:

```sh
python scripts/generate_driver.py --contract examples/add_ip_contract.json --output-dir generated --json
python -m py_compile generated/add_ip_driver.py
```

The output directory must not already exist. Generation succeeds only after name, offset, width, access, and duplicate checks. Inject `MockMMIO` for PC tests, or bind the generated driver to the verified base/range from `Overlay.ip_dict`. When a PYNQ driver exposes `register_map`, prefer it for named register inspection and retain the contract for automated host-code generation.
