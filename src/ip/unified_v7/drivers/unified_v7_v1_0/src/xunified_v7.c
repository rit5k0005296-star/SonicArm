// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2025.2 (64-bit)
// Tool Version Limit: 2025.11
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2025 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================
/***************************** Include Files *********************************/
#include "xunified_v7.h"

/************************** Function Implementation *************************/
#ifndef __linux__
int XUnified_v7_CfgInitialize(XUnified_v7 *InstancePtr, XUnified_v7_Config *ConfigPtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(ConfigPtr != NULL);

    InstancePtr->Control_BaseAddress = ConfigPtr->Control_BaseAddress;
    InstancePtr->IsReady = XIL_COMPONENT_IS_READY;

    return XST_SUCCESS;
}
#endif

void XUnified_v7_Start(XUnified_v7 *InstancePtr) {
    u32 Data;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_AP_CTRL) & 0x80;
    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_AP_CTRL, Data | 0x01);
}

u32 XUnified_v7_IsDone(XUnified_v7 *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_AP_CTRL);
    return (Data >> 1) & 0x1;
}

u32 XUnified_v7_IsIdle(XUnified_v7 *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_AP_CTRL);
    return (Data >> 2) & 0x1;
}

u32 XUnified_v7_IsReady(XUnified_v7 *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_AP_CTRL);
    // check ap_start to see if the pcore is ready for next input
    return !(Data & 0x1);
}

void XUnified_v7_EnableAutoRestart(XUnified_v7 *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_AP_CTRL, 0x80);
}

void XUnified_v7_DisableAutoRestart(XUnified_v7 *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_AP_CTRL, 0);
}

u32 XUnified_v7_Get_return(XUnified_v7 *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_AP_RETURN);
    return Data;
}
void XUnified_v7_Set_input_r(XUnified_v7 *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_INPUT_R_DATA, (u32)(Data));
    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_INPUT_R_DATA + 4, (u32)(Data >> 32));
}

u64 XUnified_v7_Get_input_r(XUnified_v7 *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_INPUT_R_DATA);
    Data += (u64)XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_INPUT_R_DATA + 4) << 32;
    return Data;
}

void XUnified_v7_Set_weights(XUnified_v7 *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_WEIGHTS_DATA, (u32)(Data));
    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_WEIGHTS_DATA + 4, (u32)(Data >> 32));
}

u64 XUnified_v7_Get_weights(XUnified_v7 *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_WEIGHTS_DATA);
    Data += (u64)XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_WEIGHTS_DATA + 4) << 32;
    return Data;
}

void XUnified_v7_Set_bias(XUnified_v7 *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_BIAS_DATA, (u32)(Data));
    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_BIAS_DATA + 4, (u32)(Data >> 32));
}

u64 XUnified_v7_Get_bias(XUnified_v7 *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_BIAS_DATA);
    Data += (u64)XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_BIAS_DATA + 4) << 32;
    return Data;
}

void XUnified_v7_Set_multiplier(XUnified_v7 *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_MULTIPLIER_DATA, (u32)(Data));
    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_MULTIPLIER_DATA + 4, (u32)(Data >> 32));
}

u64 XUnified_v7_Get_multiplier(XUnified_v7 *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_MULTIPLIER_DATA);
    Data += (u64)XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_MULTIPLIER_DATA + 4) << 32;
    return Data;
}

void XUnified_v7_Set_post_lut(XUnified_v7 *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_POST_LUT_DATA, (u32)(Data));
    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_POST_LUT_DATA + 4, (u32)(Data >> 32));
}

u64 XUnified_v7_Get_post_lut(XUnified_v7 *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_POST_LUT_DATA);
    Data += (u64)XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_POST_LUT_DATA + 4) << 32;
    return Data;
}

void XUnified_v7_Set_residual(XUnified_v7 *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_RESIDUAL_DATA, (u32)(Data));
    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_RESIDUAL_DATA + 4, (u32)(Data >> 32));
}

u64 XUnified_v7_Get_residual(XUnified_v7 *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_RESIDUAL_DATA);
    Data += (u64)XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_RESIDUAL_DATA + 4) << 32;
    return Data;
}

void XUnified_v7_Set_output_r(XUnified_v7 *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_OUTPUT_R_DATA, (u32)(Data));
    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_OUTPUT_R_DATA + 4, (u32)(Data >> 32));
}

