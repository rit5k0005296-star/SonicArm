#include "conv_relu.h"

extern "C" void conv_relu(const int8_t input[CR_INPUT_ELEMENTS],
                          const int8_t weights[CR_WEIGHT_ELEMENTS],
                          const int32_t bias[CONV_COUT],
                          const uint32_t requant_q40[CONV_COUT],
                          const int8_t post_lut[256],
                          int8_t output[CR_OUTPUT_ELEMENTS],
                          int32_t accumulator_out[CR_OUTPUT_ELEMENTS]) {
#pragma HLS INTERFACE mode=m_axi port=input offset=slave bundle=gmem_input depth=CR_INPUT_ELEMENTS
#pragma HLS INTERFACE mode=m_axi port=weights offset=slave bundle=gmem_params depth=CR_WEIGHT_ELEMENTS
#pragma HLS INTERFACE mode=m_axi port=bias offset=slave bundle=gmem_params depth=CONV_COUT
#pragma HLS INTERFACE mode=m_axi port=requant_q40 offset=slave bundle=gmem_params depth=CONV_COUT
#pragma HLS INTERFACE mode=m_axi port=post_lut offset=slave bundle=gmem_params depth=256
#pragma HLS INTERFACE mode=m_axi port=output offset=slave bundle=gmem_output depth=CR_OUTPUT_ELEMENTS
#pragma HLS INTERFACE mode=m_axi port=accumulator_out offset=slave bundle=gmem_output depth=CR_OUTPUT_ELEMENTS
#pragma HLS INTERFACE mode=s_axilite port=input bundle=control
#pragma HLS INTERFACE mode=s_axilite port=weights bundle=control
#pragma HLS INTERFACE mode=s_axilite port=bias bundle=control
#pragma HLS INTERFACE mode=s_axilite port=requant_q40 bundle=control
#pragma HLS INTERFACE mode=s_axilite port=post_lut bundle=control
#pragma HLS INTERFACE mode=s_axilite port=output bundle=control
#pragma HLS INTERFACE mode=s_axilite port=accumulator_out bundle=control
#pragma HLS INTERFACE mode=s_axilite port=return bundle=control

    int16_t x[CONV_CIN][CONV_T];
    int8_t w[CR_OUTPUT_LANES][CONV_CIN];
    int32_t acc[CR_OUTPUT_LANES][CONV_T];
    int32_t tile_bias[CR_OUTPUT_LANES];
    uint32_t tile_q40[CR_OUTPUT_LANES];
    int8_t lut[256];
#pragma HLS ARRAY_PARTITION variable=x cyclic factor=CR_FRAME_LANES dim=2
#pragma HLS BIND_STORAGE variable=x type=ram_2p impl=bram
#pragma HLS ARRAY_PARTITION variable=w complete dim=1
#pragma HLS ARRAY_PARTITION variable=acc complete dim=1
#pragma HLS ARRAY_PARTITION variable=acc cyclic factor=CR_FRAME_LANES dim=2
#pragma HLS ARRAY_PARTITION variable=tile_bias complete
#pragma HLS ARRAY_PARTITION variable=tile_q40 complete

load_lut:
    for (int k = 0; k < 256; ++k) {
#pragma HLS PIPELINE II=1
        lut[k] = post_lut[k];
    }
load_input_channels:
    for (int c = 0; c < CONV_CIN; ++c) {
load_input_frames:
        for (int t = 0; t < CONV_T; ++t) {
#pragma HLS PIPELINE II=1
            x[c][t] = static_cast<int16_t>(static_cast<int32_t>(input[c * CONV_T + t])
                                         - CONV_INPUT_ZERO_POINT);
        }
    }
output_tiles:
    for (int ob = 0; ob < CONV_COUT; ob += CR_OUTPUT_LANES) {
load_parameter_channels:
        for (int ol = 0; ol < CR_OUTPUT_LANES; ++ol) {
            tile_bias[ol] = bias[ob + ol];
            tile_q40[ol] = requant_q40[ob + ol];
load_weight_row:
            for (int c = 0; c < CONV_CIN; ++c) {
#pragma HLS PIPELINE II=1
                w[ol][c] = weights[(ob + ol) * CONV_CIN + c];
            }
        }
initialize_frames:
        for (int t = 0; t < CONV_T; ++t) {
#pragma HLS PIPELINE II=1
initialize_channels:
            for (int ol = 0; ol < CR_OUTPUT_LANES; ++ol) {
#pragma HLS UNROLL
                acc[ol][t] = tile_bias[ol];
            }
        }
input_channels:
        for (int c = 0; c < CONV_CIN; ++c) {
frame_blocks:
            for (int t = 0; t < CONV_T; t += CR_FRAME_LANES) {
#pragma HLS PIPELINE II=1
frame_lanes:
                for (int fl = 0; fl < CR_FRAME_LANES; ++fl) {
#pragma HLS UNROLL
                    if (t + fl < CONV_T) {
                        const int32_t value = x[c][t + fl];
output_lanes:
                        for (int ol = 0; ol < CR_OUTPUT_LANES; ++ol) {
#pragma HLS UNROLL
                            acc[ol][t + fl] += value * static_cast<int32_t>(w[ol][c]);
                        }
                    }
                }
            }
        }
        // Separate contiguous writes avoid mixing INT32/INT8 stores in one loop.
store_debug_channels:
        for (int ol = 0; ol < CR_OUTPUT_LANES; ++ol) {
store_debug_frames:
            for (int t = 0; t < CONV_T; ++t) {
#pragma HLS PIPELINE II=1
                accumulator_out[(ob + ol) * CONV_T + t] = acc[ol][t];
            }
        }
store_output_channels:
        for (int ol = 0; ol < CR_OUTPUT_LANES; ++ol) {
store_output_frames:
            for (int t = 0; t < CONV_T; ++t) {
#pragma HLS PIPELINE II=1
                const int8_t q1 = conv_relu_requantize(acc[ol][t], tile_q40[ol]);
                output[(ob + ol) * CONV_T + t] = lut[static_cast<int>(q1) + 128];
            }
        }
    }
}
