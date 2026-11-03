#include "unified.h"
#include "pointwise.h"
#include "fcm.h"

#define V7_MAX_CIN 1024
#define V7_MAX_COUT 512
#define V7_WEIGHT_CHANNELS 128
#define V7_OUTPUT_LANES 8
#define V7_TIME_LANES 8
#define V7_PW_T_TILE 64
#define V7_FCM_T_TILE 32
#define V7_FCM_F_TILE 4

static void load_dense_segment(const uint64_t* input,hls::stream<uint64_t>& xs,
    int base,int count) {
#pragma HLS INLINE
    const unsigned char nw=(count+7)/8;
    const unsigned char offset=base&7;
    const int first_word=base>>3;
    uint64_t carry=offset ? input[first_word]:0;
    for(unsigned char w=0;w<nw;++w) {
#pragma HLS PIPELINE II=1
        uint64_t value;
        if(offset) {
            const uint64_t next=input[first_word+w+1];
            value=(carry>>(offset*8))|(next<<((8-offset)*8));
            carry=next;
        } else value=input[first_word+w];
        const int valid=count-w*8<8 ? count-w*8:8;
        xs.write(value&byte_mask(valid));
    }
}

static void load_input(const uint64_t* input,hls::stream<uint64_t>& xs,int mode,
    int ci,int freq,int frames,int kernel,int stride,int out_f) {
#pragma HLS INLINE off
    const int f_tile=mode==V7_MODE_FCM ? V7_FCM_F_TILE:1;
    const int t_tile=mode==V7_MODE_FCM ? V7_FCM_T_TILE:V7_PW_T_TILE;
    const int f_extent=mode==V7_MODE_FCM ? out_f:1;
    const int pad=kernel/2;
    for(unsigned char fb=0;fb<static_cast<unsigned char>(f_extent);fb+=f_tile) {
        const int nf=f_extent-fb<f_tile ? f_extent-fb:f_tile;
        const int rows=mode==V7_MODE_FCM ? (nf-1)*stride+kernel:1;
        for(unsigned short tb=0;tb<static_cast<unsigned short>(frames);tb+=t_tile) {
            const int nt=frames-tb<t_tile ? frames-tb:t_tile;
            if(mode==V7_MODE_POINTWISE) {
                for(unsigned short c=0;c<static_cast<unsigned short>(ci);++c)
                    load_dense_segment(input,xs,c*frames+tb,nt);
            } else {
                const int input_words=(((nt+7)/8)*8+kernel-1+7)/8;
                for(unsigned char c=0;c<static_cast<unsigned char>(ci);++c)
                    for(unsigned char f=0;f<static_cast<unsigned char>(rows);++f)
                        for(unsigned char tw=0;tw<static_cast<unsigned char>(input_words);++tw) {
#pragma HLS PIPELINE II=1
                            const int fi=fb*stride+f-pad;
                            const int ti=tb+tw*8-pad;
                            const int lead=ti<0 ? -ti:0;
                            const int remain=frames-ti<8 ? frames-ti:8;
                            const int valid=remain-lead;
                            uint64_t word=0;
                            if(fi>=0 && fi<freq && valid>0)
                                word=read_fragment(input,(c*freq+fi)*frames+ti+lead,valid)<<(lead*8);
                            xs.write(word);
                        }
            }
        }
    }
}

