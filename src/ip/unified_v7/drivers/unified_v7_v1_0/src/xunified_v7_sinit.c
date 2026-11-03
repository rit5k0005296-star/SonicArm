// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2025.2 (64-bit)
// Tool Version Limit: 2025.11
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2025 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================
#ifndef __linux__

#include "xstatus.h"
#ifdef SDT
#include "xparameters.h"
#endif
#include "xunified_v7.h"

extern XUnified_v7_Config XUnified_v7_ConfigTable[];

#ifdef SDT
XUnified_v7_Config *XUnified_v7_LookupConfig(UINTPTR BaseAddress) {
	XUnified_v7_Config *ConfigPtr = NULL;

	int Index;

	for (Index = (u32)0x0; XUnified_v7_ConfigTable[Index].Name != NULL; Index++) {
		if (!BaseAddress || XUnified_v7_ConfigTable[Index].Control_BaseAddress == BaseAddress) {
			ConfigPtr = &XUnified_v7_ConfigTable[Index];
			break;
		}
	}

	return ConfigPtr;
}

int XUnified_v7_Initialize(XUnified_v7 *InstancePtr, UINTPTR BaseAddress) {
	XUnified_v7_Config *ConfigPtr;

	Xil_AssertNonvoid(InstancePtr != NULL);

	ConfigPtr = XUnified_v7_LookupConfig(BaseAddress);
	if (ConfigPtr == NULL) {
		InstancePtr->IsReady = 0;
		return (XST_DEVICE_NOT_FOUND);
	}

	return XUnified_v7_CfgInitialize(InstancePtr, ConfigPtr);
}
#else
XUnified_v7_Config *XUnified_v7_LookupConfig(u16 DeviceId) {
	XUnified_v7_Config *ConfigPtr = NULL;

	int Index;

	for (Index = 0; Index < XPAR_XUNIFIED_V7_NUM_INSTANCES; Index++) {
		if (XUnified_v7_ConfigTable[Index].DeviceId == DeviceId) {
			ConfigPtr = &XUnified_v7_ConfigTable[Index];
			break;
		}
	}

	return ConfigPtr;
}

int XUnified_v7_Initialize(XUnified_v7 *InstancePtr, u16 DeviceId) {
	XUnified_v7_Config *ConfigPtr;

	Xil_AssertNonvoid(InstancePtr != NULL);

	ConfigPtr = XUnified_v7_LookupConfig(DeviceId);
	if (ConfigPtr == NULL) {
		InstancePtr->IsReady = 0;
		return (XST_DEVICE_NOT_FOUND);
	}

	return XUnified_v7_CfgInitialize(InstancePtr, ConfigPtr);
}
#endif

#endif

