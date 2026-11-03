#include "pointwise.h"
#include "abi_adapters.h"
#include <algorithm>
#include <climits>
#include <cmath>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

template<class T> std::vector<T> read_bin(const std::string& dir,const char* name,size_t n) {
    std::ifstream f((dir+"/"+name).c_str(),std::ios::binary|std::ios::ate);
    if (!f || f.tellg()!=static_cast<std::streamoff>(n*sizeof(T))) throw std::runtime_error("Missing/wrong binary "+dir+"/"+name);
    std::vector<T> a(n);f.seekg(0);f.read(reinterpret_cast<char*>(a.data()),n*sizeof(T));
    if (!f) throw std::runtime_error("Short binary read");return a;
}

int8_t golden(int32_t acc,uint32_t m,int shift,int zp) {
    const int64_t p=static_cast<int64_t>(acc)*m,unit=INT64_C(1)<<shift;
    int64_t q=p/unit;const int64_t rem=p%unit,mag=rem<0 ? -rem : rem;
    if (mag>unit/2 || (mag==unit/2 && q%2!=0)) q+=p<0 ? -1 : 1;
    return static_cast<int8_t>(std::max<int64_t>(-128,std::min<int64_t>(127,q+zp)));
}

void rounding_tests() {
    const int shifts[]={8,32,38,39,40};
    const int32_t accs[]={INT32_MIN,INT32_MAX,0,255,256,257,768,-255,-256,-257,-768};
    const uint32_t mults[]={0,1,UINT32_C(1)<<31,UINT32_MAX};
    for (int s:shifts) for (int32_t a:accs) for (uint32_t m:mults)
        for (int z: {-128,-15,0,127}) if (pw_requantize(a,m,s,z)!=golden(a,m,s,z)) throw std::runtime_error("Rounding boundary");
    std::cout << "[PASS] Variable shift, signed ties, zero points and saturation\n";
}

void check_call(std::vector<int8_t> x,std::vector<int8_t> w,std::vector<int32_t> b,
                std::vector<uint32_t> m,std::vector<int8_t> lut,const std::vector<int32_t>& ref,
                const std::vector<int8_t>& expected,int cin,int cout,int frames,int xz,int yz,int shift,int flags) {
    // The m_axi depth annotations bound RTL smoke-test transactions, not the
    // synthesised address range. Pad host buffers to those declared depths so
    // co-simulation instrumentation never reads beyond an allocation.
    x.resize(std::max<size_t>(x.size(),131072),0);w.resize(524288,0);b.resize(512,0);m.resize(512,0);
    // unified_v7 shares FCM's 64-KiB post-LUT AXI contract.  Pointwise only
    // consumes the first 256 entries, but the co-simulation wrapper copies the
    // declared interface depth on every call.
    lut.resize(65536,0);
    const size_t count=cout*frames;
    std::vector<int8_t> residual_dummy(131072,0);
    std::vector<int8_t> actual(std::max<size_t>(count,131072)+16,85);
    std::vector<int32_t> debug(std::max<size_t>(count,131072)+16,0x5a5a5a5a);
    if (pointwise(x.data(),w.data(),b.data(),m.data(),lut.data(),actual.data(),debug.data(),
                  cin,cout,frames,xz,yz,shift,flags,residual_dummy.data())!=0) throw std::runtime_error("Top status");
    for (size_t k=0;k<count;++k) {
        if (actual[k]!=expected[k] || ((flags&PW_FLAG_DEBUG) && debug[k]!=ref[k]))
            throw std::runtime_error("Kernel differs from integer golden at index "+std::to_string(k));
        if (!(flags&PW_FLAG_DEBUG) && debug[k]!=0x5a5a5a5a) throw std::runtime_error("Debug-disabled write");
    }
    for (size_t k=count;k<actual.size();++k)
        if (actual[k]!=85 || debug[k]!=0x5a5a5a5a) throw std::runtime_error("Out-of-range output store");
}

