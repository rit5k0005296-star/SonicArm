#ifndef SONICARM_CONV1X1_H
#define SONICARM_CONV1X1_H

#include <stdint.h>
#include "layer_params.h"

#define CONV_INPUT_ELEMENTS (CONV_BATCH * CONV_CIN * CONV_T)
#define CONV_WEIGHT_ELEMENTS (CONV_COUT * CONV_CIN)
#define CONV_OUTPUT_ELEMENTS (CONV_BATCH * CONV_COUT * CONV_T)
#define CONV_FRAME_LANES 4
#define CONV_REQUANT_SHIFT 40

static_assert(CONV_BATCH == 1, "This kernel supports batch size 1");
static_assert(CONV_KERNEL == 1 && CONV_STRIDE == 1 && CONV_PADDING == 0 &&
              CONV_DILATION == 1 && CONV_GROUPS == 1,
              "Only ungrouped pointwise Conv1D is supported");
static_assert(CONV_INPUT_ZERO_POINT >= -128 && CONV_INPUT_ZERO_POINT <= 127 &&
              CONV_OUTPUT_ZERO_POINT >= -128 && CONV_OUTPUT_ZERO_POINT <= 127,
              "Activation zero points must be signed INT8");

// Host-side conversion only:
// q40[o] = floor(CONV_REQUANT_MULTIPLIER[o] * 2^40 + 0.5).
// q40 must fit uint32_t (multiplier < 1/256). No float operations in hardware.
// Integer-product rounding uses nearest, ties to even, BEFORE adding output ZP.
// Taking an unsigned magnitude avoids right-shifting negative signed integers.
inline int8_t conv1x1_requantize(int32_t accumulator, uint32_t q40) {
#pragma HLS INLINE
    const int64_t product = static_cast<int64_t>(accumulator) *
                            static_cast<int64_t>(q40);
    const bool negative = product < 0;
    const uint64_t magnitude = negative
        ? static_cast<uint64_t>(-(product + 1)) + UINT64_C(1)
        : static_cast<uint64_t>(product);
    const uint64_t mask = (UINT64_C(1) << CONV_REQUANT_SHIFT) - UINT64_C(1);
    const uint64_t half = UINT64_C(1) << (CONV_REQUANT_SHIFT - 1);
    uint64_t whole = magnitude >> CONV_REQUANT_SHIFT;
    const uint64_t fraction = magnitude & mask;
    if (fraction > half || (fraction == half && (whole & UINT64_C(1)))) {
        ++whole;
    }
    const int64_t rounded = negative ? -static_cast<int64_t>(whole)
                                     : static_cast<int64_t>(whole);
    const int64_t quantized = rounded + CONV_OUTPUT_ZERO_POINT;
    if (quantized > 127) return static_cast<int8_t>(127);
    if (quantized < -128) return static_cast<int8_t>(-128);
    return static_cast<int8_t>(quantized);
}

// HLS top: select Vivado IP flow, top function = conv1x1.
// X/Y/accumulator: [1,C,T], index c*CONV_T+t (T contiguous).
// W: [Cout,Cin,1], index o*CONV_CIN+c. Bias/q40: [Cout].
// All pointers are non-overlapping DDR buffers. Bias is already INT32 QDQ bias.
// Caller must ensure each accumulation fits INT32; the test bench checks this.
// accumulator_out is a debug/verification output and adds DDR traffic.
// No ReLU, residual addition, or next-layer BatchNorm is applied here.
extern "C" void conv1x1(
    const int8_t input[CONV_INPUT_ELEMENTS],
    const int8_t weights[CONV_WEIGHT_ELEMENTS],
    const int32_t bias[CONV_COUT],
    const uint32_t requant_q40[CONV_COUT],
    int8_t output[CONV_OUTPUT_ELEMENTS],
    int32_t accumulator_out[CONV_OUTPUT_ELEMENTS]);

#endif
