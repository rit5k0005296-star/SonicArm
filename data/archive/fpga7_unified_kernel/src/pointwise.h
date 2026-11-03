#ifndef SONICARM_POINTWISE_V7_H
#define SONICARM_POINTWISE_V7_H
#include "packed.h"
#define PW_MAX_CIN 1024
#define PW_MAX_COUT 512
#define PW_MAX_FRAMES 2048
#define PW_TIME_TILE 64
#define PW_FRAME_LANES 8
#define PW_OUTPUT_LANES 8
#define PW_WEIGHT_CHANNELS 128
#define PW_FLAG_POST_LUT 1
#define PW_FLAG_DEBUG 2
inline int8_t pw_requantize(int32_t a,uint32_t m,int s,int z) { return v7_requantize(a,m,s,z); }
int pointwise_v7(const uint64_t* input,const uint64_t* weights,const int32_t* bias,
    const uint32_t* multiplier,const int8_t* post_lut,uint64_t* output,int32_t* accumulator_out,
    int cin,int cout,int frames,int input_zp,int output_zp,int requant_shift,int flags);
// Native/CSim compatibility adapter. Board callers retain dense [C,T] layout.
#endif
