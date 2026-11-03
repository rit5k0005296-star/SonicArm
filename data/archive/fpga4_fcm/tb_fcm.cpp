#include "fcm.h"
#include <algorithm>
#include <climits>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

struct Config { int ci,co,f,t,k,s,xz,yz,shift,flags; };
template<class T> std::vector<T> read_bin(const std::string& path,size_t n) {
    std::ifstream f(path.c_str(),std::ios::binary|std::ios::ate);
    if(!f || f.tellg()!=static_cast<std::streamoff>(n*sizeof(T))) throw std::runtime_error("Binary size: "+path);
    std::vector<T> out(n); f.seekg(0); f.read(reinterpret_cast<char*>(out.data()),n*sizeof(T));
    if(!f) throw std::runtime_error("Binary read: "+path); return out;
}

int8_t round_reference(int32_t a,uint32_t m,int s,int z) {
    const int64_t p=static_cast<int64_t>(a)*m, unit=INT64_C(1)<<s;
    int64_t q=p/unit, r=p%unit; const int64_t ar=r<0 ? -r:r;
    if(ar>unit/2 || (ar==unit/2 && q%2!=0)) q+=p<0 ? -1:1;
    return static_cast<int8_t>(std::max<int64_t>(-128,std::min<int64_t>(127,q+z)));
}

void oracle(const Config& c,const std::vector<int8_t>& x,const std::vector<int8_t>& w,
            const std::vector<int32_t>& b,const std::vector<uint32_t>& m,
            const std::vector<int8_t>& lut,const std::vector<int8_t>& skip,
            std::vector<int32_t>& acc,std::vector<int8_t>& y) {
    const int of=(c.f+c.s-1)/c.s, pad=c.k/2;
    acc.resize(c.co*of*c.t); y.resize(acc.size());
    for(int o=0;o<c.co;++o) for(int f=0;f<of;++f) for(int t=0;t<c.t;++t) {
        int64_t a=b[o];
        for(int i=0;i<c.ci;++i) for(int kf=0;kf<c.k;++kf) for(int kt=0;kt<c.k;++kt) {
            const int fi=f*c.s+kf-pad, ti=t+kt-pad;
            const int xv=fi<0 || fi>=c.f || ti<0 || ti>=c.t ? c.xz:x[(i*c.f+fi)*c.t+ti];
            a+=static_cast<int64_t>(xv-c.xz)*w[((o*c.ci+i)*c.k+kf)*c.k+kt];
            if(a<INT32_MIN || a>INT32_MAX) throw std::runtime_error("INT32 partial overflow");
        }
        const int index=(o*of+f)*c.t+t; acc[index]=static_cast<int32_t>(a);
        const int8_t q=round_reference(acc[index],m[o],c.shift,c.yz);
        int li=static_cast<int>(q)+128;
        if(c.flags&FCM_FLAG_RESIDUAL) li=li*256+static_cast<int>(skip[index])+128;
        y[index]=(c.flags&FCM_FLAG_LUT) ? lut[li]:q;
    }
}

void check(Config c,std::vector<int8_t> x,std::vector<int8_t> w,std::vector<int32_t> b,
           std::vector<uint32_t> m,std::vector<int8_t> lut,std::vector<int8_t> skip,
           const std::vector<int32_t>* file_acc=0,const std::vector<int8_t>* file_y=0) {
    std::vector<int32_t> ref; std::vector<int8_t> expected;
    oracle(c,x,w,b,m,lut,skip,ref,expected);
    if(file_acc && (ref!=*file_acc || expected!=*file_y)) throw std::runtime_error("Python/C++ reference mismatch");
    const size_t count=expected.size(), size=std::max<size_t>(count,16384);
    x.resize(std::max<size_t>(x.size(),16384),0); w.resize(9216,0); b.resize(32,0); m.resize(32,0);
    lut.resize(65536,0); skip.resize(std::max<size_t>(skip.size(),16384),0);
    std::vector<int8_t> actual(size+16,85); std::vector<int32_t> debug(size+16,0x5a5a5a5a);
    int rc=fcm(x.data(),w.data(),b.data(),m.data(),lut.data(),skip.data(),actual.data(),debug.data(),
               c.ci,c.co,c.f,c.t,c.k,c.s,c.xz,c.yz,c.shift,c.flags);
    if(rc!=0) throw std::runtime_error("Kernel status");
    for(size_t i=0;i<count;++i) {
        if(actual[i]!=expected[i] || ((c.flags&2) && debug[i]!=ref[i]))
            throw std::runtime_error("Kernel mismatch at "+std::to_string(i));
        if(!(c.flags&2) && debug[i]!=0x5a5a5a5a) throw std::runtime_error("Debug disabled write");
    }
    for(size_t i=count;i<actual.size();++i) if(actual[i]!=85 || debug[i]!=0x5a5a5a5a)
        throw std::runtime_error("Output guard overwritten");
}

