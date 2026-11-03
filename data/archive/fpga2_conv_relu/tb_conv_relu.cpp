#include "conv_relu.h"
#include <algorithm>
#include <climits>
#include <cmath>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

template<class T> std::vector<T> read_bin(const std::string& dir, const char* name, size_t count) {
    std::ifstream f((dir + "/" + name).c_str(), std::ios::binary | std::ios::ate);
    if (!f || f.tellg() != static_cast<std::streamoff>(count*sizeof(T)))
        throw std::runtime_error(std::string("Missing/wrong-sized binary: ") + dir + "/" + name);
    std::vector<T> x(count);
    f.seekg(0); f.read(reinterpret_cast<char*>(x.data()), count*sizeof(T));
    if (!f) throw std::runtime_error("Short binary read");
    return x;
}

// Independent division/remainder rounding, rather than the kernel's bit shifts.
int8_t integer_golden(int32_t acc, uint32_t q40) {
    const int64_t p = static_cast<int64_t>(acc)*q40;
    const int64_t unit = INT64_C(1)<<40;
    int64_t q = p/unit;
    const int64_t r = p%unit;
    const uint64_t mag = r < 0 ? static_cast<uint64_t>(-r) : static_cast<uint64_t>(r);
    if (mag > static_cast<uint64_t>(unit/2) ||
        (mag == static_cast<uint64_t>(unit/2) && q%2 != 0)) q += p < 0 ? -1 : 1;
    return static_cast<int8_t>(std::max<int64_t>(-128,std::min<int64_t>(127,q+CONV_OUTPUT_ZERO_POINT)));
}

int8_t post_golden(int q1) {
    const double real = std::max(0.0,(q1-CONV_OUTPUT_ZERO_POINT)*POST_INPUT_SCALE);
    const double value = real/POST_OUTPUT_SCALE;
    const double lower = std::floor(value), fraction = value-lower;
    int64_t q = static_cast<int64_t>(lower);
    if (fraction > .5 || (fraction == .5 && q%2 != 0)) ++q;
    return static_cast<int8_t>(std::max<int64_t>(-128,std::min<int64_t>(127,q+POST_OUTPUT_ZERO_POINT)));
}

void rounding_tests() {
    const int32_t values[] = {0,255,256,257,768,1280,-255,-256,-257,-768,-1280,INT32_MAX,INT32_MIN};
    const uint32_t scales[] = {0,1,UINT32_C(1)<<31,UINT32_MAX};
    for (uint32_t s : scales) for (int32_t x : values)
        if (conv_relu_requantize(x,s) != integer_golden(x,s)) throw std::runtime_error("Q40 rounding/saturation boundary");
    uint32_t state = 1;
    for (int i=0;i<2048;++i) {
        state = state*1664525u+1013904223u;
        const int32_t x = static_cast<int32_t>(state);
        state = state*1664525u+1013904223u;
        if (conv_relu_requantize(x,state) != integer_golden(x,state)) throw std::runtime_error("Q40 randomized arithmetic");
    }
    std::cout << "[PASS] Q40 signed ties, endpoints, saturation and 2048 random products\n";
}

void verify_call(const std::vector<int8_t>& x,const std::vector<int8_t>& w,
                 const std::vector<int32_t>& b,const std::vector<uint32_t>& q40,
                 const std::vector<int8_t>& lut,const std::vector<int32_t>* reference_acc,
                 const std::vector<int8_t>* reference_q1,const std::vector<int8_t>* reference_final) {
    std::vector<int32_t> actual_acc(CR_OUTPUT_ELEMENTS,0x5a5a5a5a);
    std::vector<int8_t> actual(CR_OUTPUT_ELEMENTS,85);
    conv_relu(x.data(),w.data(),b.data(),q40.data(),lut.data(),actual.data(),actual_acc.data());
    size_t errors = 0;
    for (int o=0;o<CONV_COUT;++o) for (int t=0;t<CONV_T;++t) {
        int64_t sum = b[o];
        for (int c=0;c<CONV_CIN;++c) {
            sum += (static_cast<int64_t>(x[c*CONV_T+t])-CONV_INPUT_ZERO_POINT)*w[o*CONV_CIN+c];
            if (sum<INT32_MIN || sum>INT32_MAX) throw std::runtime_error("INT32 partial sum overflow");
        }
        const int index=o*CONV_T+t;
        const int8_t q1=integer_golden(static_cast<int32_t>(sum),q40[o]);
        const int8_t final=post_golden(q1);
        const bool bad=actual_acc[index]!=sum || actual[index]!=final ||
             (reference_acc && (*reference_acc)[index]!=sum) ||
             (reference_q1 && (*reference_q1)[index]!=q1) ||
             (reference_final && (*reference_final)[index]!=final);
        if (bad && ++errors<=4) std::cerr << "Mismatch c=" << o << " t=" << t << '\n';
    }
    if (errors) throw std::runtime_error("Kernel/reference element mismatch");
    std::cout << "[PASS] " << CR_OUTPUT_ELEMENTS << " INT32/final INT8 elements; final time lanes included\n";
}

