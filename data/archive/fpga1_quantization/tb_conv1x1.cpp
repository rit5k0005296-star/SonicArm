#include "conv1x1.h"

#include <algorithm>
#include <climits>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

std::string join_path(const std::string& directory, const char* name) {
    return directory + "/" + name;
}

bool have_vectors(const std::string& directory) {
    std::ifstream input(join_path(directory, "input_int8.bin").c_str(),
                        std::ios::binary);
    return input.good();
}

std::string data_directory(int argc, char** argv) {
    if (argc > 2) throw std::runtime_error("Usage: tb_conv1x1 [data_directory]");
    if (argc == 2) return argv[1];
#ifdef CONV_TEST_DATA_DIR
    if (have_vectors(CONV_TEST_DATA_DIR)) return CONV_TEST_DATA_DIR;
#endif
    if (have_vectors(".")) return ".";
    const std::string source(__FILE__);
    const std::string::size_type separator = source.find_last_of("/\\");
    if (separator != std::string::npos) {
        const std::string directory = source.substr(0, separator);
        if (have_vectors(directory)) return directory;
    }
    throw std::runtime_error(
        "Test vectors not found. Pass the conv1x1 directory as a test-bench "
        "argument, or add all six .bin files as HLS test-bench data files.");
}

template <typename T>
std::vector<T> read_binary(const std::string& directory, const char* name,
                           size_t count) {
    const std::string path = join_path(directory, name);
    std::ifstream file(path.c_str(), std::ios::binary | std::ios::ate);
    if (!file) throw std::runtime_error("Cannot open " + path);
    const std::streamoff bytes = file.tellg();
    const std::streamoff expected = static_cast<std::streamoff>(count * sizeof(T));
    if (bytes != expected) {
        std::ostringstream message;
        message << "Wrong file size: " << path << ": " << bytes
                << ", expected " << expected << ". Re-export matching vectors.";
        throw std::runtime_error(message.str());
    }
    std::vector<T> values(count);
    file.seekg(0);
    file.read(reinterpret_cast<char*>(values.data()), expected);
    if (!file) throw std::runtime_error("Short read: " + path);
    return values;
}

std::vector<uint32_t> make_multipliers() {
    std::vector<uint32_t> multipliers(CONV_COUT);
    const double unit = static_cast<double>(UINT64_C(1) << CONV_REQUANT_SHIFT);
    for (int o = 0; o < CONV_COUT; ++o) {
        if (CONV_WEIGHT_ZERO_POINT[o] < -128 ||
            CONV_WEIGHT_ZERO_POINT[o] > 127) {
            throw std::runtime_error("Weight zero point is outside INT8 range");
        }
        const double scale = CONV_REQUANT_MULTIPLIER[o];
        const double integer = std::floor(scale * unit + 0.5);
        if (!std::isfinite(scale) || scale <= 0.0 || integer < 1.0 ||
            integer > static_cast<double>(std::numeric_limits<uint32_t>::max())) {
            throw std::runtime_error("Scale cannot be represented by uint32 Q40");
        }
        multipliers[o] = static_cast<uint32_t>(integer);
    }
    return multipliers;
}

// Independent FP64 golden rounding; do not call the kernel's rounding helper.
int8_t float_golden(int32_t accumulator, int channel) {
    const double scaled = static_cast<double>(accumulator) *
                          CONV_REQUANT_MULTIPLIER[channel];
    const double lower = std::floor(scaled);
    const double fraction = scaled - lower;
    int64_t rounded = static_cast<int64_t>(lower);
    if (fraction > 0.5 || (fraction == 0.5 && rounded % 2 != 0)) ++rounded;
    const int64_t quantized = rounded + CONV_OUTPUT_ZERO_POINT;
    return static_cast<int8_t>(std::max<int64_t>(-128,
                              std::min<int64_t>(127, quantized)));
}