void real_case(const std::string& dir,bool rtl) {
    Config c; std::ifstream f((dir+"/config.txt").c_str());
    if(!(f>>c.ci>>c.co>>c.f>>c.t>>c.k>>c.s>>c.xz>>c.yz>>c.shift>>c.flags)) throw std::runtime_error("Config read");
    const int of=(c.f+c.s-1)/c.s;
    auto x=read_bin<int8_t>(dir+"/input_int8.bin",c.ci*c.f*c.t);
    auto w=read_bin<int8_t>(dir+"/weights_int8.bin",c.co*c.ci*c.k*c.k);
    auto b=read_bin<int32_t>(dir+"/bias_int32.bin",c.co);
    auto m=read_bin<uint32_t>(dir+"/multiplier_uint32.bin",c.co);
    auto lut=read_bin<int8_t>(dir+"/post_lut_int8.bin",(c.flags&4) ? 65536:256);
    auto skip=read_bin<int8_t>(dir+"/residual_int8.bin",c.co*of*c.t);
    if(rtl) {
        // Recompute boundaries for the SHORT invocation, including its right pad;
        // copying a reference prefix would be wrong for temporal K=3.
        const int nt=5; std::vector<int8_t> sx(c.ci*c.f*nt),ss(c.co*of*nt);
        for(int i=0;i<c.ci*c.f;++i) for(int t=0;t<nt;++t) sx[i*nt+t]=x[i*c.t+t];
        for(int i=0;i<c.co*of;++i) for(int t=0;t<nt;++t) ss[i*nt+t]=skip[i*c.t+t];
        x.swap(sx); skip.swap(ss); c.t=nt; check(c,x,w,b,m,lut,skip);
    } else {
        auto a=read_bin<int32_t>(dir+"/reference_accum_int32.bin",c.co*of*c.t);
        auto y=read_bin<int8_t>(dir+"/reference_output_int8.bin",c.co*of*c.t);
        check(c,x,w,b,m,lut,skip,&a,&y);
    }
    std::cout << "[PASS REAL] " << dir << " T=" << c.t << " Cin=" << c.ci << " Cout=" << c.co << " F=" << c.f << std::endl;
}

void synthetic(Config c) {
    const int of=(c.f+c.s-1)/c.s;
    std::vector<int8_t> x(c.ci*c.f*c.t),w(c.co*c.ci*c.k*c.k),lut(65536),skip(c.co*of*c.t);
    std::vector<int32_t> b(c.co); std::vector<uint32_t> m(c.co);
    for(size_t i=0;i<x.size();++i) x[i]=static_cast<int8_t>((i*73+17)%256-128);
    for(size_t i=0;i<w.size();++i) w[i]=static_cast<int8_t>((i*31+9)%256-128);
    for(size_t i=0;i<skip.size();++i) skip[i]=static_cast<int8_t>((i*11+19)%256-128);
    for(int i=0;i<c.co;++i) { b[i]=(i-15)*7919; m[i]=UINT32_C(1073741824)+i; }
    for(int i=0;i<65536;++i) lut[i]=static_cast<int8_t>((i*17+i/256)%256-128);
    check(c,x,w,b,m,lut,skip);
    std::cout << "[PASS SYNTH] " << c.ci << "->" << c.co << " F=" << c.f << " T=" << c.t << " K=" << c.k << " S=" << c.s << " flags=" << c.flags << std::endl;
}

int main(int argc,char** argv) {
    try {
        if(argc<2) throw std::runtime_error("Usage: tb_fcm CASE_ROOT [--rtl]");
        const bool rtl=argc>2 && std::string(argv[2])=="--rtl";
        if(!rtl) {
            const int32_t aa[]={INT32_MIN,INT32_MAX,-769,-768,-257,-256,-255,0,255,256,257,768,769};
            for(int s:{8,32,38,39,40}) for(int32_t a:aa) for(uint32_t m:{0u,1u,UINT32_C(2147483648),UINT32_MAX})
                for(int z:{-128,-1,0,127}) if(fcm_requantize(a,m,s,z)!=round_reference(a,m,s,z)) throw std::runtime_error("Round ties/extremes");
        }
        std::string root=argv[1],name; std::ifstream list((root+(rtl ? "/rtl_cases.txt":"/all_cases.txt")).c_str());
        if(!list) throw std::runtime_error("Case list"); int count=0;
        while(std::getline(list,name)) { if(!name.empty() && name.back()=='\r') name.pop_back(); if(!name.empty()) { real_case(root+"/"+name,rtl); ++count; } }
        synthetic({3,9,7,35,3,2,11,-7,38,7}); // frequency/time/channel tails + residual
        synthetic({1,1,1,2048,1,1,-128,127,40,0}); // maximum T, disabled LUT/debug
        synthetic({1,32,80,3,3,1,127,-128,39,3}); // maximum F/Cout, extreme ZP
        if(!rtl) {
            synthetic({32,32,3,33,3,1,-128,0,38,2}); // max Cin/Cout/kernel; identity
            synthetic({2,7,5,1,1,2,0,0,32,1}); // T=1 K=1 stride2 no debug
            synthetic({1,1,1,1,3,2,11,1,40,3}); // spatial padding on all sides
            int8_t x=0,w=0,l=0,r=0,y=85; int32_t b=0,a=123; uint32_t m=1;
            if(fcm(&x,&w,&b,&m,&l,&r,&y,&a,0,1,1,1,3,1,0,0,40,2)!=-1 || y!=85 || a!=123) throw std::runtime_error("Invalid config wrote DDR");
            if(fcm(&x,&w,&b,&m,&l,&r,&y,&a,1,1,1,1,3,1,0,0,40,4)!=-1 || y!=85 || a!=123) throw std::runtime_error("Invalid flags");
        }
        if(count!=(rtl ? 5:48)) throw std::runtime_error("Unexpected real case count");
        std::cout << "FCM_TEST_PASS real_cases=" << count << " mode=" << (rtl ? "RTL_SMOKE":"FULL_C") << std::endl;
        return 0;
    } catch(const std::exception& e) { std::cerr << "FCM_TEST_FAIL " << e.what() << std::endl; return 1; }
}
