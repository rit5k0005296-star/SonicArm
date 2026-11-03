#ifndef SONICARM_FCM_V4_H
#define SONICARM_FCM_V4_H
#include <stdint.h>
#define FCM_MAX_C 32
#define FCM_MAX_F 80
#define FCM_MAX_T 2048
#define FCM_F_TILE 4
#define FCM_T_TILE 32
#define FCM_O_LANES 8
#define FCM_T_LANES 4
#define FCM_FLAG_LUT 1
#define FCM_FLAG_DEBUG 2
#define FCM_FLAG_RESIDUAL 4

inline int8_t fcm_requantize(int32_t acc, uint32_t multiplier, int shift, int zp) {
#pragma HLS INLINE
    const int64_t product=static_cast<int64_t>(acc)*static_cast<int64_t>(multiplier);
    const bool negative=product<0;
    const uint64_t mag=negative ? static_cast<uint64_t>(-(product+1))+UINT64_C(1) : static_cast<uint64_t>(product);
    uint64_t whole=mag>>shift;
    const uint64_t fraction=mag&((UINT64_C(1)<<shift)-1), half=UINT64_C(1)<<(shift-1);
    if (fraction>half || (fraction==half && (whole&1))) ++whole;
    const int64_t q=(negative ? -static_cast<int64_t>(whole) : static_cast<int64_t>(whole))+zp;
    return static_cast<int8_t>(q>127 ? 127 : q < -128 ? -128 : q);
}

// X/Y NCHW, batch=1, contiguous time. W [Cout,Cin,K,K], symmetric ZP=0.
// K=1 or 3, frequency stride=1 or 2, time stride=1, same symmetric padding K/2.
// LUT is applied AFTER original Conv Q1 rounding/saturation. Unary index q+128;
// residual index (q+128)*256+(skip+128), encoding exact original DQ/Add/ReLU/Q.
// Residual has output shape/layout; no broadcasting. Residual flag requires LUT.
// Caller proves INT32 partial sums fit and nonoverlapping correctly sized buffers.
// flags=0..7; debug disabled leaves accumulator_out untouched. Invalid config
// returns -1 before DDR access. T is invocation-local: host must provide halos
// for long-record temporal chunks, never cut K=3 without neighbouring samples.
extern "C" int fcm(const int8_t* input, const int8_t* weights, const int32_t* bias,
                   const uint32_t* multiplier, const int8_t* post_lut,
                   const int8_t* residual, int8_t* output, int32_t* accumulator_out,
                   int cin, int cout, int freq, int frames, int kernel, int stride_f,
                   int input_zp, int output_zp, int requant_shift, int flags);
#endif
