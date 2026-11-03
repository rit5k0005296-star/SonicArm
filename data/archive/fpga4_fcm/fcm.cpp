#include "fcm.h"

extern "C" int fcm(const int8_t* input, const int8_t* weights, const int32_t* bias,
                   const uint32_t* multiplier, const int8_t* post_lut,
                   const int8_t* residual, int8_t* output, int32_t* accumulator_out,
                   int cin, int cout, int freq, int frames, int kernel, int stride_f,
                   int input_zp, int output_zp, int requant_shift, int flags) {
#pragma HLS INTERFACE mode=m_axi port=input offset=slave bundle=gmem_input depth=16384
#pragma HLS INTERFACE mode=m_axi port=residual offset=slave bundle=gmem_input depth=16384
#pragma HLS INTERFACE mode=m_axi port=weights offset=slave bundle=gmem_params depth=9216
#pragma HLS INTERFACE mode=m_axi port=bias offset=slave bundle=gmem_params depth=32
#pragma HLS INTERFACE mode=m_axi port=multiplier offset=slave bundle=gmem_params depth=32
#pragma HLS INTERFACE mode=m_axi port=post_lut offset=slave bundle=gmem_params depth=65536
#pragma HLS INTERFACE mode=m_axi port=output offset=slave bundle=gmem_output depth=16384
#pragma HLS INTERFACE mode=m_axi port=accumulator_out offset=slave bundle=gmem_output depth=16384
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
    if(cin<1 || cin>FCM_MAX_C || cout<1 || cout>FCM_MAX_C || freq<1 || freq>FCM_MAX_F ||
       frames<1 || frames>FCM_MAX_T || (kernel!=1 && kernel!=3) || (stride_f!=1 && stride_f!=2) ||
       input_zp < -128 || input_zp>127 || output_zp < -128 || output_zp>127 ||
       requant_shift<8 || requant_shift>40 || flags<0 || flags>7 ||
       ((flags&FCM_FLAG_RESIDUAL) && !(flags&FCM_FLAG_LUT))) return -1;
    const int out_f=stride_f==2 ? ((freq+1)>>1) : freq, pad=kernel/2;
    int16_t x[FCM_MAX_C][9][FCM_T_TILE+2];
    int8_t w[FCM_MAX_C*9][FCM_MAX_C];
    int32_t acc[FCM_O_LANES][FCM_F_TILE][FCM_T_TILE];
    int32_t b[FCM_MAX_C]; uint32_t mult[FCM_MAX_C]; int8_t lut[65536];
#pragma HLS ARRAY_PARTITION variable=x cyclic factor=FCM_T_LANES dim=3
#pragma HLS BIND_STORAGE variable=x type=ram_2p impl=bram
#pragma HLS ARRAY_PARTITION variable=w cyclic factor=FCM_O_LANES dim=2
#pragma HLS BIND_STORAGE variable=w type=ram_2p impl=bram
#pragma HLS ARRAY_PARTITION variable=acc complete dim=1
#pragma HLS ARRAY_PARTITION variable=acc cyclic factor=FCM_T_LANES dim=3
#pragma HLS BIND_STORAGE variable=acc type=ram_2p impl=lutram
#pragma HLS BIND_STORAGE variable=lut type=ram_2p impl=bram
#pragma HLS ARRAY_PARTITION variable=b cyclic factor=FCM_O_LANES
#pragma HLS ARRAY_PARTITION variable=mult cyclic factor=FCM_O_LANES
load_parameters:
    for(int o=0;o<cout;++o) {
        b[o]=bias[o]; mult[o]=multiplier[o];
load_weights:
        for(int i=0;i<cin*kernel*kernel;++i) {
#pragma HLS PIPELINE II=1
#pragma HLS LOOP_TRIPCOUNT min=1 max=288 avg=288
            w[i][o]=weights[o*cin*kernel*kernel+i];
        }
    }
    if(flags&FCM_FLAG_LUT) {
        const int size=(flags&FCM_FLAG_RESIDUAL) ? 65536 : 256;
load_lut:
        for(int k=0;k<size;++k) {
#pragma HLS PIPELINE II=1
#pragma HLS LOOP_TRIPCOUNT min=256 max=65536 avg=256
            lut[k]=post_lut[k];
        }
    }
frequency_tiles:
    for(int fb=0;fb<out_f;fb+=FCM_F_TILE) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=20 avg=10
        const int nf=(out_f-fb)<FCM_F_TILE ? out_f-fb : FCM_F_TILE;
        const int rows=(nf-1)*stride_f+kernel;
time_tiles:
        for(int tb=0;tb<frames;tb+=FCM_T_TILE) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=64 avg=10
            const int nt=(frames-tb)<FCM_T_TILE ? frames-tb : FCM_T_TILE;
load_channels:
            for(int c=0;c<cin;++c) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=32 avg=32
                for(int f=0;f<rows;++f) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=9 avg=6
                    const int fi=fb*stride_f+f-pad;
                    const int base=(c*freq+fi)*frames+tb-pad;
load_input:
                    for(int t=0;t<nt+kernel-1;++t) {
#pragma HLS PIPELINE II=1
#pragma HLS LOOP_FLATTEN off
#pragma HLS LOOP_TRIPCOUNT min=1 max=34 avg=34
                        const int ti=tb+t-pad;
                        // Out-of-image integer padding equals input_zp, i.e. centred 0.
                        x[c][f][t]=(fi<0 || fi>=freq || ti<0 || ti>=frames) ? 0 :
                            static_cast<int16_t>(static_cast<int>(input[base+t])-input_zp);
                    }
                }
            }
