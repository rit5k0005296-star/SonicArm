# Portability matrix

| Target | Overlay | Driver | Data path | Reports |
|---|---|---|---|---|
| PYNQ-Z2 / Zynq-7000 | bit/HWH and required-IP contract | AXI-Lite MMIO or `register_map` | AXI DMA and Buffer synchronization | Vivado timing/utilization plus benchmark JSON |
| PYNQ-Z1 / Zynq-7000 | replace bit/HWH and required IP list | replace base/range/register contract | reuse DMA wrapper with target alignment | reuse artifact collector |
| Zynq UltraScale+ boards | replace board artifacts and IP list | replace address/register contract | select the target memory/coherency policy | reuse artifact collector |

All board-specific values are inputs rather than hard-coded project names or addresses.