static void compute(hls::stream<uint64_t>& xs,hls::stream<AccWord>& ys,
    const uint64_t weights[V7_WEIGHT_CHANNELS][128],const int32_t bias[V7_WEIGHT_CHANNELS],
    int mode,int ci,int co,int freq,int frames,int kernel,int stride,int xz,int out_f,int first) {
#pragma HLS INLINE off
    uint64_t x_pw[PW_MAX_CIN][V7_PW_T_TILE/8];
    int16_t x_fcm[FCM_MAX_C][9][40];
#pragma HLS BIND_STORAGE variable=x_pw type=ram_2p impl=bram
#pragma HLS ARRAY_PARTITION variable=x_fcm cyclic factor=8 dim=3
#pragma HLS BIND_STORAGE variable=x_fcm type=ram_2p impl=bram
    const int f_tile=mode==V7_MODE_FCM ? V7_FCM_F_TILE:1;
    const int t_tile=mode==V7_MODE_FCM ? V7_FCM_T_TILE:V7_PW_T_TILE;
    const int f_extent=mode==V7_MODE_FCM ? out_f:1;
    const int pad=kernel/2;
    for(unsigned char fb=0;fb<static_cast<unsigned char>(f_extent);fb+=f_tile) {
        const int nf=f_extent-fb<f_tile ? f_extent-fb:f_tile;
        const int rows=mode==V7_MODE_FCM ? (nf-1)*stride+kernel:1;
        for(unsigned short tb=0;tb<static_cast<unsigned short>(frames);tb+=t_tile) {
            const int nt=frames-tb<t_tile ? frames-tb:t_tile;
            const unsigned char nw=(nt+7)/8;
            if(mode==V7_MODE_POINTWISE) {
                for(unsigned short c=0;c<static_cast<unsigned short>(ci);++c)
                    for(unsigned char tw=0;tw<nw;++tw) {
#pragma HLS PIPELINE II=1
                        x_pw[c][tw]=xs.read();
                    }
            } else {
                const unsigned char input_words=(((nt+7)/8)*8+kernel-1+7)/8;
                for(unsigned char c=0;c<static_cast<unsigned char>(ci);++c)
                    for(unsigned char f=0;f<static_cast<unsigned char>(rows);++f)
                        for(unsigned char tw=0;tw<input_words;++tw) {
#pragma HLS PIPELINE II=1
                            const uint64_t word=xs.read();
                            const int fi=fb*stride+f-pad;
                            for(int tl=0;tl<V7_TIME_LANES;++tl) {
#pragma HLS UNROLL
                                const int ti=tb+tw*8+tl-pad;
                                x_fcm[c][f][tw*8+tl]=(fi<0 || fi>=freq || ti<0 || ti>=frames) ?
                                    0:signed_byte(word,tl)-xz;
                            }
                        }
            }
            for(unsigned short ob=0;ob<static_cast<unsigned short>(co);ob+=V7_OUTPUT_LANES)
                for(unsigned char f=0;f<static_cast<unsigned char>(nf);++f)
                    for(unsigned char tw=0;tw<nw;++tw) {
                        int32_t ps[4][V7_OUTPUT_LANES][V7_TIME_LANES];
#pragma HLS ARRAY_PARTITION variable=ps complete dim=0
                        for(int p=0;p<4;++p) for(int o=0;o<V7_OUTPUT_LANES;++o)
                            for(int t=0;t<V7_TIME_LANES;++t) {
#pragma HLS UNROLL
                                ps[p][o][t]=0;
                            }
                        int c=0,kf=0,kt=0;
                        const int work=mode==V7_MODE_FCM ? ci*kernel*kernel:ci;
shared_mac:
                        for(unsigned short wi=0;wi<static_cast<unsigned short>(work);++wi) {
#pragma HLS PIPELINE II=1
#pragma HLS DEPENDENCE variable=ps inter RAW distance=4 true
                            const uint64_t xv=mode==V7_MODE_POINTWISE ? x_pw[wi][tw]:0;
                            for(int ol=0;ol<V7_OUTPUT_LANES;++ol) {
#pragma HLS UNROLL
                                const int8_t w=static_cast<int8_t>(signed_byte(weights[ob+ol][wi>>3],wi&7));
                                for(int tl=0;tl<V7_TIME_LANES;++tl) {
#pragma HLS UNROLL
                                    const int16_t value=mode==V7_MODE_POINTWISE ?
                                        static_cast<int16_t>(signed_byte(xv,tl)-xz):
                                        x_fcm[c][f*stride+kf][tw*8+tl+kt];
                                    ps[wi&3][ol][tl]+=value*w;
                                }
                            }
                            if(mode==V7_MODE_FCM && ++kt==kernel) {
                                kt=0;
                                if(++kf==kernel) { kf=0; ++c; }
                            }
                        }
                        for(int ol=0;ol<V7_OUTPUT_LANES;++ol) if(ob+ol<co) {
                            AccWord out;
                            out.index=mode==V7_MODE_POINTWISE ?
                                (first+ob+ol)*frames+tb+tw*8:
                                ((ob+ol)*out_f+fb+f)*frames+tb+tw*8;
                            out.valid=nt-tw*8<8 ? nt-tw*8:8;
                            out.channel=ob+ol;
                            for(int tl=0;tl<V7_TIME_LANES;++tl) {
#pragma HLS UNROLL
                                out.a[tl]=bias[ob+ol]+ps[0][ol][tl]+ps[1][ol][tl]+ps[2][ol][tl]+ps[3][ol][tl];
                            }
                            ys.write(out);
                        }
                    }
        }
    }
}

