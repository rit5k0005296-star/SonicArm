---
name: pynq-data-path
description: >-
  Classify PYNQ data paths and provide reusable AXI DMA transfer, alignment, timeout, and cache-consistency handling.
---
# PYNQ Data Path

Use for buffer, cache, timeout, and transfer-path checks. Never call HLS `m_axi` an AXI DMA; VDMA is frame-oriented. Read [path matrix](references/path_matrix.md) and [buffer safety](references/buffer_safety.md).

```sh
python scripts/data_path_check.py --config examples/dma_loopback.json --json
```

For AXI DMA host code, use `scripts/dma_transfer.py`. `DmaTransfer.exchange()` validates contiguous-buffer metadata and alignment, starts receive before send, applies the supported `sync_to_device`/`flush` and `sync_from_device`/`invalidate` APIs, and reports missing channels, invalid lengths, alignment faults, cache API mismatches, and bounded-poll timeouts.
