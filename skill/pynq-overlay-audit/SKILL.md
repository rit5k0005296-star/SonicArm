---
name: pynq-overlay-audit
description: >-
  Audit PYNQ bitstream/HWH identity and provide reusable Overlay loading, IP lookup, and register_map verification.
---
# PYNQ Overlay Audit

Use for HWH XML structure, IP/address maps, artifact hashes, trusted-manifest identity, and a consistent Overlay startup procedure.

Inputs: HWH; optional bit, JSON manifest, required IP names, and board profile. Read [evidence rules](references/evidence_rules.md) for release conclusions and [troubleshooting](references/troubleshooting.md) for XML/address failures.

```sh
python scripts/overlay_audit.py --hwh design.hwh --bit design.bit --manifest manifest.json --json --output audit.json
```

The CLI returns 0 for `PASS` and 2 for `FAIL`. It checks parseable XML, non-overlapping declared ranges, required IP presence, and supplied manifest hashes. For runtime integration, import `OverlaySession` from `scripts/overlay_session.py`, list required IP names, then choose `open(download=False)` for inspection or `open(download=True)` for deployment. The wrapper verifies `ip_dict`, provides named IP lookup, and exposes `register_map` when the driver supplies it.
