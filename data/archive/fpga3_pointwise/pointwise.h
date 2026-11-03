#ifndef SONICARM_POINTWISE_V3_H
#define SONICARM_POINTWISE_V3_H
#include <stdint.h>
#define PW_MAX_CIN 1024
#define PW_MAX_COUT 512
#define PW_MAX_FRAMES 2048
#define PW_TIME_TILE 64
#define PW_FRAME_LANES 4
#define PW_OUTPUT_LANES 8
#define PW_FLAG_POST_LUT 1
#define PW_FLAG_DEBUG 2

inline int8_t pw_requantize(int32_t acc, uint32_t multiplier, int shift, int output_zp) {
#pragma HLS INLINE
    const int64_t product=static_cast<int64_t>(acc)*static_cast<int64_t>(multiplier);
    const bool negative=product<0;
    const uint64_t mag=negative ? static_cast<uint64_t>(-(product+1))+UINT64_C(1) : static_cast<uint64_t>(product);
    uint64_t whole=mag>>shift;
    const uint64_t fraction=mag&((UINT64_C(1)<<shift)-1);
    const uint64_t half=UINT64_C(1)<<(shift-1);
    if (fraction>half || (fraction==half && (whole&1))) ++whole;
    const int64_t q=(negative ? -static_cast<int64_t>(whole) : static_cast<int64_t>(whole))+output_zp;
    return static_cast<int8_t>(q>127 ? 127 : q < -128 ? -128 : q);
}

// Runtime-configured, ungrouped, stride-1 kernel-1 Conv1D; symmetric W ZP=0.
// Layout X/Y: [C,T] with T contiguous; W: [Cout,Cin]. No packing conversion.
// multiplier[o] / 2^requant_shift approximates xs*ws[o]/ys.
// flags bit0: apply post_lut after ORIGINAL Q1 saturation; bit1: store INT32.
// Return 0 on success, -1 on invalid config without touching DDR.
// Host must prove every INT32 partial sum fits; buffers must not overlap.
// Debug-disabled mode leaves accumulator_out unchanged; it must still be a valid
// pointer when using the test driver. Weights are reloaded for each time tile.
extern "C" int pointwise(const int8_t* input, const int8_t* weights, const int32_t* bias,
                         const uint32_t* multiplier, const int8_t* post_lut,
                         int8_t* output, int32_t* accumulator_out,
                         int cin, int cout, int frames, int input_zp, int output_zp,
                         int requant_shift, int flags);
#endif
