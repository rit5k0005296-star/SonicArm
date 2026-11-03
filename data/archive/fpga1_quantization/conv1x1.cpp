#include "conv1x1.h"

extern "C" void conv1x1(
    const int8_t input[CONV_INPUT_ELEMENTS],
    const int8_t weights[CONV_WEIGHT_ELEMENTS],
    const int32_t bias[CONV_COUT],
    const uint32_t requant_q40[CONV_COUT],
    int8_t output[CONV_OUTPUT_ELEMENTS],
    int32_t accumulator_out[CONV_OUTPUT_ELEMENTS]) {
#pragma HLS INTERFACE mode=m_axi port=input offset=slave bundle=gmem_input depth=CONV_INPUT_ELEMENTS
#pragma HLS INTERFACE mode=m_axi port=weights offset=slave bundle=gmem_params depth=CONV_WEIGHT_ELEMENTS
#pragma HLS INTERFACE mode=m_axi port=bias offset=slave bundle=gmem_params depth=CONV_COUT
#pragma HLS INTERFACE mode=m_axi port=requant_q40 offset=slave bundle=gmem_params depth=CONV_COUT
#pragma HLS INTERFACE mode=m_axi port=output offset=slave bundle=gmem_output depth=CONV_OUTPUT_ELEMENTS
#pragma HLS INTERFACE mode=m_axi port=accumulator_out offset=slave bundle=gmem_output depth=CONV_OUTPUT_ELEMENTS
#pragma HLS INTERFACE mode=s_axilite port=input bundle=control
#pragma HLS INTERFACE mode=s_axilite port=weights bundle=control
#pragma HLS INTERFACE mode=s_axilite port=bias bundle=control
#pragma HLS INTERFACE mode=s_axilite port=requant_q40 bundle=control
#pragma HLS INTERFACE mode=s_axilite port=output bundle=control
#pragma HLS INTERFACE mode=s_axilite port=accumulator_out bundle=control
#pragma HLS INTERFACE mode=s_axilite port=return bundle=control

    // Widen BEFORE zero-point subtraction: INT8 - (-128) can reach 255.
    // Cache the input once; reuse it across every output channel.
    int16_t centered_input[CONV_CIN][CONV_T];
    int16_t weight_row[CONV_CIN];
    int32_t accumulators[CONV_T];
#pragma HLS ARRAY_PARTITION variable=centered_input cyclic factor=CONV_FRAME_LANES dim=2
#pragma HLS BIND_STORAGE variable=centered_input type=ram_2p impl=bram
#pragma HLS ARRAY_PARTITION variable=accumulators cyclic factor=CONV_FRAME_LANES dim=1

load_input_channels:
    for (int c = 0; c < CONV_CIN; ++c) {
load_input_frames:
        for (int t = 0; t < CONV_T; ++t) {
#pragma HLS PIPELINE II=1
            centered_input[c][t] = static_cast<int16_t>(
                static_cast<int32_t>(input[c * CONV_T + t]) -
                CONV_INPUT_ZERO_POINT);
        }
    }

output_channels:
    for (int o = 0; o < CONV_COUT; ++o) {
        const int32_t channel_bias = bias[o];
        const uint32_t channel_multiplier = requant_q40[o];
load_weight_row:
        for (int c = 0; c < CONV_CIN; ++c) {
#pragma HLS PIPELINE II=1
            weight_row[c] = static_cast<int16_t>(
                static_cast<int32_t>(weights[o * CONV_CIN + c]) -
                CONV_WEIGHT_ZERO_POINT[o]);
        }
initialize_accumulators:
        for (int t = 0; t < CONV_T; ++t) {
#pragma HLS PIPELINE II=1
            accumulators[t] = channel_bias;
        }
input_channels:
        for (int c = 0; c < CONV_CIN; ++c) {
            const int16_t channel_weight = weight_row[c];
frame_blocks:
            for (int t = 0; t < CONV_T; t += CONV_FRAME_LANES) {
#pragma HLS PIPELINE II=1
frame_lanes:
                for (int lane = 0; lane < CONV_FRAME_LANES; ++lane) {
#pragma HLS UNROLL
                    const int frame = t + lane;
                    // CONV_T=150: the last block has only two valid lanes.
                    if (frame < CONV_T) {
                        const int32_t product =
                            static_cast<int32_t>(centered_input[c][frame]) *
                            static_cast<int32_t>(channel_weight);
                        accumulators[frame] += product;
                    }
                }
            }
        }
store_outputs:
        for (int t = 0; t < CONV_T; ++t) {
#pragma HLS PIPELINE II=1
            const int index = o * CONV_T + t;
            const int32_t accumulator = accumulators[t];
            accumulator_out[index] = accumulator;
            output[index] = conv1x1_requantize(accumulator, channel_multiplier);
        }
    }
}