static void store(hls::stream<AccWord>& ys,const uint64_t* residual,uint64_t* output,
    int32_t* debug,const uint32_t mult[V7_WEIGHT_CHANNELS],const int8_t lut[65536],
    int mode,int co,int frames,int out_f,int shift,int zp,int flags,int first) {
#pragma HLS INLINE off
    uint64_t tile[1024];
    uint64_t skips[512];
    uint64_t carries[128];
#pragma HLS BIND_STORAGE variable=tile type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=skips type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=carries type=ram_2p impl=bram
    const int f_tile=mode==V7_MODE_FCM ? V7_FCM_F_TILE:1;
    const int t_tile=mode==V7_MODE_FCM ? V7_FCM_T_TILE:V7_PW_T_TILE;
    const int f_extent=mode==V7_MODE_FCM ? out_f:1;
    for(unsigned char fb=0;fb<static_cast<unsigned char>(f_extent);fb+=f_tile) {
        const unsigned char nf=f_extent-fb<f_tile ? f_extent-fb:f_tile;
        for(unsigned short tb=0;tb<static_cast<unsigned short>(frames);tb+=t_tile) {
            const unsigned char nt=frames-tb<t_tile ? frames-tb:t_tile;
            const unsigned char nw=(nt+7)/8;
            if(mode==V7_MODE_FCM && (flags&4))
                for(unsigned char o=0;o<static_cast<unsigned char>(co);++o)
                    for(unsigned char f=0;f<nf;++f)
                        for(unsigned char w=0;w<nw;++w) {
#pragma HLS PIPELINE II=2
                            const int valid=nt-w*8<8 ? nt-w*8:8;
                            skips[(o*nf+f)*nw+w]=read_fragment(residual,
                                (o*out_f+fb+f)*frames+tb+w*8,valid);
                        }
            AccWord out;
            uint64_t skip=0,packed=0;
            unsigned short ob=0;
            unsigned char f=0,tw=0,ol=0;
            const unsigned short last_ob=(co-1)&~7;
            const unsigned char tail_ol=(co-1)&7;
            const unsigned total=static_cast<unsigned>(co)*nf*nw*8;
requantize_tile:
            for(unsigned i=0;i<total;++i) {
#pragma HLS PIPELINE II=1
                const int tl=i&7;
                if(tl==0) {
                    out=ys.read();
                    skip=(mode==V7_MODE_FCM && (flags&4)) ? skips[(out.channel*nf+f)*nw+tw]:0;
                }
                int8_t y=0;
                if(tl<out.valid) {
                    const int8_t q=v7_requantize(out.a[tl],mult[out.channel],shift,zp);
                    int li=static_cast<int>(q)+128;
                    if(mode==V7_MODE_FCM && (flags&4)) li=li*256+signed_byte(skip,tl)+128;
                    y=(flags&1) ? lut[li]:q;
                    if(flags&2) debug[out.index+tl]=out.a[tl];
                }
                packed=(packed>>8)|(static_cast<uint64_t>(static_cast<uint8_t>(y))<<56);
                if(tl==7) {
                    tile[(out.channel*nf+f)*nw+tw]=packed;
                    const unsigned char last_ol=ob==last_ob ? tail_ol:7;
                    if(ol==last_ol) {
                        ol=0;
                        if(++tw==nw) {
                            tw=0;
                            if(++f==nf) { f=0; ob+=8; }
                        }
                    } else ++ol;
                }
            }
            for(unsigned short o=0;o<static_cast<unsigned short>(co);++o)
                for(unsigned char row_f=0;row_f<nf;++row_f) {
                    const int row=o*nf+row_f;
                    const int base=mode==V7_MODE_POINTWISE ?
                        (first+o)*frames:(o*out_f+fb+row_f)*frames;
                    const int offset=base&7;
                    int wi=(base+tb)>>3;
                    uint64_t carry=tb ? carries[row] : (offset ? output[wi]&byte_mask(offset):0);
                    int count=offset;
write_row:
                    for(unsigned char word=0;word<nw;++word) {
#pragma HLS PIPELINE II=1
                        const int valid=nt-word*8<8 ? nt-word*8:8;
                        const uint64_t value=tile[row*nw+word];
                        const uint64_t merged=carry|(value<<(offset*8));
                        count=offset+valid;
                        if(count>=8) {
                            output[wi++]=merged;
                            carry=offset ? value>>((8-offset)*8):0;
                            count-=8;
                        } else carry=merged;
                    }
                    carries[row]=carry;
                    if(tb+nt==frames && count) {
                        const uint64_t mask=byte_mask(count);
                        output[wi]=(output[wi]&~mask)|(carry&mask);
                    }
                }
        }
    }
}