void run_case(const std::string& dir, bool synthetic) {
    const std::vector<int8_t> x=read_bin<int8_t>(dir,"input_int8.bin",CR_INPUT_ELEMENTS);
    std::vector<int8_t> w=read_bin<int8_t>(dir,"weights_int8.bin",CR_WEIGHT_ELEMENTS);
    std::vector<int32_t> b=read_bin<int32_t>(dir,"bias_int32.bin",CONV_COUT);
    const std::vector<uint32_t> q40=read_bin<uint32_t>(dir,"requant_q40_uint32.bin",CONV_COUT);
    const std::vector<int8_t> lut=read_bin<int8_t>(dir,"post_lut_int8.bin",256);
    const std::vector<int32_t> acc=read_bin<int32_t>(dir,"reference_accum_int32.bin",CR_OUTPUT_ELEMENTS);
    const std::vector<int8_t> q1=read_bin<int8_t>(dir,"reference_conv_output_int8.bin",CR_OUTPUT_ELEMENTS);
    const std::vector<int8_t> oq1=read_bin<int8_t>(dir,"onnx_conv_output_int8.bin",CR_OUTPUT_ELEMENTS);
    const std::vector<int8_t> final=read_bin<int8_t>(dir,"reference_output_int8.bin",CR_OUTPUT_ELEMENTS);
    const std::vector<int8_t> ofinal=read_bin<int8_t>(dir,"onnx_output_int8.bin",CR_OUTPUT_ELEMENTS);
    if (q1!=oq1 || final!=ofinal) throw std::runtime_error("ONNX references are not exact");
    for (int k=0;k<256;++k) if (lut[k]!=post_golden(k-128)) throw std::runtime_error("Full LUT test failed");
    for (int o=0;o<CONV_COUT;++o) {
        const uint32_t expected=static_cast<uint32_t>(std::floor(CONV_REQUANT_MULTIPLIER[o]*(UINT64_C(1)<<40)+.5));
        if (q40[o]!=expected) throw std::runtime_error("Header/Q40 mismatch");
    }
    std::cout << "[CASE] " << dir << '\n';
    verify_call(x,w,b,q40,lut,&acc,&q1,&final);
    if (synthetic) {
        std::vector<int8_t> altered(CR_INPUT_ELEMENTS,static_cast<int8_t>(CONV_INPUT_ZERO_POINT));
        verify_call(altered,w,b,q40,lut,0,0,0);
        for (int c=0;c<CONV_CIN;++c) for (int t=0;t<CONV_T;++t)
            altered[c*CONV_T+t]=static_cast<int8_t>((c+t)%2 ? 127 : -128);
        for (int o=0;o<CONV_COUT;++o) {
            b[o]=o*17-1000;
            for (int c=0;c<CONV_CIN;++c) w[o*CONV_CIN+c]=static_cast<int8_t>((o+c)%2 ? 127 : -128);
        }
        verify_call(altered,w,b,q40,lut,0,0,0);
        std::cout << "[PASS] Zero-centered input, changed weights/bias, repeated calls and INT8 endpoints\n";
    }
}

int main(int argc,char** argv) {
    try {
        static_assert(CHAR_BIT==8 && sizeof(int32_t)==4,"Host integer types");
        const uint16_t endian=1;
        if (*reinterpret_cast<const unsigned char*>(&endian)!=1) throw std::runtime_error("Little endian required");
        if (argc>3) throw std::runtime_error("Usage: tb_conv_relu [directory] [--all]");
        rounding_tests();
        const std::string dir=argc>1 ? argv[1] : ".";
        if (argc==3) {
            if (std::string(argv[2])!="--all") throw std::runtime_error("Unknown test option");
            const char* names[]={"case_001","case_002","case_003","case_004","case_005"};
            for (int i=0;i<5;++i) run_case(dir+"/"+names[i],i==0);
        } else run_case(dir,true);
        std::cout << "PASS: conv_relu test bench\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr << "FAIL: " << e.what() << '\n'; return 1;
    }
}