void test_requantization() {
    // q40=2^31 means multiplier=1/512: exact positive/negative half ties.
    const uint32_t scale = UINT32_C(1) << 31;
    const int32_t inputs[] = {0, 255, 256, 257, 768, 1280,
                             -255, -256, -257, -768, -1280};
    const int expected_round[] = {0, 0, 0, 1, 2, 2, 0, 0, -1, -2, -2};
    for (size_t i = 0; i < sizeof(inputs) / sizeof(inputs[0]); ++i) {
        const int expected = std::max(-128, std::min(127,
            expected_round[i] + CONV_OUTPUT_ZERO_POINT));
        if (static_cast<int>(conv1x1_requantize(inputs[i], scale)) != expected) {
            throw std::runtime_error("Signed ties-to-even rounding test failed");
        }
    }
    if (conv1x1_requantize(INT32_MAX, UINT32_MAX) != 127 ||
        conv1x1_requantize(INT32_MIN, UINT32_MAX) != -128 ||
        conv1x1_requantize(INT32_MIN, 0) != CONV_OUTPUT_ZERO_POINT) {
        throw std::runtime_error("INT8 saturation / product boundary test failed");
    }
    std::cout << "[PASS] Signed rounding, saturation and product boundaries\n";
}

void check_reference_integrity(const std::vector<int8_t>& input,
                               const std::vector<int8_t>& weights,
                               const std::vector<int32_t>& bias,
                               const std::vector<int32_t>& reference_accum,
                               const std::vector<int8_t>& reference_output) {
    for (int o = 0; o < CONV_COUT; ++o) {
        for (int t = 0; t < CONV_T; ++t) {
            int64_t sum = bias[o];
            for (int c = 0; c < CONV_CIN; ++c) {
                const int64_t x = static_cast<int64_t>(input[c * CONV_T + t]) -
                                  CONV_INPUT_ZERO_POINT;
                const int64_t w = static_cast<int64_t>(weights[o * CONV_CIN + c]) -
                                  CONV_WEIGHT_ZERO_POINT[o];
                sum += x * w;
                // Prevent signed overflow in the kernel's INT32 partial sums.
                if (sum < INT32_MIN || sum > INT32_MAX) {
                    throw std::runtime_error("INT32 accumulation would overflow");
                }
            }
            const int index = o * CONV_T + t;
            if (sum != reference_accum[index] ||
                float_golden(static_cast<int32_t>(sum), o) != reference_output[index]) {
                throw std::runtime_error("Reference data / layer_params.h mismatch");
            }
        }
    }
    std::cout << "[PASS] Reference files match independent INT64 MAC / FP64 golden\n";
}

void compare_outputs(const std::vector<int32_t>& actual_accum,
                     const std::vector<int8_t>& actual_output,
                     const std::vector<int32_t>& reference_accum,
                     const std::vector<int8_t>& reference_output,
                     const std::vector<int8_t>& onnx_output) {
    size_t accum_errors = 0, reference_errors = 0, onnx_errors = 0;
    int max_reference_lsb = 0, max_onnx_lsb = 0;
    for (size_t i = 0; i < actual_output.size(); ++i) {
        if (actual_accum[i] != reference_accum[i]) ++accum_errors;
        const int reference_lsb = std::abs(static_cast<int>(actual_output[i]) -
                                           static_cast<int>(reference_output[i]));
        const int onnx_lsb = std::abs(static_cast<int>(actual_output[i]) -
                                      static_cast<int>(onnx_output[i]));
        reference_errors += reference_lsb != 0;
        onnx_errors += onnx_lsb != 0;
        max_reference_lsb = std::max(max_reference_lsb, reference_lsb);
        max_onnx_lsb = std::max(max_onnx_lsb, onnx_lsb);
        if ((actual_accum[i] != reference_accum[i] || reference_lsb != 0) &&
            accum_errors + reference_errors <= 8) {
            std::cerr << "Mismatch c=" << i / CONV_T << " t=" << i % CONV_T
                      << " accum=" << actual_accum[i] << '/' << reference_accum[i]
                      << " output=" << static_cast<int>(actual_output[i]) << '/'
                      << static_cast<int>(reference_output[i]) << '\n';
        }
    }
    std::cout << "[COMPARE] " << actual_output.size() << " elements; INT32 mismatches="
              << accum_errors << "; INT8 golden mismatches=" << reference_errors
              << "; max golden LSB=" << max_reference_lsb
              << "; ONNX mismatches=" << onnx_errors
              << "; max ONNX LSB=" << max_onnx_lsb << '\n';
    // Exact extracted integer golden is mandatory. Q40 is a hardware approximation
    // to FP64 scaling; new data near a rounding boundary can expose a 1-LSB error.
    // Fail visibly in that case instead of silently weakening the golden criterion.
    if (accum_errors || reference_errors ||
        max_onnx_lsb > CONV_REFERENCE_ONNX_MAX_LSB) {
        throw std::runtime_error("Kernel output does not meet reference criteria");
    }
}