static void process(const uint64_t* input,const uint64_t* residual,uint64_t* output,
    int32_t* debug,const uint64_t weights[V7_WEIGHT_CHANNELS][128],
    const int32_t bias[V7_WEIGHT_CHANNELS],const uint32_t mult[V7_WEIGHT_CHANNELS],
    const int8_t lut[65536],int mode,int ci,int co,int freq,int frames,int kernel,
    int stride,int xz,int yz,int shift,int flags,int out_f,int first) {
#pragma HLS INLINE off
#pragma HLS DATAFLOW
    hls::stream<uint64_t> xs("input_tiles");
    hls::stream<AccWord> ys("accumulator_words");
#pragma HLS STREAM variable=xs depth=2048
#pragma HLS STREAM variable=ys depth=32
    load_input(input,xs,mode,ci,freq,frames,kernel,stride,out_f);
    compute(xs,ys,weights,bias,mode,ci,co,freq,frames,kernel,stride,xz,out_f,first);
    store(ys,residual,output,debug,mult,lut,mode,co,frames,out_f,shift,yz,flags,first);
}

int unified_v7(const uint64_t* input,const uint64_t* weights,const int32_t* bias,
    const uint32_t* multiplier,const int8_t* post_lut,const uint64_t* residual,
    uint64_t* output,int32_t* accumulator_out,int mode,int cin,int cout,int freq,
    int frames,int kernel,int stride_f,int input_zp,int output_zp,int requant_shift,
    int flags) {
#pragma HLS INTERFACE mode=m_axi port=input offset=slave bundle=gmem_input depth=16384 max_read_burst_length=64 num_read_outstanding=8
#pragma HLS INTERFACE mode=m_axi port=weights offset=slave bundle=gmem_params depth=65536 max_read_burst_length=64 num_read_outstanding=8
#pragma HLS INTERFACE mode=m_axi port=bias offset=slave bundle=gmem_params depth=512
#pragma HLS INTERFACE mode=m_axi port=multiplier offset=slave bundle=gmem_params depth=512
#pragma HLS INTERFACE mode=m_axi port=post_lut offset=slave bundle=gmem_params depth=65536
#pragma HLS INTERFACE mode=m_axi port=residual offset=slave bundle=gmem_output depth=16384
#pragma HLS INTERFACE mode=m_axi port=output offset=slave bundle=gmem_output depth=16384 max_write_burst_length=64 num_write_outstanding=8
#pragma HLS INTERFACE mode=m_axi port=accumulator_out offset=slave bundle=gmem_output depth=32768
#pragma HLS INTERFACE mode=s_axilite port=input bundle=control
#pragma HLS INTERFACE mode=s_axilite port=weights bundle=control
#pragma HLS INTERFACE mode=s_axilite port=bias bundle=control
#pragma HLS INTERFACE mode=s_axilite port=multiplier bundle=control
#pragma HLS INTERFACE mode=s_axilite port=post_lut bundle=control
#pragma HLS INTERFACE mode=s_axilite port=residual bundle=control
#pragma HLS INTERFACE mode=s_axilite port=output bundle=control
#pragma HLS INTERFACE mode=s_axilite port=accumulator_out bundle=control
#pragma HLS INTERFACE mode=s_axilite port=mode bundle=control
#pragma HLS INTERFACE mode=s_axilite port=cin bundle=control
#pragma HLS INTERFACE mode=s_axilite port=cout bundle=control
#pragma HLS INTERFACE mode=s_axilite port=freq bundle=control
#pragma HLS INTERFACE mode=s_axilite port=frames bundle=control
#pragma HLS INTERFACE mode=s_axilite port=kernel bundle=control
#pragma HLS INTERFACE mode=s_axilite port=stride_f bundle=control
#pragma HLS INTERFACE mode=s_axilite port=input_zp bundle=control
#pragma HLS INTERFACE mode=s_axilite port=output_zp bundle=control
#pragma HLS INTERFACE mode=s_axilite port=requant_shift bundle=control
#pragma HLS INTERFACE mode=s_axilite port=flags bundle=control
#pragma HLS INTERFACE mode=s_axilite port=return bundle=control
    const bool common=mode>=V7_MODE_POINTWISE && mode<=V7_MODE_FCM && frames>=1 && frames<=2048 &&
        input_zp>=-128 && input_zp<=127 && output_zp>=-128 && output_zp<=127 &&
        requant_shift>=8 && requant_shift<=40;
    const bool pw=mode==V7_MODE_POINTWISE && cin>=1 && cin<=1024 && cout>=1 && cout<=512 &&
        freq==1 && kernel==1 && stride_f==1 && flags>=0 && flags<=3;
    const bool fcm=mode==V7_MODE_FCM && cin>=1 && cin<=32 && cout>=1 && cout<=32 &&
        freq>=1 && freq<=80 && (kernel==1 || kernel==3) &&
        (stride_f==1 || stride_f==2) && flags>=0 && flags<=7 &&
        (!((flags&4) && !(flags&1)));
    if(!common || (!pw && !fcm)) return -1;

    uint64_t w[V7_WEIGHT_CHANNELS][128];
    int32_t b[V7_WEIGHT_CHANNELS];
    uint32_t m[V7_WEIGHT_CHANNELS];
    int8_t lut[65536];
#pragma HLS ARRAY_PARTITION variable=w cyclic factor=V7_OUTPUT_LANES dim=1
#pragma HLS BIND_STORAGE variable=w type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=lut type=ram_2p impl=bram
    const int out_f=mode==V7_MODE_FCM ? (freq+stride_f-1)/stride_f:1;
    const int weight_count=mode==V7_MODE_FCM ? cin*kernel*kernel:cin;
    const int step=V7_WEIGHT_CHANNELS;
    for(unsigned short first=0;first<static_cast<unsigned short>(cout);first+=step) {
        const int co=cout-first<step ? cout-first:step;
        // Only the lanes that the shared 8-output MAC can actually consume
        // need resident parameters.  Loading all 128 rows made every FCM call
        // pay for 96 unreachable output channels and penalized pointwise tails.
        const unsigned short loaded_co=(co+V7_OUTPUT_LANES-1)&~(V7_OUTPUT_LANES-1);
        for(unsigned short o=0;o<loaded_co;++o) {
            b[o]=o<co ? bias[first+o]:0;
            m[o]=o<co ? multiplier[first+o]:0;
            const int base=(first+o)*weight_count;
            const int offset=base&7;
            const int first_word=base>>3;
            uint64_t carry=(o<co && offset) ? weights[first_word]:0;
            for(unsigned short cw=0;cw<static_cast<unsigned short>((weight_count+7)/8);++cw) {
#pragma HLS PIPELINE II=1
                const int valid=weight_count-cw*8<8 ? weight_count-cw*8:8;
                uint64_t value=0;
                if(o<co) {
                    if(offset) {
                        const uint64_t next=weights[first_word+cw+1];
                        value=(carry>>(offset*8))|(next<<((8-offset)*8));
                        carry=next;
                    } else value=weights[first_word+cw];
                }
                w[o][cw]=value&byte_mask(valid);
            }
        }
        if(flags&1) for(unsigned i=0;i<static_cast<unsigned>((mode==V7_MODE_FCM && (flags&4)) ? 65536:256);++i) {
#pragma HLS PIPELINE II=1
            lut[i]=post_lut[i];
        }
        process(input,residual,output,accumulator_out,w,b,m,lut,mode,cin,co,freq,frames,
            kernel,stride_f,input_zp,output_zp,requant_shift,flags,out_f,first);
    }
    return 0;
}