u64 XUnified_v7_Get_output_r(XUnified_v7 *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_OUTPUT_R_DATA);
    Data += (u64)XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_OUTPUT_R_DATA + 4) << 32;
    return Data;
}

void XUnified_v7_Set_accumulator_out(XUnified_v7 *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_ACCUMULATOR_OUT_DATA, (u32)(Data));
    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_ACCUMULATOR_OUT_DATA + 4, (u32)(Data >> 32));
}

u64 XUnified_v7_Get_accumulator_out(XUnified_v7 *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_ACCUMULATOR_OUT_DATA);
    Data += (u64)XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_ACCUMULATOR_OUT_DATA + 4) << 32;
    return Data;
}

void XUnified_v7_Set_mode(XUnified_v7 *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_MODE_DATA, Data);
}

u32 XUnified_v7_Get_mode(XUnified_v7 *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_MODE_DATA);
    return Data;
}

void XUnified_v7_Set_cin(XUnified_v7 *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_CIN_DATA, Data);
}

u32 XUnified_v7_Get_cin(XUnified_v7 *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_CIN_DATA);
    return Data;
}

void XUnified_v7_Set_cout(XUnified_v7 *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_COUT_DATA, Data);
}

u32 XUnified_v7_Get_cout(XUnified_v7 *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_COUT_DATA);
    return Data;
}

void XUnified_v7_Set_freq(XUnified_v7 *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_FREQ_DATA, Data);
}

u32 XUnified_v7_Get_freq(XUnified_v7 *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_FREQ_DATA);
    return Data;
}

void XUnified_v7_Set_frames(XUnified_v7 *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_FRAMES_DATA, Data);
}

u32 XUnified_v7_Get_frames(XUnified_v7 *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_FRAMES_DATA);
    return Data;
}

void XUnified_v7_Set_kernel(XUnified_v7 *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_KERNEL_DATA, Data);
}

u32 XUnified_v7_Get_kernel(XUnified_v7 *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_KERNEL_DATA);
    return Data;
}

void XUnified_v7_Set_stride_f(XUnified_v7 *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_STRIDE_F_DATA, Data);
}

u32 XUnified_v7_Get_stride_f(XUnified_v7 *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_STRIDE_F_DATA);
    return Data;
}

void XUnified_v7_Set_input_zp(XUnified_v7 *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_INPUT_ZP_DATA, Data);
}

u32 XUnified_v7_Get_input_zp(XUnified_v7 *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_INPUT_ZP_DATA);
    return Data;
}

void XUnified_v7_Set_output_zp(XUnified_v7 *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_OUTPUT_ZP_DATA, Data);
}

u32 XUnified_v7_Get_output_zp(XUnified_v7 *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_OUTPUT_ZP_DATA);
    return Data;
}

void XUnified_v7_Set_requant_shift(XUnified_v7 *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_REQUANT_SHIFT_DATA, Data);
}

u32 XUnified_v7_Get_requant_shift(XUnified_v7 *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_REQUANT_SHIFT_DATA);
    return Data;
}

void XUnified_v7_Set_flags(XUnified_v7 *InstancePtr, u32 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_FLAGS_DATA, Data);
}

u32 XUnified_v7_Get_flags(XUnified_v7 *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_FLAGS_DATA);
    return Data;
}

void XUnified_v7_InterruptGlobalEnable(XUnified_v7 *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_GIE, 1);
}

void XUnified_v7_InterruptGlobalDisable(XUnified_v7 *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_GIE, 0);
}

void XUnified_v7_InterruptEnable(XUnified_v7 *InstancePtr, u32 Mask) {
    u32 Register;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Register =  XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_IER);
    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_IER, Register | Mask);
}

void XUnified_v7_InterruptDisable(XUnified_v7 *InstancePtr, u32 Mask) {
    u32 Register;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Register =  XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_IER);
    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_IER, Register & (~Mask));
}

void XUnified_v7_InterruptClear(XUnified_v7 *InstancePtr, u32 Mask) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XUnified_v7_WriteReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_ISR, Mask);
}

u32 XUnified_v7_InterruptGetEnabled(XUnified_v7 *InstancePtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    return XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_IER);
}

u32 XUnified_v7_InterruptGetStatus(XUnified_v7 *InstancePtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    return XUnified_v7_ReadReg(InstancePtr->Control_BaseAddress, XUNIFIED_V7_CONTROL_ADDR_ISR);
}