void run_case(const std::string& dir,int short_frames=0,int short_cout=0) {
    int cin,cout,frames,xz,yz,shift,flags;
    std::ifstream cfg((dir+"/config.txt").c_str());
    if (!(cfg>>cin>>cout>>frames>>xz>>yz>>shift>>flags)) throw std::runtime_error("Config read");
    auto x=read_bin<int8_t>(dir,"input_int8.bin",cin*frames);
    auto w=read_bin<int8_t>(dir,"weights_int8.bin",cin*cout);
    auto b=read_bin<int32_t>(dir,"bias_int32.bin",cout);
    auto mult=read_bin<uint32_t>(dir,"multiplier_uint32.bin",cout);
    auto lut=read_bin<int8_t>(dir,"post_lut_int8.bin",256);
    auto ref=read_bin<int32_t>(dir,"reference_accum_int32.bin",cout*frames);
    auto expected=read_bin<int8_t>(dir,"reference_output_int8.bin",cout*frames);
    auto onnx=read_bin<int8_t>(dir,"onnx_output_int8.bin",cout*frames);
    size_t onnx_errors=0;
    for (int o=0;o<cout;++o) {
        int64_t bound=std::abs(static_cast<int64_t>(b[o]));
        for (int c=0;c<cin;++c) bound+=std::abs(static_cast<int64_t>(w[o*cin+c]))*std::max(std::abs(-128-xz),std::abs(127-xz));
        if (bound>INT32_MAX) throw std::runtime_error("Partial sum bound");
        for (int t=0;t<frames;++t) {
            const int k=o*frames+t;
            if (golden(ref[k],mult[o],shift,yz)!=expected[k]) throw std::runtime_error("Golden binary integrity");
            const int delta=std::abs(static_cast<int>(expected[k])-onnx[k]);
            if (delta>1) throw std::runtime_error("ONNX differs by >1 LSB");
            onnx_errors+=delta!=0;
        }
    }
    if (short_frames) {
        std::vector<int8_t> sx(cin*short_frames),sy(cout*short_frames);
        std::vector<int32_t> sa(cout*short_frames);
        for (int c=0;c<cin;++c) for (int t=0;t<short_frames;++t) sx[c*short_frames+t]=x[c*frames+t];
        for (int o=0;o<cout;++o) for (int t=0;t<short_frames;++t) {
            sy[o*short_frames+t]=expected[o*frames+t];sa[o*short_frames+t]=ref[o*frames+t];
        }
        x.swap(sx);expected.swap(sy);ref.swap(sa);frames=short_frames;
    }
    if (short_cout) {
        if (short_cout<1 || short_cout>cout) throw std::runtime_error("Invalid output-channel slice");
        cout=short_cout;w.resize(cin*cout);b.resize(cout);mult.resize(cout);
        ref.resize(cout*frames);expected.resize(cout*frames);
    }
    check_call(x,w,b,mult,lut,ref,expected,cin,cout,frames,xz,yz,shift,flags);
    std::cout << "[PASS] " << dir << " X=" << cin << 'x' << frames << " Cout=" << cout
              << " shift=" << shift << "; integer exact; full-case ONNX mismatches=" << onnx_errors << " (max 1 LSB)\n";
}

// Exercise runtime dimension limits separately so the AXI VIP does not retain
// a 1024*512-byte read workload. Full combined dimensions remain in --all CSim.
void dimension_limit_tests() {
    for (int mode=0;mode<2;++mode) {
        const int cin=1,cout=mode==0 ? PW_MAX_COUT : 1,frames=mode==0 ? 3 : PW_MAX_FRAMES;
        const int xz=5,yz=-3,shift=38;
        std::vector<int8_t> x(frames),w(cout),lut(256,0),expected(cout*frames);
        std::vector<int32_t> b(cout),ref(cout*frames);
        std::vector<uint32_t> mult(cout,UINT32_C(1)<<31);
        for(int t=0;t<frames;++t) x[t]=static_cast<int8_t>(t%3==0 ? -128 : t%3==1 ? 0 : 127);
        for(int o=0;o<cout;++o) {
            w[o]=static_cast<int8_t>(o%17-8);b[o]=o*31-8000;
            for(int t=0;t<frames;++t) {
                ref[o*frames+t]=b[o]+(static_cast<int>(x[t])-xz)*w[o];
                expected[o*frames+t]=golden(ref[o*frames+t],mult[o],shift,yz);
            }
        }
        check_call(x,w,b,mult,lut,ref,expected,cin,cout,frames,xz,yz,shift,2);
    }
    std::cout << "[PASS] Maximum Cout=512 and maximum frames=2048 tested separately\n";
}

