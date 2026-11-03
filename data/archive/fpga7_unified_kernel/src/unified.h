#ifndef SONICARM_UNIFIED_V7_H
#define SONICARM_UNIFIED_V7_H

#include "packed.h"

#define V7_MODE_POINTWISE 0
#define V7_MODE_FCM 1

int unified_v7(const uint64_t* input,const uint64_t* weights,const int32_t* bias,
    const uint32_t* multiplier,const int8_t* post_lut,const uint64_t* residual,
    uint64_t* output,int32_t* accumulator_out,int mode,int cin,int cout,int freq,
    int frames,int kernel,int stride_f,int input_zp,int output_zp,int requant_shift,
    int flags);

#endif
