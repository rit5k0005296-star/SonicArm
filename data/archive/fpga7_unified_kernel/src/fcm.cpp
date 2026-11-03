#include "fcm.h"

static void load_input(const uint64_t* input,hls::stream<uint64_t>& xs,
    int ci,int freq,int frames,int kernel,int stride,int out_f) {
#pragma HLS INLINE off
    const int pad=kernel/2;
    for(int fb=0;fb<out_f;fb+=FCM_F_TILE) {
        const int nf=out_f-fb<FCM_F_TILE ? out_f-fb:FCM_F_TILE;
        const int rows=(nf-1)*stride+kernel;
        for(int tb=0;tb<frames;tb+=FCM_T_TILE) {
            const int nt=frames-tb<FCM_T_TILE ? frames-tb:FCM_T_TILE;
            for(int c=0;c<ci;++c) for(int f=0;f<rows;++f) for(int tw=0;tw<((nt+7)/8*8+kernel-1+7)/8;++tw) {
#pragma HLS PIPELINE II=1
                const int fi=fb*stride+f-pad,ti=tb+tw*8-pad;
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

static void compute(hls::stream<uint64_t>& xs,hls::stream<AccWord>& ys,
    const uint64_t weights[32][36],const int32_t bias[32],int ci,int co,int freq,int frames,
    int kernel,int stride,int xz,int out_f) {
#pragma HLS INLINE off
    int16_t x[32][9][40];
#pragma HLS ARRAY_PARTITION variable=x cyclic factor=8 dim=3
#pragma HLS BIND_STORAGE variable=x type=ram_2p impl=bram
    const int pad=kernel/2;
    for(int fb=0;fb<out_f;fb+=FCM_F_TILE) {
        const int nf=out_f-fb<FCM_F_TILE ? out_f-fb:FCM_F_TILE;
        const int rows=(nf-1)*stride+kernel;
        for(int tb=0;tb<frames;tb+=FCM_T_TILE) {
            const int nt=frames-tb<FCM_T_TILE ? frames-tb:FCM_T_TILE;
            for(int c=0;c<ci;++c) for(int f=0;f<rows;++f) for(int tw=0;tw<((nt+7)/8*8+kernel-1+7)/8;++tw) {
#pragma HLS PIPELINE II=1
                const uint64_t word=xs.read();
                const int fi=fb*stride+f-pad;
                for(int tl=0;tl<8;++tl) {
#pragma HLS UNROLL
                    const int ti=tb+tw*8+tl-pad;
                    x[c][f][tw*8+tl]=(fi<0 || fi>=freq || ti<0 || ti>=frames) ? 0:signed_byte(word,tl)-xz;
                }
            }
            for(int ob=0;ob<co;ob+=FCM_O_LANES) for(int f=0;f<nf;++f) for(int tw=0;tw<(nt+7)/8;++tw) {
                int32_t ps[4][8][8];
#pragma HLS ARRAY_PARTITION variable=ps complete dim=0
                for(int p=0;p<4;++p) for(int o=0;o<8;++o) for(int t=0;t<8;++t) {
#pragma HLS UNROLL
                    ps[p][o][t]=0;
                }
                int c=0,kf=0,kt=0;
mac_kernel:
                for(int wi=0;wi<ci*kernel*kernel;++wi) {
#pragma HLS PIPELINE II=1
#pragma HLS DEPENDENCE variable=ps inter RAW distance=4 true
                    for(int ol=0;ol<8;++ol) {
#pragma HLS UNROLL
                        const int8_t w=static_cast<int8_t>(signed_byte(weights[ob+ol][wi>>3],wi&7));
                        for(int tl=0;tl<8;++tl) {
#pragma HLS UNROLL
                            const int16_t value=x[c][f*stride+kf][tw*8+tl+kt];
                            ps[wi&3][ol][tl]+=value*w;
                        }
                    }
                    if(++kt==kernel) { kt=0; if(++kf==kernel) { kf=0; ++c; } }
                }
                for(int ol=0;ol<8;++ol) if(ob+ol<co) {
                    AccWord out;
                    out.index=((ob+ol)*out_f+fb+f)*frames+tb+tw*8;
                    out.channel=ob+ol;out.valid=nt-tw*8<8 ? nt-tw*8:8;
                    for(int tl=0;tl<8;++tl) {
#pragma HLS UNROLL
                        out.a[tl]=bias[ob+ol]+ps[0][ol][tl]+ps[1][ol][tl]+ps[2][ol][tl]+ps[3][ol][tl];
                    }
                    ys.write(out);
                }
            }
        }
    }
}

static void store(hls::stream<AccWord>& ys,const uint64_t* residual,uint64_t* output,int32_t* debug,
    const uint32_t mult[32],const int8_t lut[65536],int co,int frames,int out_f,int shift,int zp,int flags) {
#pragma HLS INLINE off
    // One 4 KiB tile, plus 1 KiB of row carries. No replicated MAC/requantizer.
    // The original stream order interleaves channels; reorder here so DDR sees
    // consecutive words per row rather than one read/modify/write per fragment.
    uint64_t tile[512];
    uint64_t skips[512];
    uint64_t carries[128];
#pragma HLS BIND_STORAGE variable=tile type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=skips type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=carries type=ram_2p impl=bram
    // Top-level validation proves these bounds. Keep address/loop products
    // narrow: unconstrained signed int products otherwise infer up to 90 bits.
    const unsigned char co_count=co&63,of_count=out_f&127;
    const unsigned short frame_count=frames&4095;
    for(unsigned char fb=0;fb<of_count;fb+=FCM_F_TILE) {
        const unsigned char nf=of_count-fb<FCM_F_TILE ? of_count-fb:FCM_F_TILE;
        for(unsigned short tb=0;tb<frame_count;tb+=FCM_T_TILE) {
            const unsigned char nt=frame_count-tb<FCM_T_TILE ? frame_count-tb:FCM_T_TILE;
            const unsigned char nw=(nt+7)/8;
            // Stage the residual before the continuous scalar pipeline. A
            // read_fragment can need TWO AXI reads: putting it inside the
            // scalar loop forces II>=2 even though it runs only every 8 lanes.
            if(flags&4) for(unsigned char o=0;o<co_count;++o) for(unsigned char r=0;r<nf;++r) for(unsigned char w=0;w<nw;++w) {
#pragma HLS PIPELINE II=2
                const int valid=nt-w*8<8 ? nt-w*8:8;
                skips[(o*4+r)*4+w]=read_fragment(residual,(o*of_count+fb+r)*frame_count+tb+w*8,valid);
            }
            AccWord out;
            uint64_t skip=0,packed=0;
            unsigned char ob=0,f=0,tw=0,ol=0;
            const unsigned char last_ob=(co-1)&~7;
            const unsigned char tail_ol=(co-1)&7;
            // Flatten over ALL words in the tile: a single continuously running
            // scalar requantization pipeline, including the Cin=1 head layer.
requantize_tile:
            for(unsigned i=0;i<(static_cast<unsigned>(co_count)*(nf&7)*(nw&7)<<3);++i) {
#pragma HLS PIPELINE II=1
                const int tl=i&7;
                if(tl==0) {
                    out=ys.read();
                    skip=(flags&4) ? skips[((ob+ol)*4+f)*4+tw]:0;
                }
                int8_t y=0;
                if(tl<out.valid) {
                    const int8_t q=v7_requantize(out.a[tl],mult[out.channel],shift,zp);
                    int li=static_cast<int>(q)+128;
                    if(flags&4) li=li*256+signed_byte(skip,tl)+128;
                    y=(flags&1) ? lut[li]:q;
                    if(flags&2) debug[out.index+tl]=out.a[tl];
                }
                packed=(packed>>8)|(static_cast<uint64_t>(static_cast<uint8_t>(y))<<56);
                if(tl==7) {
                    tile[((ob+ol)*4+f)*4+tw]=packed;
                    const unsigned char last_ol=ob==last_ob ? tail_ol:7;
                    if(ol==last_ol) { ol=0;
                        if(++tw==nw) { tw=0;
                            if(++f==nf) { f=0; ob+=8; }
                        }
                    } else ++ol;
                }
            }
            for(unsigned char o=0;o<co_count;++o) for(unsigned char row=0;row<nf;++row) {
                const int base=(o*of_count+fb+row)*frame_count;
                const int offset=base&7;
                int wi=(base+tb)>>3;
                uint64_t carry=tb ? carries[o*4+row] :
                    (offset ? output[wi]&byte_mask(offset):0);
                int count=offset;
write_row:
                for(int word=0;word<nw;++word) {
#pragma HLS PIPELINE II=1
                    const int valid=nt-word*8<8 ? nt-word*8:8;
                    const uint64_t value=tile[(o*4+row)*4+word];
                    const uint64_t merged=carry|(value<<(offset*8));
                    count=offset+valid;
                    if(count>=8) {
                        output[wi++]=merged;
                        carry=offset ? value>>((8-offset)*8):0;
                        count-=8;
                    } else carry=merged;
                }
                carries[o*4+row]=carry;
                if(tb+nt==frame_count && count) {
                    // Only the final partial word of each dense row needs RMW.
                    // Direct byte decode avoids the historical wide carry chain.
                    const uint64_t mask=byte_mask(count);
                    output[wi]=(output[wi]&~mask)|(carry&mask);
                }
            }
        }
    }
}

static void process(const uint64_t* input,const uint64_t* residual,uint64_t* output,int32_t* debug,
    const uint64_t weights[32][36],const int32_t bias[32],const uint32_t mult[32],const int8_t lut[65536],
    int ci,int co,int freq,int frames,int kernel,int stride,int xz,int yz,int shift,int flags,int out_f) {
#pragma HLS INLINE off
#pragma HLS DATAFLOW
    hls::stream<uint64_t> xs("input_tiles"); hls::stream<AccWord> ys("accumulator_words");
#pragma HLS STREAM variable=xs depth=2048
#pragma HLS STREAM variable=ys depth=32
    load_input(input,xs,ci,freq,frames,kernel,stride,out_f);
    compute(xs,ys,weights,bias,ci,co,freq,frames,kernel,stride,xz,out_f);
    store(ys,residual,output,debug,mult,lut,co,frames,out_f,shift,yz,flags);
}

int fcm_v7(const uint64_t* input,const uint64_t* weights,const int32_t* bias,
    const uint32_t* multiplier,const int8_t* post_lut,const uint64_t* residual,
    uint64_t* output,int32_t* accumulator_out,int cin,int cout,int freq,int frames,
    int kernel,int stride_f,int input_zp,int output_zp,int requant_shift,int flags) {
#pragma HLS INTERFACE mode=m_axi port=input offset=slave bundle=gmem_input depth=16384 max_read_burst_length=64 num_read_outstanding=8
// Residual belongs to the store process. Sharing the input read bundle merges
// load/compute/store into one sequential HLS process and deadlocks finite FIFOs.
#pragma HLS INTERFACE mode=m_axi port=residual offset=slave bundle=gmem_output depth=16384
#pragma HLS INTERFACE mode=m_axi port=weights offset=slave bundle=gmem_params depth=1152 max_read_burst_length=64 num_read_outstanding=8
#pragma HLS INTERFACE mode=m_axi port=bias offset=slave bundle=gmem_params depth=32
#pragma HLS INTERFACE mode=m_axi port=multiplier offset=slave bundle=gmem_params depth=32
#pragma HLS INTERFACE mode=m_axi port=post_lut offset=slave bundle=gmem_params depth=65536
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
    if(cin<1 || cin>32 || cout<1 || cout>32 || freq<1 || freq>80 || frames<1 || frames>2048 ||
       (kernel!=1 && kernel!=3) || (stride_f!=1 && stride_f!=2) || input_zp < -128 || input_zp>127 ||
       output_zp < -128 || output_zp>127 || requant_shift<8 || requant_shift>40 || flags<0 || flags>7 ||
       ((flags&4) && !(flags&1))) return -1;
    uint64_t w[32][36]; int32_t b[32]; uint32_t m[32]; int8_t lut[65536];
#pragma HLS ARRAY_PARTITION variable=w cyclic factor=8 dim=1
#pragma HLS BIND_STORAGE variable=w type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=lut type=ram_2p impl=bram
    for(int o=0;o<32;++o) {
        b[o]=o<cout ? bias[o]:0;m[o]=o<cout ? multiplier[o]:0;
        for(int cw=0;cw<(cin*kernel*kernel+7)/8;++cw) {
#pragma HLS PIPELINE II=1
            const int valid=cin*kernel*kernel-cw*8<8 ? cin*kernel*kernel-cw*8:8;
            w[o][cw]=o<cout ? read_fragment(weights,o*cin*kernel*kernel+cw*8,valid):0;
        }
    }
    if(flags&1) for(int i=0;i<((flags&4) ? 65536:256);++i) {
#pragma HLS PIPELINE II=1
        lut[i]=post_lut[i];
    }
    process(input,residual,output,accumulator_out,w,b,m,lut,cin,cout,freq,frames,kernel,stride_f,input_zp,output_zp,requant_shift,flags,(freq+stride_f-1)/stride_f);
    return 0;
}
