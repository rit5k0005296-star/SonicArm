#include "pointwise.h"

static void load_input(const uint64_t* input,hls::stream<uint64_t>& xs,int cin,int frames) {
#pragma HLS INLINE off
    for(unsigned short tb=0;tb<static_cast<unsigned short>(frames);tb+=PW_TIME_TILE) {
        const int nt=frames-tb<PW_TIME_TILE ? frames-tb:PW_TIME_TILE;
        const int nw=(nt+7)/8;
        for(unsigned short c=0;c<static_cast<unsigned short>(cin);++c) {
            // A dense [C,T] row can start at any byte within a 64-bit AXI
            // word.  Keep the previous aligned word as a carry so an
            // unaligned 8-byte fragment costs one new AXI read, not two.
            const int base=c*frames+tb;
            const int offset=base&7;
            const int first_word=base>>3;
            uint64_t carry=offset ? input[first_word]:0;
            for(unsigned char tw=0;tw<static_cast<unsigned char>(nw);++tw) {
#pragma HLS PIPELINE II=1
                uint64_t value;
                if(offset) {
                    const uint64_t next=input[first_word+tw+1];
                    value=(carry>>(offset*8))|(next<<((8-offset)*8));
                    carry=next;
                } else value=input[first_word+tw];
                const int valid=nt-tw*8<8 ? nt-tw*8:8;
                xs.write(value&byte_mask(valid));
            }
        }
    }
}

static void compute(hls::stream<uint64_t>& xs,hls::stream<AccWord>& ys,
    const uint64_t weights[PW_WEIGHT_CHANNELS][128],const int32_t bias[PW_WEIGHT_CHANNELS],
    int cin,int co,int frames,int xz,int first) {
#pragma HLS INLINE off
    uint64_t x[PW_MAX_CIN][8];
#pragma HLS BIND_STORAGE variable=x type=ram_2p impl=bram
    for(unsigned short tb=0;tb<static_cast<unsigned short>(frames);tb+=PW_TIME_TILE) {
        const int nt=frames-tb<PW_TIME_TILE ? frames-tb:PW_TIME_TILE;
        const int nw=(nt+7)/8;
        for(unsigned short c=0;c<static_cast<unsigned short>(cin);++c)
            for(unsigned char tw=0;tw<static_cast<unsigned char>(nw);++tw) {
#pragma HLS PIPELINE II=1
            x[c][tw]=xs.read();
        }
        for(unsigned short ob=0;ob<static_cast<unsigned short>(co);ob+=PW_OUTPUT_LANES)
            for(unsigned char tw=0;tw<static_cast<unsigned char>(nw);++tw) {
            // Four independent recurrence banks, not a false-dependence waiver.
            // Each bank is revisited exactly every four Cin iterations.
            int32_t ps[4][PW_OUTPUT_LANES][PW_FRAME_LANES];
#pragma HLS ARRAY_PARTITION variable=ps complete dim=0
            for(int p=0;p<4;++p) for(int o=0;o<PW_OUTPUT_LANES;++o) for(int t=0;t<PW_FRAME_LANES;++t) {
#pragma HLS UNROLL
                ps[p][o][t]=0;
            }
mac_channels:
            for(unsigned short c=0;c<static_cast<unsigned short>(cin);++c) {
#pragma HLS PIPELINE II=1
#pragma HLS DEPENDENCE variable=ps inter RAW distance=4 true
                const uint64_t xv=x[c][tw];
                for(int ol=0;ol<PW_OUTPUT_LANES;++ol) {
#pragma HLS UNROLL
                    const uint64_t word=weights[ob+ol][c>>3];
                    const int8_t w=static_cast<int8_t>(signed_byte(word,c&7));
                    for(int tl=0;tl<PW_FRAME_LANES;++tl) {
#pragma HLS UNROLL
                        const int16_t value=static_cast<int16_t>(signed_byte(xv,tl)-xz);
                        ps[c&3][ol][tl]+=value*w;
                    }
                }
            }
            for(int ol=0;ol<PW_OUTPUT_LANES;++ol) if(ob+ol<co) {
                AccWord out;
                out.index=(first+ob+ol)*frames+tb+tw*8;
                out.valid=nt-tw*8<8 ? nt-tw*8:8;
                out.channel=ob+ol;
                for(int tl=0;tl<PW_FRAME_LANES;++tl) {
#pragma HLS UNROLL
                    out.a[tl]=bias[ob+ol]+ps[0][ol][tl]+ps[1][ol][tl]+ps[2][ol][tl]+ps[3][ol][tl];
                }
                ys.write(out);
            }
        }
    }
}

