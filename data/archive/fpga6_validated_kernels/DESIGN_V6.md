# FPGA-6 design contract

Target: PYNQ-Z2, xc7z020clg400-1, Vivado/Vitis 2025.2, 100 MHz PL.
V: is reserved only after verifying that it is unused or maps to this directory.
W: remains mapped to FPGA-5. No prior build cache, IP, bitstream or DCP is imported.

## Selected change

Freeze the 57 CPU sessions, dense host tensor layouts, 55 pointwise and 12 FCM
logical calls, time chunk/halo rules and 8 x 8 MAC arrays. The pointwise source
is imported with the V6 identity; its datapath is unchanged and rebuilt locally.

FCM retains three DATAFLOW processes (load, compute, store). Inside store,
flatten scalar requantization across an entire 32-channel x 4-frequency x
32-time tile. This targets the short Cin=1 MAC schedule without adding another
engine: long scalar-pipeline setup/drain per 8-byte result is removed. A 4 KiB
tile changes the interleaved compute order to consecutive output words per row.
A 1 KiB carry array joins unaligned words across time tiles. Read/modify/write
is used only at row boundaries; byte enables use direct decode. No physical
DDR bandwidth or stage-cycle attribution is assumed from this source analysis.

Initial budget: unchanged 64 FCM MACs and one scalar requantizer; 6 additional
RAMB18 equivalents for tile, residual prefetch and carry storage; no replicated LUT.
Baseline integrated use: DSP 206/220, BRAM tiles 110.5/140, LUT 46500/53200,
Slice 13173/13300. HLS area and routed packing/timing are mandatory gates.
No promise of a fixed speedup or RTF below 1 before same-board measurement.

## Arithmetic, protocol and acceptance

INT8 input/weights; centered input held in INT16; INT32 accumulators; signed
64-bit multiplier product; ties-to-even rounding, saturation, exact LUT and
residual indices. All original quantization boundaries remain. Invalid configs
return -1 without DDR writes. AXI bases are 8-byte aligned with padded tails;
only logical output bytes may change. Debug off must not write accumulators.
ap_start accepts a single nonconcurrent invocation; ap_done/IRQ occur after
all output transfers. AXI may stall indefinitely for safety; liveness tests
use bounded deterministic stalls. Single FCLK0 clock; PS reset synchronized by
proc_sys_reset. No new CDC or external PL pins. Only PS DDR/FIXED_IO are external.

Order: native/reference/boundaries, HLS C simulation and synthesis, actual
generated DATAFLOW/II review, C/RTL cosimulation plus independent AXI stalls,
fresh IP integration, ordinary synthesis/implementation, full STA/constraints,
matched bit/HWH and package audit, then user-run board checks and timing.
Resource or timing failures remain recorded. No weakened clocks or exceptions.

V5 board result run_4c5e10fec13d43d9a055a4042888adb5 is the performance baseline;
its files are parsed and hashed in reports/v5_evidence_inventory.json. V6 has
no actual hardware validation until the user runs the package. Original QDQ
drift failures, accuracy_matched_claim=false and uncalibrated thresholds remain.
