#ifndef SONICARM_CONV_RELU_H
#define SONICARM_CONV_RELU_H
#include <stdint.h>
#include "layer_params.h"

#define CR_INPUT_ELEMENTS (CONV_CIN * CONV_T)
#define CR_WEIGHT_ELEMENTS (CONV_COUT * CONV_CIN)
#define CR_OUTPUT_ELEMENTS (CONV_COUT * CONV_T)
#define CR_FRAME_LANES 4
#define CR_OUTPUT_LANES 4
#define CR_REQUANT_SHIFT 40
static_assert(CONV_BATCH == 1 && CONV_CIN == 128 && CONV_COUT == 128 && CONV_T == 150,
              "V2-A is a fixed-shape accelerator, not the reusable multi-layer engine");
static_assert(CONV_COUT % CR_OUTPUT_LANES == 0, "Output tile must divide Cout");

// Preserve Q1 saturation BEFORE applying the DQ1 -> ReLU -> Q2 lookup table.
inline int8_t conv_relu_requantize(int32_t accumulator, uint32_t q40) {
#pragma HLS INLINE
    const int64_t product = static_cast<int64_t>(accumulator) * static_cast<int64_t>(q40);
    const bool negative = product < 0;
    const uint64_t magnitude = negative ? static_cast<uint64_t>(-(product + 1)) + UINT64_C(1)
                                        : static_cast<uint64_t>(product);
    uint64_t whole = magnitude >> CR_REQUANT_SHIFT;
    const uint64_t fraction = magnitude & ((UINT64_C(1) << CR_REQUANT_SHIFT) - 1);
    const uint64_t half = UINT64_C(1) << (CR_REQUANT_SHIFT - 1);
    if (fraction > half || (fraction == half && (whole & 1))) ++whole;
    const int64_t rounded = negative ? -static_cast<int64_t>(whole) : static_cast<int64_t>(whole);
    const int64_t quantized = rounded + CONV_OUTPUT_ZERO_POINT;
    if (quantized > 127) return static_cast<int8_t>(127);
    if (quantized < -128) return static_cast<int8_t>(-128);
    return static_cast<int8_t>(quantized);
}

// X/Y are channel-major [1,C,T]; W is [Cout,Cin,1]. Weights have ZP=0.
// post_lut[q1+128] maps all 256 signed INT8 Q1 values to Q2 exactly.
// Parameters remain resident in host DDR; this IP reloads them on each call.
// All buffers must be non-overlapping. accumulator_out remains enabled for validation.
extern "C" void conv_relu(const int8_t input[CR_INPUT_ELEMENTS],
                          const int8_t weights[CR_WEIGHT_ELEMENTS],
                          const int32_t bias[CONV_COUT],
                          const uint32_t requant_q40[CONV_COUT],
                          const int8_t post_lut[256],
                          int8_t output[CR_OUTPUT_ELEMENTS],
                          int32_t accumulator_out[CR_OUTPUT_ELEMENTS]);
#endif
