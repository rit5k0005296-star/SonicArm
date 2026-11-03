# Project source map

| Source | Location | Reused insight |
|---|---|---|
| FPGA-10 bit/HWH | `FPGA-10/export/` and board packages | Overlay artifact naming, HWH parsing and required-IP checks |
| routed timing/utilization | `FPGA-10/vivado/.../impl_1/` and `report/fpga/` | timing/utilization report fields and automated summary format |
| PYNQ 3.0.1 source tree | board image source package | Overlay, Buffer and DMA host API patterns |
| VDMA and AXI reports | FPGA-10 Vivado runs | explicit distinction among AXI DMA, VDMA, AXI-Stream and HLS `m_axi` |
| development interactions | project collaboration records | repeated failure patterns, corrective workflow and reusable prompts |

