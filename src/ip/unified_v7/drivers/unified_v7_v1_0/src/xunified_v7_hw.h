// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2025.2 (64-bit)
// Tool Version Limit: 2025.11
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2025 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================
// control
// 0x00 : Control signals
//        bit 0  - ap_start (Read/Write/COH)
//        bit 1  - ap_done (Read/COR)
//        bit 2  - ap_idle (Read)
//        bit 3  - ap_ready (Read/COR)
//        bit 7  - auto_restart (Read/Write)
//        bit 9  - interrupt (Read)
//        others - reserved
// 0x04 : Global Interrupt Enable Register
//        bit 0  - Global Interrupt Enable (Read/Write)
//        others - reserved
// 0x08 : IP Interrupt Enable Register (Read/Write)
//        bit 0 - enable ap_done interrupt (Read/Write)
//        bit 1 - enable ap_ready interrupt (Read/Write)
//        others - reserved
// 0x0c : IP Interrupt Status Register (Read/TOW)
//        bit 0 - ap_done (Read/TOW)
//        bit 1 - ap_ready (Read/TOW)
//        others - reserved
// 0x10 : Data signal of ap_return
//        bit 31~0 - ap_return[31:0] (Read)
// 0x18 : Data signal of input_r
//        bit 31~0 - input_r[31:0] (Read/Write)
// 0x1c : Data signal of input_r
//        bit 31~0 - input_r[63:32] (Read/Write)
// 0x20 : reserved
// 0x24 : Data signal of weights
//        bit 31~0 - weights[31:0] (Read/Write)
// 0x28 : Data signal of weights
//        bit 31~0 - weights[63:32] (Read/Write)
// 0x2c : reserved
// 0x30 : Data signal of bias
//        bit 31~0 - bias[31:0] (Read/Write)
// 0x34 : Data signal of bias
//        bit 31~0 - bias[63:32] (Read/Write)
// 0x38 : reserved
// 0x3c : Data signal of multiplier
//        bit 31~0 - multiplier[31:0] (Read/Write)
// 0x40 : Data signal of multiplier
//        bit 31~0 - multiplier[63:32] (Read/Write)
// 0x44 : reserved
// 0x48 : Data signal of post_lut
//        bit 31~0 - post_lut[31:0] (Read/Write)
// 0x4c : Data signal of post_lut
//        bit 31~0 - post_lut[63:32] (Read/Write)
// 0x50 : reserved
// 0x54 : Data signal of residual
//        bit 31~0 - residual[31:0] (Read/Write)
// 0x58 : Data signal of residual
//        bit 31~0 - residual[63:32] (Read/Write)
// 0x5c : reserved
// 0x60 : Data signal of output_r
//        bit 31~0 - output_r[31:0] (Read/Write)
// 0x64 : Data signal of output_r
//        bit 31~0 - output_r[63:32] (Read/Write)
// 0x68 : reserved
// 0x6c : Data signal of accumulator_out
//        bit 31~0 - accumulator_out[31:0] (Read/Write)
// 0x70 : Data signal of accumulator_out
//        bit 31~0 - accumulator_out[63:32] (Read/Write)
// 0x74 : reserved
// 0x78 : Data signal of mode
//        bit 31~0 - mode[31:0] (Read/Write)
// 0x7c : reserved
// 0x80 : Data signal of cin
//        bit 31~0 - cin[31:0] (Read/Write)
// 0x84 : reserved
// 0x88 : Data signal of cout
//        bit 31~0 - cout[31:0] (Read/Write)
// 0x8c : reserved
// 0x90 : Data signal of freq
//        bit 31~0 - freq[31:0] (Read/Write)
// 0x94 : reserved
// 0x98 : Data signal of frames
//        bit 31~0 - frames[31:0] (Read/Write)
// 0x9c : reserved
// 0xa0 : Data signal of kernel
//        bit 31~0 - kernel[31:0] (Read/Write)
// 0xa4 : reserved
// 0xa8 : Data signal of stride_f
//        bit 31~0 - stride_f[31:0] (Read/Write)
// 0xac : reserved
// 0xb0 : Data signal of input_zp
//        bit 31~0 - input_zp[31:0] (Read/Write)
// 0xb4 : reserved
// 0xb8 : Data signal of output_zp
//        bit 31~0 - output_zp[31:0] (Read/Write)
// 0xbc : reserved
// 0xc0 : Data signal of requant_shift
//        bit 31~0 - requant_shift[31:0] (Read/Write)
// 0xc4 : reserved
// 0xc8 : Data signal of flags
//        bit 31~0 - flags[31:0] (Read/Write)
// 0xcc : reserved
// (SC = Self Clear, COR = Clear on Read, TOW = Toggle on Write, COH = Clear on Handshake)