void test_synthetic_mac(const std::vector<uint32_t>& multipliers) {
    // Exercise INT8 endpoints and repeat calls, including a partial frame block.
    std::vector<int8_t> input(CONV_INPUT_ELEMENTS, static_cast<int8_t>(-128));
    std::vector<int8_t> weights(CONV_WEIGHT_ELEMENTS, static_cast<int8_t>(-128));
    std::vector<int32_t> bias(CONV_COUT), actual_accum(CONV_OUTPUT_ELEMENTS);
    std::vector<int8_t> actual_output(CONV_OUTPUT_ELEMENTS);
    for (int c = 0; c < CONV_CIN; ++c) {
        for (int t = 0; t < CONV_T; ++t) {
            input[c * CONV_T + t] = static_cast<int8_t>((c + t) % 2 ? 127 : -128);
        }
    }
    for (int o = 0; o < CONV_COUT; ++o) {
        bias[o] = o * 17 - 1000;
        for (int c = 0; c < CONV_CIN; ++c) {
            weights[o * CONV_CIN + c] = static_cast<int8_t>((o + c) % 2 ? 127 : -128);
        }
    }
    conv1x1(input.data(), weights.data(), bias.data(), multipliers.data(),
            actual_output.data(), actual_accum.data());
    for (int o = 0; o < CONV_COUT; ++o) {
        for (int t = 0; t < CONV_T; ++t) {
            int64_t sum = bias[o];
            for (int c = 0; c < CONV_CIN; ++c) {
                sum += (static_cast<int64_t>(input[c * CONV_T + t]) - CONV_INPUT_ZERO_POINT) *
                       (static_cast<int64_t>(weights[o * CONV_CIN + c]) - CONV_WEIGHT_ZERO_POINT[o]);
            }
            const int index = o * CONV_T + t;
            if (sum < INT32_MIN || sum > INT32_MAX || actual_accum[index] != sum ||
                actual_output[index] != float_golden(static_cast<int32_t>(sum), o)) {
                throw std::runtime_error("Synthetic endpoint MAC / output test failed");
            }
        }
    }
    std::cout << "[PASS] Repeated call / INT8 endpoints / final frame lanes\n";
}

} // namespace

int main(int argc, char** argv) {
    try {
        static_assert(CHAR_BIT == 8 && sizeof(int32_t) == 4, "Unexpected host types");
        const uint16_t endian = 1;
        if (*reinterpret_cast<const unsigned char*>(&endian) != 1) {
            throw std::runtime_error("Raw .bin vectors require a little-endian host");
        }
        test_requantization();
        const std::string directory = data_directory(argc, argv);
        std::cout << "[DATA] " << directory << "\n[LAYER] " << CONV_NODE
                  << "\n[SHAPE] X=[1," << CONV_CIN << ',' << CONV_T << "] W=["
                  << CONV_COUT << ',' << CONV_CIN << ",1]\n";
        const std::vector<int8_t> input = read_binary<int8_t>(directory, "input_int8.bin", CONV_INPUT_ELEMENTS);
        const std::vector<int8_t> weights = read_binary<int8_t>(directory, "weights_int8.bin", CONV_WEIGHT_ELEMENTS);
        const std::vector<int32_t> bias = read_binary<int32_t>(directory, "bias_int32.bin", CONV_COUT);
        const std::vector<int32_t> reference_accum = read_binary<int32_t>(directory, "reference_accum_int32.bin", CONV_OUTPUT_ELEMENTS);
        const std::vector<int8_t> reference_output = read_binary<int8_t>(directory, "reference_output_int8.bin", CONV_OUTPUT_ELEMENTS);
        const std::vector<int8_t> onnx_output = read_binary<int8_t>(directory, "onnx_output_int8.bin", CONV_OUTPUT_ELEMENTS);
        const std::vector<uint32_t> multipliers = make_multipliers();
        check_reference_integrity(input, weights, bias, reference_accum, reference_output);
        std::vector<int8_t> output(CONV_OUTPUT_ELEMENTS);
        std::vector<int32_t> accumulators(CONV_OUTPUT_ELEMENTS);
        conv1x1(input.data(), weights.data(), bias.data(), multipliers.data(),
                output.data(), accumulators.data());
        compare_outputs(accumulators, output, reference_accum, reference_output, onnx_output);
        test_synthetic_mac(multipliers);
        std::cout << "PASS: conv1x1 test bench\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << '\n';
        return 1;
    }
}
