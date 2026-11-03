# Contest traceability

| Requirement | Implementation | Verification |
|---|---|---|
| General Overlay loading and verification | `pynq-overlay-audit/scripts/overlay_session.py` | injected Overlay tests cover loading mode, required IP and `register_map` |
| Register mapping and `register_map` usage | Overlay `ip_dict` verification plus named register-map accessor | missing IP/map produces a precise error |
| Reusable DMA transfer and cache consistency | `pynq-data-path/scripts/dma_transfer.py` | receive-before-send, alignment, length, timeout and cache API tests |
| Host code from interface contract | `pynq-ip-driver/scripts/generate_driver.py` | schema validation, generated Python compilation and MockMMIO execution |
| Golden reference comparison | `pynq-validation/scripts/validate_evidence.py` | exact, tolerance and shape-mismatch tests |
| Performance/resource collection and reporting | `pynq-validation/scripts/collect_report.py` | benchmark latency statistics and Vivado timing/utilization parsing |
| Reusable outside SonicArm | parameterized paths, IP names, addresses, buffers and reports | independent add-IP contract and fake Overlay/DMA backends |

The five Skills are separated by responsibility and can be copied individually or invoked through `pynq-workflow`.

