#include "packed.h"
#include <cassert>
#include <cstring>
#include <iostream>

int main() {
    for(int count=0;count<=8;++count) {
        const uint64_t expected=count==8 ? UINT64_MAX : ((UINT64_C(1)<<(count*8))-1);
        assert(byte_mask(count)==expected);
    }
    int cases=0;
    const uint64_t patterns[]={0,UINT64_MAX,UINT64_C(0x01807ffeaa5500ff),UINT64_C(0xfedcba9876543210)};
    for(int base=0;base<32;++base) for(int valid=0;valid<=8;++valid) for(uint64_t value:patterns) {
        uint64_t words[8];
        unsigned char expected[sizeof(words)];
        auto* bytes=reinterpret_cast<unsigned char*>(words);
        for(unsigned i=0;i<sizeof(words);++i) bytes[i]=static_cast<unsigned char>(i*17+3);
        std::memcpy(expected,words,sizeof(words));
        for(int lane=0;lane<valid;++lane) expected[base+lane]=static_cast<unsigned char>(value>>(8*lane));
        write_fragment(words,base,valid,value);
        assert(std::memcmp(words,expected,sizeof(words))==0);
        const uint64_t result=read_fragment(words,base,valid);
        for(int lane=0;lane<valid;++lane) assert(((result>>(8*lane))&255)==expected[base+lane]);
        ++cases;
    }
    std::cout<<"V7_PACKED_BYTE_MASK_PASS "<<cases<<" fragment/guard cases\n";
}