output_tiles:
            for(int ob=0;ob<cout;ob+=FCM_O_LANES) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=4 avg=4
                for(int f=0;f<nf;++f) {
                    for(int t=0;t<nt;++t) {
#pragma HLS PIPELINE II=1
                        for(int ol=0;ol<FCM_O_LANES;++ol) {
#pragma HLS UNROLL
                            acc[ol][f][t]=ob+ol<cout ? b[ob+ol] : 0;
                        }
                    }
                }
input_channels:
                for(int c=0;c<cin;++c) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=32 avg=32
kernel_rows:
                    for(int kf=0;kf<kernel;++kf) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=3 avg=3
kernel_columns:
                        for(int kt=0;kt<kernel;++kt) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=3 avg=3
                            const int wi=(c*kernel+kf)*kernel+kt;
                            for(int f=0;f<nf;++f) {
time_mac:
                                for(int t=0;t<nt;t+=FCM_T_LANES) {
#pragma HLS PIPELINE II=1
#pragma HLS LOOP_TRIPCOUNT min=1 max=8 avg=8
                                    for(int tl=0;tl<FCM_T_LANES;++tl) {
#pragma HLS UNROLL
                                        if(t+tl<nt) {
                                            const int16_t value=x[c][f*stride_f+kf][t+tl+kt];
                                            for(int ol=0;ol<FCM_O_LANES;++ol) {
#pragma HLS UNROLL
                                                if(ob+ol<cout) acc[ol][f][t+tl]+=value*static_cast<int32_t>(w[wi][ob+ol]);
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
store_channels:
                for(int ol=0;ol<FCM_O_LANES;++ol) {
                    if(ob+ol<cout) {
                        for(int f=0;f<nf;++f) {
                            if(flags&FCM_FLAG_DEBUG) {
store_debug:
                                for(int t=0;t<nt;++t) {
#pragma HLS PIPELINE II=1
                                    const int index=((ob+ol)*out_f+fb+f)*frames+tb+t;
                                    accumulator_out[index]=acc[ol][f][t];
                                }
                            }
store_output:
                            for(int t=0;t<nt;++t) {
#pragma HLS PIPELINE II=1
                                const int index=((ob+ol)*out_f+fb+f)*frames+tb+t;
                                const int8_t q=fcm_requantize(acc[ol][f][t],mult[ob+ol],requant_shift,output_zp);
                                int li=static_cast<int>(q)+128;
                                if(flags&FCM_FLAG_RESIDUAL) li=li*256+static_cast<int>(residual[index])+128;
                                output[index]=(flags&FCM_FLAG_LUT) ? lut[li] : q;
                            }
                        }
                    }
                }
            }
        }
    }
    return 0;
}
