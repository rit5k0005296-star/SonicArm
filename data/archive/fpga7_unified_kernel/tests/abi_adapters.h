#ifndef SONICARM_V7_TEST_ADAPTERS_H
#define SONICARM_V7_TEST_ADAPTERS_H
#include "pointwise.h"
#include "fcm.h"
#ifdef V7_UNIFIED_TEST
#include "unified.h"
#endif
inline int pointwise(const int8_t* x,const int8_t* w,const int32_t* b,const uint32_t* m,
    const int8_t* l,int8_t* y,int32_t* a,int ci,int co,int t,int xz,int yz,int s,int fl,
    const int8_t* residual_dummy=0) {
#ifdef V7_UNIFIED_TEST
    // Keep every AXI master argument backed by a distinct host allocation.
    // The residual port is unused in pointwise mode, but Vitis co-simulation
    // still marshals its declared depth.
    return unified_v7(reinterpret_cast<const uint64_t*>(x),reinterpret_cast<const uint64_t*>(w),b,m,l,
        reinterpret_cast<const uint64_t*>(residual_dummy),reinterpret_cast<uint64_t*>(y),a,
        V7_MODE_POINTWISE,ci,co,1,t,1,1,xz,yz,s,fl);
#else
    return pointwise_v7(reinterpret_cast<const uint64_t*>(x),reinterpret_cast<const uint64_t*>(w),b,m,l,
        reinterpret_cast<uint64_t*>(y),a,ci,co,t,xz,yz,s,fl);
#endif
}
inline int fcm(const int8_t* x,const int8_t* w,const int32_t* b,const uint32_t* m,
    const int8_t* l,const int8_t* r,int8_t* y,int32_t* a,int ci,int co,int f,int t,int k,int s,int xz,int yz,int q,int fl) {
#ifdef V7_UNIFIED_TEST
    return unified_v7(reinterpret_cast<const uint64_t*>(x),reinterpret_cast<const uint64_t*>(w),b,m,l,
        reinterpret_cast<const uint64_t*>(r),reinterpret_cast<uint64_t*>(y),a,V7_MODE_FCM,
        ci,co,f,t,k,s,xz,yz,q,fl);
#else
    return fcm_v7(reinterpret_cast<const uint64_t*>(x),reinterpret_cast<const uint64_t*>(w),b,m,l,
        reinterpret_cast<const uint64_t*>(r),reinterpret_cast<uint64_t*>(y),a,ci,co,f,t,k,s,xz,yz,q,fl);
#endif
}
#endif
