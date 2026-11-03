#ifndef SONICARM_FCM_V6_H
#define SONICARM_FCM_V6_H
#include "packed.h"
#define FCM_MAX_C 32
#define FCM_MAX_F 80
#define FCM_MAX_T 2048
#define FCM_F_TILE 4
#define FCM_T_TILE 32
#define FCM_O_LANES 8
#define FCM_T_LANES 8
#define FCM_FLAG_LUT 1
#define FCM_FLAG_DEBUG 2
#define FCM_FLAG_RESIDUAL 4
inline int8_t fcm_requantize(int32_t a,uint32_t m,int s,int z) { return v6_requantize(a,m,s,z); }
int fcm_v6(const uint64_t* input,const uint64_t* weights,const int32_t* bias,
    const uint32_t* multiplier,const int8_t* post_lut,const uint64_t* residual,
    uint64_t* output,int32_t* accumulator_out,int cin,int cout,int freq,int frames,
    int kernel,int stride_f,int input_zp,int output_zp,int requant_shift,int flags);
#endif
