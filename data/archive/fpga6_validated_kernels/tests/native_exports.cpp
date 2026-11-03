#include "abi_adapters.h"
#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif
extern "C" EXPORT int call_pw6(const int8_t* x,const int8_t* w,const int32_t* b,const uint32_t* m,
    const int8_t* l,int8_t* y,int32_t* a,int ci,int co,int t,int xz,int yz,int s,int fl) {
    return pointwise(x,w,b,m,l,y,a,ci,co,t,xz,yz,s,fl);
}
extern "C" EXPORT int call_fcm6(const int8_t* x,const int8_t* w,const int32_t* b,const uint32_t* m,
    const int8_t* l,const int8_t* r,int8_t* y,int32_t* a,int ci,int co,int f,int t,int k,int s,int xz,int yz,int q,int fl) {
    return fcm(x,w,b,m,l,r,y,a,ci,co,f,t,k,s,xz,yz,q,fl);
}