static void store(hls::stream<AccWord>& ys,uint64_t* output,int32_t* debug,
    const uint32_t mult[PW_WEIGHT_CHANNELS],const int8_t lut[256],int co,int frames,
    int shift,int zp,int flags,int first) {
#pragma HLS INLINE off
    // Reorder the compute stream into dense channel rows.  Only a row's final
    // partial AXI word is read/modified/written; complete fragments are written
    // once.  This is the pointwise counterpart of the proven V6 FCM packer.
    uint64_t tile[PW_WEIGHT_CHANNELS][PW_TIME_TILE/8];
    uint64_t carries[PW_WEIGHT_CHANNELS];
#pragma HLS BIND_STORAGE variable=tile type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=carries type=ram_2p impl=bram
    for(unsigned short tb=0;tb<static_cast<unsigned short>(frames);tb+=PW_TIME_TILE) {
        const int nt=frames-tb<PW_TIME_TILE ? frames-tb:PW_TIME_TILE;
        const int nw=(nt+7)/8;
        for(unsigned short ob=0;ob<static_cast<unsigned short>(co);ob+=PW_OUTPUT_LANES)
            for(unsigned char tw=0;tw<static_cast<unsigned char>(nw);++tw)
            for(int ol=0;ol<PW_OUTPUT_LANES;++ol) if(ob+ol<co) {
                const AccWord out=ys.read();
                uint64_t packed=0;
requantize_lanes:
                for(int tl=0;tl<8;++tl) {
#pragma HLS PIPELINE II=1
                    if(tl<out.valid) {
                        const int8_t q=v7_requantize(out.a[tl],mult[out.channel],shift,zp);
                        const int8_t y=(flags&1) ? lut[static_cast<int>(q)+128]:q;
                        packed|=static_cast<uint64_t>(static_cast<uint8_t>(y))<<(tl*8);
                        if(flags&2) debug[out.index+tl]=out.a[tl];
                    }
                }
                tile[ob+ol][tw]=packed;
            }
        for(unsigned short o=0;o<static_cast<unsigned short>(co);++o) {
            const int base=(first+o)*frames;
            const int offset=base&7;
            int wi=(base+tb)>>3;
            uint64_t carry=tb ? carries[o] : (offset ? output[wi]&byte_mask(offset):0);
            int count=offset;
write_row:
            for(unsigned char word=0;word<static_cast<unsigned char>(nw);++word) {
#pragma HLS PIPELINE II=1
                const int valid=nt-word*8<8 ? nt-word*8:8;
                const uint64_t value=tile[o][word];
                const uint64_t merged=carry|(value<<(offset*8));
                count=offset+valid;
                if(count>=8) {
                    output[wi++]=merged;
                    carry=offset ? value>>((8-offset)*8):0;
                    count-=8;
                } else carry=merged;
            }
            carries[o]=carry;
            if(tb+nt==frames && count) {
                const uint64_t mask=byte_mask(count);
                output[wi]=(output[wi]&~mask)|(carry&mask);
            }
        }
    }
}

static void process(const uint64_t* input,uint64_t* output,int32_t* debug,
    const uint64_t weights[PW_WEIGHT_CHANNELS][128],const int32_t bias[PW_WEIGHT_CHANNELS],
    const uint32_t mult[PW_WEIGHT_CHANNELS],const int8_t lut[256],int cin,int co,int frames,
    int xz,int yz,int shift,int flags,int first) {
#pragma HLS INLINE off
#pragma HLS DATAFLOW
    hls::stream<uint64_t> xs("input_tiles");
    hls::stream<AccWord> ys("accumulator_words");
#pragma HLS STREAM variable=xs depth=2048
#pragma HLS STREAM variable=ys depth=32
    load_input(input,xs,cin,frames);
    compute(xs,ys,weights,bias,cin,co,frames,xz,first);
    store(ys,output,debug,mult,lut,co,frames,shift,yz,flags,first);
}

