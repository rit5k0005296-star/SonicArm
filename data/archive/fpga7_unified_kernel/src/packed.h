#ifndef SONICARM_V7_PACKED_H
#define SONICARM_V7_PACKED_H
#include <stdint.h>
#ifdef V7_PORTABLE
#include <deque>
namespace hls { template<class T> class stream {
    std::deque<T> q;
public:
    stream() {} explicit stream(const char*) {}
    void write(const T& v) { q.push_back(v); }
    T read() { T v=q.front(); q.pop_front(); return v; }
}; }
#else
#include <hls_stream.h>
#endif

struct AccWord { int32_t a[8]; int index; int valid; int channel; };

// Logical tensors stay dense byte arrays. DMA bases must be 8-byte aligned,
// allocated through round_up(logical_bytes,8); only valid lanes are consumed.
inline uint64_t read_fragment(const uint64_t* p,int base,int valid) {
#pragma HLS INLINE
    const int word=base>>3, offset=base&7;
    const uint64_t lo=p[word];
    uint64_t value=lo>>(offset*8);
    if(offset && offset+valid>8) value|=p[word+1]<<((8-offset)*8);
    return value;
}
inline int signed_byte(uint64_t v,int lane) {
#pragma HLS INLINE
    return static_cast<int8_t>((v>>(lane*8))&255);
}
inline uint64_t byte_mask(int count) {
#pragma HLS INLINE
    // Decode byte enables directly: a variable 64-bit shift followed by -1
    // otherwise infers a long carry chain on the packed-output store path.
    uint64_t mask=0;
    for(int lane=0;lane<8;++lane) {
#pragma HLS UNROLL
        if(lane<count) mask|=UINT64_C(255)<<(lane*8);
    }
    return mask;
}
inline void write_fragment(uint64_t* p,int base,int valid,uint64_t value) {
#pragma HLS INLINE
    const int wi=base>>3, offset=base&7;
    const int first=valid<(8-offset) ? valid:8-offset;
    const uint64_t lowmask=byte_mask(first);
    const uint64_t mask=lowmask<<(offset*8);
    const uint64_t before=mask==UINT64_MAX ? 0:p[wi];
    p[wi]=(before&~mask)|((value&lowmask)<<(offset*8));
    if(first<valid) {
        const int remaining=valid-first;
        const uint64_t tailmask=byte_mask(remaining);
        const uint64_t tail=p[wi+1];
        p[wi+1]=(tail&~tailmask)|((value>>(first*8))&tailmask);
    }
}
inline int8_t v7_requantize(int32_t acc,uint32_t multiplier,int shift,int zp) {
#pragma HLS INLINE
    const int64_t product=static_cast<int64_t>(acc)*static_cast<int64_t>(multiplier);
    const bool neg=product<0;
    const uint64_t mag=neg ? static_cast<uint64_t>(-(product+1))+1:static_cast<uint64_t>(product);
    uint64_t whole=mag>>shift;
    const uint64_t fraction=mag&((UINT64_C(1)<<shift)-1),half=UINT64_C(1)<<(shift-1);
    if(fraction>half || (fraction==half && (whole&1))) ++whole;
    const int64_t q=(neg ? -static_cast<int64_t>(whole):static_cast<int64_t>(whole))+zp;
    return static_cast<int8_t>(q>127 ? 127:q < -128 ? -128:q);
}
#endif
