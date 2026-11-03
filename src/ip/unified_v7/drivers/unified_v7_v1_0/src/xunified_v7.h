// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2025.2 (64-bit)
// Tool Version Limit: 2025.11
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2025 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================
#ifndef XUNIFIED_V7_H
#define XUNIFIED_V7_H

#ifdef __cplusplus
extern "C" {
#endif

/***************************** Include Files *********************************/
#ifndef __linux__
#include "xil_types.h"
#include "xil_assert.h"
#include "xstatus.h"
#include "xil_io.h"
#else
#include <stdint.h>
#include <assert.h>
#include <dirent.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include <stddef.h>
#endif
#include "xunified_v7_hw.h"

/**************************** Type Definitions ******************************/
#ifdef __linux__
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
#else
typedef struct {
#ifdef SDT
    char *Name;
#else
    u16 DeviceId;
#endif
    u64 Control_BaseAddress;
} XUnified_v7_Config;
#endif

typedef struct {
    u64 Control_BaseAddress;
    u32 IsReady;
} XUnified_v7;

typedef u32 word_type;

/***************** Macros (Inline Functions) Definitions *********************/
#ifndef __linux__
#define XUnified_v7_WriteReg(BaseAddress, RegOffset, Data) \
    Xil_Out32((BaseAddress) + (RegOffset), (u32)(Data))
#define XUnified_v7_ReadReg(BaseAddress, RegOffset) \
    Xil_In32((BaseAddress) + (RegOffset))
#else
#define XUnified_v7_WriteReg(BaseAddress, RegOffset, Data) \
    *(volatile u32*)((BaseAddress) + (RegOffset)) = (u32)(Data)
#define XUnified_v7_ReadReg(BaseAddress, RegOffset) \
    *(volatile u32*)((BaseAddress) + (RegOffset))

#define Xil_AssertVoid(expr)    assert(expr)
#define Xil_AssertNonvoid(expr) assert(expr)

#define XST_SUCCESS             0
#define XST_DEVICE_NOT_FOUND    2
#define XST_OPEN_DEVICE_FAILED  3
#define XIL_COMPONENT_IS_READY  1
#endif

/************************** Function Prototypes *****************************/
#ifndef __linux__
#ifdef SDT
int XUnified_v7_Initialize(XUnified_v7 *InstancePtr, UINTPTR BaseAddress);
XUnified_v7_Config* XUnified_v7_LookupConfig(UINTPTR BaseAddress);
#else
int XUnified_v7_Initialize(XUnified_v7 *InstancePtr, u16 DeviceId);
XUnified_v7_Config* XUnified_v7_LookupConfig(u16 DeviceId);
#endif
int XUnified_v7_CfgInitialize(XUnified_v7 *InstancePtr, XUnified_v7_Config *ConfigPtr);
#else
int XUnified_v7_Initialize(XUnified_v7 *InstancePtr, const char* InstanceName);
int XUnified_v7_Release(XUnified_v7 *InstancePtr);
#endif

void XUnified_v7_Start(XUnified_v7 *InstancePtr);
u32 XUnified_v7_IsDone(XUnified_v7 *InstancePtr);
u32 XUnified_v7_IsIdle(XUnified_v7 *InstancePtr);
u32 XUnified_v7_IsReady(XUnified_v7 *InstancePtr);
void XUnified_v7_EnableAutoRestart(XUnified_v7 *InstancePtr);
void XUnified_v7_DisableAutoRestart(XUnified_v7 *InstancePtr);
u32 XUnified_v7_Get_return(XUnified_v7 *InstancePtr);

void XUnified_v7_Set_input_r(XUnified_v7 *InstancePtr, u64 Data);
u64 XUnified_v7_Get_input_r(XUnified_v7 *InstancePtr);
void XUnified_v7_Set_weights(XUnified_v7 *InstancePtr, u64 Data);
u64 XUnified_v7_Get_weights(XUnified_v7 *InstancePtr);
void XUnified_v7_Set_bias(XUnified_v7 *InstancePtr, u64 Data);
u64 XUnified_v7_Get_bias(XUnified_v7 *InstancePtr);
void XUnified_v7_Set_multiplier(XUnified_v7 *InstancePtr, u64 Data);
u64 XUnified_v7_Get_multiplier(XUnified_v7 *InstancePtr);
void XUnified_v7_Set_post_lut(XUnified_v7 *InstancePtr, u64 Data);
u64 XUnified_v7_Get_post_lut(XUnified_v7 *InstancePtr);
void XUnified_v7_Set_residual(XUnified_v7 *InstancePtr, u64 Data);
u64 XUnified_v7_Get_residual(XUnified_v7 *InstancePtr);
void XUnified_v7_Set_output_r(XUnified_v7 *InstancePtr, u64 Data);
u64 XUnified_v7_Get_output_r(XUnified_v7 *InstancePtr);
void XUnified_v7_Set_accumulator_out(XUnified_v7 *InstancePtr, u64 Data);
u64 XUnified_v7_Get_accumulator_out(XUnified_v7 *InstancePtr);
void XUnified_v7_Set_mode(XUnified_v7 *InstancePtr, u32 Data);
u32 XUnified_v7_Get_mode(XUnified_v7 *InstancePtr);
void XUnified_v7_Set_cin(XUnified_v7 *InstancePtr, u32 Data);
u32 XUnified_v7_Get_cin(XUnified_v7 *InstancePtr);
void XUnified_v7_Set_cout(XUnified_v7 *InstancePtr, u32 Data);
u32 XUnified_v7_Get_cout(XUnified_v7 *InstancePtr);
void XUnified_v7_Set_freq(XUnified_v7 *InstancePtr, u32 Data);
u32 XUnified_v7_Get_freq(XUnified_v7 *InstancePtr);
void XUnified_v7_Set_frames(XUnified_v7 *InstancePtr, u32 Data);
u32 XUnified_v7_Get_frames(XUnified_v7 *InstancePtr);
void XUnified_v7_Set_kernel(XUnified_v7 *InstancePtr, u32 Data);
u32 XUnified_v7_Get_kernel(XUnified_v7 *InstancePtr);
void XUnified_v7_Set_stride_f(XUnified_v7 *InstancePtr, u32 Data);
u32 XUnified_v7_Get_stride_f(XUnified_v7 *InstancePtr);
void XUnified_v7_Set_input_zp(XUnified_v7 *InstancePtr, u32 Data);
u32 XUnified_v7_Get_input_zp(XUnified_v7 *InstancePtr);
void XUnified_v7_Set_output_zp(XUnified_v7 *InstancePtr, u32 Data);
u32 XUnified_v7_Get_output_zp(XUnified_v7 *InstancePtr);
void XUnified_v7_Set_requant_shift(XUnified_v7 *InstancePtr, u32 Data);
u32 XUnified_v7_Get_requant_shift(XUnified_v7 *InstancePtr);
void XUnified_v7_Set_flags(XUnified_v7 *InstancePtr, u32 Data);
u32 XUnified_v7_Get_flags(XUnified_v7 *InstancePtr);

void XUnified_v7_InterruptGlobalEnable(XUnified_v7 *InstancePtr);
void XUnified_v7_InterruptGlobalDisable(XUnified_v7 *InstancePtr);
void XUnified_v7_InterruptEnable(XUnified_v7 *InstancePtr, u32 Mask);
void XUnified_v7_InterruptDisable(XUnified_v7 *InstancePtr, u32 Mask);
void XUnified_v7_InterruptClear(XUnified_v7 *InstancePtr, u32 Mask);
u32 XUnified_v7_InterruptGetEnabled(XUnified_v7 *InstancePtr);
u32 XUnified_v7_InterruptGetStatus(XUnified_v7 *InstancePtr);

#ifdef __cplusplus
}
#endif

#endif