int pointwise_v7(const uint64_t* input,const uint64_t* weights,const int32_t* bias,
    const uint32_t* multiplier,const int8_t* post_lut,uint64_t* output,int32_t* accumulator_out,
    int cin,int cout,int frames,int input_zp,int output_zp,int requant_shift,int flags) {
#pragma HLS INTERFACE mode=m_axi port=input offset=slave bundle=gmem_input depth=16384 max_read_burst_length=64 num_read_outstanding=8
#pragma HLS INTERFACE mode=m_axi port=weights offset=slave bundle=gmem_params depth=65536 max_read_burst_length=64 num_read_outstanding=8
#pragma HLS INTERFACE mode=m_axi port=bias offset=slave bundle=gmem_params depth=512
#pragma HLS INTERFACE mode=m_axi port=multiplier offset=slave bundle=gmem_params depth=512
#pragma HLS INTERFACE mode=m_axi port=post_lut offset=slave bundle=gmem_params depth=256
#pragma HLS INTERFACE mode=m_axi port=output offset=slave bundle=gmem_output depth=16384 max_write_burst_length=64 num_write_outstanding=8
#pragma HLS INTERFACE mode=m_axi port=accumulator_out offset=slave bundle=gmem_output depth=32768
#pragma HLS INTERFACE mode=s_axilite port=input bundle=control
#pragma HLS INTERFACE mode=s_axilite port=weights bundle=control
#pragma HLS INTERFACE mode=s_axilite port=bias bundle=control
#pragma HLS INTERFACE mode=s_axilite port=multiplier bundle=control
#pragma HLS INTERFACE mode=s_axilite port=post_lut bundle=control
#pragma HLS INTERFACE mode=s_axilite port=output bundle=control
#pragma HLS INTERFACE mode=s_axilite port=accumulator_out bundle=control
#pragma HLS INTERFACE mode=s_axilite port=cin bundle=control
#pragma HLS INTERFACE mode=s_axilite port=cout bundle=control
#pragma HLS INTERFACE mode=s_axilite port=frames bundle=control
#pragma HLS INTERFACE mode=s_axilite port=input_zp bundle=control
#pragma HLS INTERFACE mode=s_axilite port=output_zp bundle=control
#pragma HLS INTERFACE mode=s_axilite port=requant_shift bundle=control
#pragma HLS INTERFACE mode=s_axilite port=flags bundle=control
#pragma HLS INTERFACE mode=s_axilite port=return bundle=control
    if(cin<1 || cin>1024 || cout<1 || cout>512 || frames<1 || frames>2048 || input_zp < -128 || input_zp>127 ||
       output_zp < -128 || output_zp>127 || requant_shift<8 || requant_shift>40 || flags<0 || flags>3) return -1;
    uint64_t w[PW_WEIGHT_CHANNELS][128];
    int32_t b[PW_WEIGHT_CHANNELS]; uint32_t m[PW_WEIGHT_CHANNELS]; int8_t lut[256];
#pragma HLS ARRAY_PARTITION variable=w cyclic factor=PW_OUTPUT_LANES dim=1
#pragma HLS BIND_STORAGE variable=w type=ram_2p impl=bram
    if(flags&1) for(int i=0;i<256;++i) {
#pragma HLS PIPELINE II=1
        lut[i]=post_lut[i];
    }
    for(unsigned short first=0;first<static_cast<unsigned short>(cout);first+=PW_WEIGHT_CHANNELS) {
        const int co=cout-first<PW_WEIGHT_CHANNELS ? cout-first:PW_WEIGHT_CHANNELS;
        for(unsigned short o=0;o<PW_WEIGHT_CHANNELS;++o) {
            b[o]=o<co ? bias[first+o]:0;
            m[o]=o<co ? multiplier[first+o]:0;
            // Stream each dense weight row with one new aligned AXI read per
            // output word.  This also removes the V6 II=2 resource conflict
            // caused by two read_fragment accesses on gmem_params.
            const int base=(first+o)*cin;
            const int offset=base&7;
            const int first_word=base>>3;
            uint64_t carry=(o<co && offset) ? weights[first_word]:0;
            for(unsigned short cw=0;cw<static_cast<unsigned short>((cin+7)/8);++cw) {
#pragma HLS PIPELINE II=1
                const int valid=cin-cw*8<8 ? cin-cw*8:8;
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
        process(input,output,accumulator_out,w,b,m,lut,cin,co,frames,input_zp,output_zp,requant_shift,flags,first);
    }
    return 0;
}
