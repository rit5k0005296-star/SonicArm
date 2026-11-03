#include "pointwise.h"

extern "C" int pointwise(const int8_t* input, const int8_t* weights, const int32_t* bias,
                         const uint32_t* multiplier, const int8_t* post_lut,
                         int8_t* output, int32_t* accumulator_out,
                         int cin, int cout, int frames, int input_zp, int output_zp,
                         int requant_shift, int flags) {
#pragma HLS INTERFACE mode=m_axi port=input offset=slave bundle=gmem_input depth=32768
#pragma HLS INTERFACE mode=m_axi port=weights offset=slave bundle=gmem_params depth=524288
#pragma HLS INTERFACE mode=m_axi port=bias offset=slave bundle=gmem_params depth=512
#pragma HLS INTERFACE mode=m_axi port=multiplier offset=slave bundle=gmem_params depth=512
#pragma HLS INTERFACE mode=m_axi port=post_lut offset=slave bundle=gmem_params depth=256
#pragma HLS INTERFACE mode=m_axi port=output offset=slave bundle=gmem_output depth=32768
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
    if (cin<1 || cin>PW_MAX_CIN || cout<1 || cout>PW_MAX_COUT || frames<1 || frames>PW_MAX_FRAMES ||
        input_zp < -128 || input_zp>127 || output_zp < -128 || output_zp>127 ||
        requant_shift<8 || requant_shift>40 || flags<0 || flags>3) return -1;

    int16_t x[PW_MAX_CIN][PW_TIME_TILE];
    int8_t w[PW_OUTPUT_LANES][PW_MAX_CIN];
    int32_t acc[PW_OUTPUT_LANES][PW_TIME_TILE];
    int32_t b[PW_OUTPUT_LANES];
    uint32_t mult[PW_OUTPUT_LANES];
    int8_t lut[256];
#pragma HLS ARRAY_PARTITION variable=x cyclic factor=PW_FRAME_LANES dim=2
#pragma HLS BIND_STORAGE variable=x type=ram_2p impl=bram
#pragma HLS ARRAY_PARTITION variable=w complete dim=1
#pragma HLS ARRAY_PARTITION variable=acc complete dim=1
#pragma HLS ARRAY_PARTITION variable=acc cyclic factor=PW_FRAME_LANES dim=2
#pragma HLS BIND_STORAGE variable=acc type=ram_2p impl=lutram
#pragma HLS ARRAY_PARTITION variable=b complete
#pragma HLS ARRAY_PARTITION variable=mult complete
    if (flags&PW_FLAG_POST_LUT) {
load_lut:
        for (int k=0;k<256;++k) {
#pragma HLS PIPELINE II=1
            lut[k]=post_lut[k];
        }
    }
time_tiles:
    for (int tb=0;tb<frames;tb+=PW_TIME_TILE) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=32 avg=3
        const int valid=(frames-tb)<PW_TIME_TILE ? frames-tb : PW_TIME_TILE;
load_channels:
        for (int c=0;c<cin;++c) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=1024 avg=512
load_frames:
            for (int t=0;t<valid;++t) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=64 avg=50
#pragma HLS PIPELINE II=1
                x[c][t]=static_cast<int16_t>(static_cast<int32_t>(input[c*frames+tb+t])-input_zp);
            }
        }
output_tiles:
        for (int ob=0;ob<cout;ob+=PW_OUTPUT_LANES) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=64 avg=16
load_parameter_rows:
            for (int ol=0;ol<PW_OUTPUT_LANES;++ol) {
                const bool active=ob+ol<cout;
                b[ol]=active ? bias[ob+ol] : 0;
                mult[ol]=active ? multiplier[ob+ol] : 0;
load_weights:
                for (int c=0;c<cin;++c) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=1024 avg=512
#pragma HLS PIPELINE II=1
                    w[ol][c]=active ? weights[(ob+ol)*cin+c] : 0;
                }
            }
initialize_frames:
            for (int t=0;t<valid;++t) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=64 avg=50
#pragma HLS PIPELINE II=1
                for (int ol=0;ol<PW_OUTPUT_LANES;++ol) {
#pragma HLS UNROLL
                    acc[ol][t]=b[ol];
                }
            }
input_channels:
            for (int c=0;c<cin;++c) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=1024 avg=512
frame_blocks:
                for (int t=0;t<valid;t+=PW_FRAME_LANES) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=16 avg=13
#pragma HLS PIPELINE II=1
                    for (int fl=0;fl<PW_FRAME_LANES;++fl) {
#pragma HLS UNROLL
                        if (t+fl<valid) {
                            const int32_t value=x[c][t+fl];
                            for (int ol=0;ol<PW_OUTPUT_LANES;++ol) {
#pragma HLS UNROLL
                                acc[ol][t+fl]+=value*static_cast<int32_t>(w[ol][c]);
                            }
                        }
                    }
                }
            }
store_channels:
            for (int ol=0;ol<PW_OUTPUT_LANES;++ol) {
                if (ob+ol<cout) {
                    if (flags&PW_FLAG_DEBUG) {
store_debug:
                        for (int t=0;t<valid;++t) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=64 avg=50
#pragma HLS PIPELINE II=1
                            accumulator_out[(ob+ol)*frames+tb+t]=acc[ol][t];
                        }
                    }
store_output:
                    for (int t=0;t<valid;++t) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=64 avg=50
#pragma HLS PIPELINE II=1
                        const int8_t q=pw_requantize(acc[ol][t],mult[ol],requant_shift,output_zp);
                        output[(ob+ol)*frames+tb+t]=(flags&PW_FLAG_POST_LUT) ? lut[static_cast<int>(q)+128] : q;
                    }
                }
            }
        }
    }
    return 0;
}