// Native/CSim compatibility entry points let the existing V6 reference tests
// exercise both modes without weakening the unified hardware top contract.
int pointwise_v7(const uint64_t* input,const uint64_t* weights,const int32_t* bias,
    const uint32_t* multiplier,const int8_t* post_lut,uint64_t* output,int32_t* accumulator_out,
    int cin,int cout,int frames,int input_zp,int output_zp,int requant_shift,int flags) {
    // residual is unused in pointwise mode.  Keep the dummy address in the
    // gmem_output bundle so C/RTL co-simulation does not alias one host pointer
    // across two independent AXI masters.
    return unified_v7(input,weights,bias,multiplier,post_lut,output,output,accumulator_out,
        V7_MODE_POINTWISE,cin,cout,1,frames,1,1,input_zp,output_zp,requant_shift,flags);
}

int fcm_v7(const uint64_t* input,const uint64_t* weights,const int32_t* bias,
    const uint32_t* multiplier,const int8_t* post_lut,const uint64_t* residual,
    uint64_t* output,int32_t* accumulator_out,int cin,int cout,int freq,int frames,
    int kernel,int stride_f,int input_zp,int output_zp,int requant_shift,int flags) {
    return unified_v7(input,weights,bias,multiplier,post_lut,residual,output,accumulator_out,
        V7_MODE_FCM,cin,cout,freq,frames,kernel,stride_f,input_zp,output_zp,requant_shift,flags);
}