#define XUNIFIED_V7_CONTROL_ADDR_AP_CTRL              0x00
#define XUNIFIED_V7_CONTROL_ADDR_GIE                  0x04
#define XUNIFIED_V7_CONTROL_ADDR_IER                  0x08
#define XUNIFIED_V7_CONTROL_ADDR_ISR                  0x0c
#define XUNIFIED_V7_CONTROL_ADDR_AP_RETURN            0x10
#define XUNIFIED_V7_CONTROL_BITS_AP_RETURN            32
#define XUNIFIED_V7_CONTROL_ADDR_INPUT_R_DATA         0x18
#define XUNIFIED_V7_CONTROL_BITS_INPUT_R_DATA         64
#define XUNIFIED_V7_CONTROL_ADDR_WEIGHTS_DATA         0x24
#define XUNIFIED_V7_CONTROL_BITS_WEIGHTS_DATA         64
#define XUNIFIED_V7_CONTROL_ADDR_BIAS_DATA            0x30
#define XUNIFIED_V7_CONTROL_BITS_BIAS_DATA            64
#define XUNIFIED_V7_CONTROL_ADDR_MULTIPLIER_DATA      0x3c
#define XUNIFIED_V7_CONTROL_BITS_MULTIPLIER_DATA      64
#define XUNIFIED_V7_CONTROL_ADDR_POST_LUT_DATA        0x48
#define XUNIFIED_V7_CONTROL_BITS_POST_LUT_DATA        64
#define XUNIFIED_V7_CONTROL_ADDR_RESIDUAL_DATA        0x54
#define XUNIFIED_V7_CONTROL_BITS_RESIDUAL_DATA        64
#define XUNIFIED_V7_CONTROL_ADDR_OUTPUT_R_DATA        0x60
#define XUNIFIED_V7_CONTROL_BITS_OUTPUT_R_DATA        64
#define XUNIFIED_V7_CONTROL_ADDR_ACCUMULATOR_OUT_DATA 0x6c
#define XUNIFIED_V7_CONTROL_BITS_ACCUMULATOR_OUT_DATA 64
#define XUNIFIED_V7_CONTROL_ADDR_MODE_DATA            0x78
#define XUNIFIED_V7_CONTROL_BITS_MODE_DATA            32
#define XUNIFIED_V7_CONTROL_ADDR_CIN_DATA             0x80
#define XUNIFIED_V7_CONTROL_BITS_CIN_DATA             32
#define XUNIFIED_V7_CONTROL_ADDR_COUT_DATA            0x88
#define XUNIFIED_V7_CONTROL_BITS_COUT_DATA            32
#define XUNIFIED_V7_CONTROL_ADDR_FREQ_DATA            0x90
#define XUNIFIED_V7_CONTROL_BITS_FREQ_DATA            32
#define XUNIFIED_V7_CONTROL_ADDR_FRAMES_DATA          0x98
#define XUNIFIED_V7_CONTROL_BITS_FRAMES_DATA          32
#define XUNIFIED_V7_CONTROL_ADDR_KERNEL_DATA          0xa0
#define XUNIFIED_V7_CONTROL_BITS_KERNEL_DATA          32
#define XUNIFIED_V7_CONTROL_ADDR_STRIDE_F_DATA        0xa8
#define XUNIFIED_V7_CONTROL_BITS_STRIDE_F_DATA        32
#define XUNIFIED_V7_CONTROL_ADDR_INPUT_ZP_DATA        0xb0
#define XUNIFIED_V7_CONTROL_BITS_INPUT_ZP_DATA        32
#define XUNIFIED_V7_CONTROL_ADDR_OUTPUT_ZP_DATA       0xb8
#define XUNIFIED_V7_CONTROL_BITS_OUTPUT_ZP_DATA       32
#define XUNIFIED_V7_CONTROL_ADDR_REQUANT_SHIFT_DATA   0xc0
#define XUNIFIED_V7_CONTROL_BITS_REQUANT_SHIFT_DATA   32
#define XUNIFIED_V7_CONTROL_ADDR_FLAGS_DATA           0xc8
#define XUNIFIED_V7_CONTROL_BITS_FLAGS_DATA           32

