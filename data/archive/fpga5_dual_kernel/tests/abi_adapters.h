#ifndef SONICARM_V5_TEST_ADAPTERS_H
#define SONICARM_V5_TEST_ADAPTERS_H
#include "pointwise.h"
#include "fcm.h"
inline int pointwise(const int8_t* x,const int8_t* w,const int32_t* b,const uint32_t* m,
    const int8_t* l,int8_t* y,int32_t* a,int ci,int co,int t,int xz,int yz,int s,int fl) {
    return pointwise_v5(reinterpret_cast<const uint64_t*>(x),reinterpret_cast<const uint64_t*>(w),b,m,l,
        reinterpret_cast<uint64_t*>(y),a,ci,co,t,xz,yz,s,fl);
}
inline int fcm(const int8_t* x,const int8_t* w,const int32_t* b,const uint32_t* m,
    const int8_t* l,const int8_t* r,int8_t* y,int32_t* a,int ci,int co,int f,int t,int k,int s,int xz,int yz,int q,int fl) {
    return fcm_v5(reinterpret_cast<const uint64_t*>(x),reinterpret_cast<const uint64_t*>(w),b,m,l,
        reinterpret_cast<const uint64_t*>(r),reinterpret_cast<uint64_t*>(y),a,ci,co,f,t,k,s,xz,yz,q,fl);
}
#endif