void synthetic_tests() {
    const int cin=17,cout=9,frames=65,xz=13,yz=-7,shift=38;
    std::vector<int8_t> x(cin*frames),w(cin*cout),lut(256);
    std::vector<int32_t> b(cout),ref(cout*frames);
    std::vector<uint32_t> m(cout,UINT32_C(1)<<30);
    std::vector<int8_t> expected(cout*frames);
    for (int c=0;c<cin;++c) for (int t=0;t<frames;++t) x[c*frames+t]=static_cast<int8_t>((c+t)%2 ? 127 : -128);
    for (int k=0;k<256;++k) lut[k]=static_cast<int8_t>(std::max(-7,k-128));
    for (int o=0;o<cout;++o) {
        b[o]=o*17-1000;
        for (int c=0;c<cin;++c) w[o*cin+c]=static_cast<int8_t>((o+c)%2 ? -128 : 127);
        for (int t=0;t<frames;++t) {
            int64_t sum=b[o];
            for (int c=0;c<cin;++c) sum+=(static_cast<int64_t>(x[c*frames+t])-xz)*w[o*cin+c];
            ref[o*frames+t]=static_cast<int32_t>(sum);
            expected[o*frames+t]=lut[static_cast<int>(golden(ref[o*frames+t],m[o],shift,yz))+128];
        }
    }
    check_call(x,w,b,m,lut,ref,expected,cin,cout,frames,xz,yz,shift,3);
    check_call(x,w,b,m,lut,ref,expected,cin,cout,frames,xz,yz,shift,1);
    // Invalid configuration must not read/write buffers; use real padded storage.
    x.resize(131072);w.resize(524288);b.resize(512);m.resize(512);
    std::vector<int8_t> residual_dummy(131072,0);
    std::vector<int8_t> output(131072,85);std::vector<int32_t> acc(131072,0x5a5a5a5a);
    const int code=pointwise(x.data(),w.data(),b.data(),m.data(),lut.data(),output.data(),acc.data(),0,cout,frames,xz,yz,shift,2,residual_dummy.data());
    if (code!=-1 || std::any_of(output.begin(),output.end(),[](int8_t v){return v!=85;})) throw std::runtime_error("Invalid config guard");
    std::cout << "[PASS] Cin/Cout/time tails, nonzero input ZP, LUT, debug-off, repeated calls, invalid config\n";
}

int main(int argc,char** argv) {
    try {
        if (argc!=3) throw std::runtime_error("Usage: tb_pointwise CASE_ROOT --all|--representative|--rtl");
        rounding_tests();const std::string root=argv[1],mode=argv[2];
        const char* list=mode=="--all" ? "all_cases.txt" : mode=="--rtl" ? "rtl_cases.txt" : "representative_cases.txt";
        if (mode!="--all" && mode!="--representative" && mode!="--rtl") throw std::runtime_error("Unknown test mode");
        std::ifstream f((root+"/"+list).c_str());if (!f) throw std::runtime_error("Case list");
        std::string name;int count=0;
        while (std::getline(f,name)) if (!name.empty()) {
            const int slice=mode=="--rtl" ? (count==0 ? 7 : count==1 ? 5 : 3) : 0;
            run_case(root+"/"+name,slice,mode=="--rtl" && count==2 ? PW_OUTPUT_LANES : 0);++count;
        }
        if (!count) throw std::runtime_error("Empty case list");
#ifdef V7_UNIFIED_TEST
        // Vitis 2025.2 cannot replay the unified top's mixed-width, three-port
        // gmem_output arena after the host vectors are reallocated across eight
        // transactions.  The three fixed real-layer transactions below cover
        // PW RTL arithmetic, channel/time tails and AXI traffic.  The synthetic
        // and dimension-limit cases still run in CSim/native regression.
        if(mode!="--rtl") { synthetic_tests();dimension_limit_tests(); }
#else
        synthetic_tests();dimension_limit_tests();
#endif
        std::cout << "PASS: pointwise " << count << " real cases; mode " << mode << '\n';return 0;
    } catch(const std::exception& e) {std::cerr << "FAIL: " << e.what() << '\n';return 1;}
}
