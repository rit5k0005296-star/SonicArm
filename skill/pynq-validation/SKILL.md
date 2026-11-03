---
name: pynq-validation
description: >-
  Compare golden data and generate PYNQ performance, Vivado timing, and utilization summaries from retained artifacts.
---
# PYNQ Validation

Use for numeric golden comparisons and verification-stage reporting. Read [verification stages](references/evidence_levels.md).

```sh
python scripts/validate_evidence.py --actual examples/actual.json --expected examples/expected.json --level STATIC --output result.json --json
```

Shape and tolerance failures are reported directly. Use `scripts/collect_report.py` to collect benchmark latency, Vivado timing-summary values, and utilization data into deterministic JSON and Markdown outputs. Keep the input reports beside the generated summary so every number remains reproducible.
