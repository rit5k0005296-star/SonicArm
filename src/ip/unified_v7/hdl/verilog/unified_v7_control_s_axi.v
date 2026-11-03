// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2025.2 (64-bit)
// Tool Version Limit: 2025.11
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2025 Advanced Micro Devices, Inc. All Rights Reserved.
// 
// ==============================================================
`timescale 1ns/1ps
(* DowngradeIPIdentifiedWarnings="yes" *) module unified_v7_control_s_axi
#(parameter
    C_S_AXI_ADDR_WIDTH = 8,
    C_S_AXI_DATA_WIDTH = 32
)(
    input  wire                          ACLK,
    input  wire                          ARESET,
    input  wire                          ACLK_EN,
    input  wire [C_S_AXI_ADDR_WIDTH-1:0] AWADDR,
    input  wire                          AWVALID,
    output wire                          AWREADY,
    input  wire [C_S_AXI_DATA_WIDTH-1:0] WDATA,
    input  wire [C_S_AXI_DATA_WIDTH/8-1:0] WSTRB,
    input  wire                          WVALID,
    output wire                          WREADY,
    output wire [1:0]                    BRESP,
    output wire                          BVALID,
    input  wire                          BREADY,
    input  wire [C_S_AXI_ADDR_WIDTH-1:0] ARADDR,
    input  wire                          ARVALID,
    output wire                          ARREADY,
    output wire [C_S_AXI_DATA_WIDTH-1:0] RDATA,
    output wire [1:0]                    RRESP,
    output wire                          RVALID,
    input  wire                          RREADY,
    output wire                          interrupt,
    output wire                          ap_start,
    input  wire                          ap_done,
    input  wire                          ap_ready,
    input  wire                          ap_idle,
    input  wire [31:0]                   ap_return,
    output wire [63:0]                   input_r,
    output wire [63:0]                   weights,
    output wire [63:0]                   bias,
    output wire [63:0]                   multiplier,
    output wire [63:0]                   post_lut,
    output wire [63:0]                   residual,
    output wire [63:0]                   output_r,
    output wire [63:0]                   accumulator_out,
    output wire [31:0]                   mode,
    output wire [31:0]                   cin,
    output wire [31:0]                   cout,
    output wire [31:0]                   freq,
    output wire [31:0]                   frames,
    output wire [31:0]                   kernel,
    output wire [31:0]                   stride_f,
    output wire [31:0]                   input_zp,
    output wire [31:0]                   output_zp,
    output wire [31:0]                   requant_shift,
    output wire [31:0]                   flags
);
//------------------------Address Info-------------------
// Protocol Used: ap_ctrl_hs
//
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

//------------------------Parameter----------------------
localparam
    ADDR_AP_CTRL                = 8'h00,
    ADDR_GIE                    = 8'h04,
    ADDR_IER                    = 8'h08,
    ADDR_ISR                    = 8'h0c,
    ADDR_AP_RETURN_0            = 8'h10,
    ADDR_INPUT_R_DATA_0         = 8'h18,
    ADDR_INPUT_R_DATA_1         = 8'h1c,
    ADDR_INPUT_R_CTRL           = 8'h20,
    ADDR_WEIGHTS_DATA_0         = 8'h24,
    ADDR_WEIGHTS_DATA_1         = 8'h28,
    ADDR_WEIGHTS_CTRL           = 8'h2c,
    ADDR_BIAS_DATA_0            = 8'h30,
    ADDR_BIAS_DATA_1            = 8'h34,
    ADDR_BIAS_CTRL              = 8'h38,
    ADDR_MULTIPLIER_DATA_0      = 8'h3c,
    ADDR_MULTIPLIER_DATA_1      = 8'h40,
    ADDR_MULTIPLIER_CTRL        = 8'h44,
    ADDR_POST_LUT_DATA_0        = 8'h48,
    ADDR_POST_LUT_DATA_1        = 8'h4c,
    ADDR_POST_LUT_CTRL          = 8'h50,
    ADDR_RESIDUAL_DATA_0        = 8'h54,
    ADDR_RESIDUAL_DATA_1        = 8'h58,
    ADDR_RESIDUAL_CTRL          = 8'h5c,
    ADDR_OUTPUT_R_DATA_0        = 8'h60,
    ADDR_OUTPUT_R_DATA_1        = 8'h64,
    ADDR_OUTPUT_R_CTRL          = 8'h68,
    ADDR_ACCUMULATOR_OUT_DATA_0 = 8'h6c,
    ADDR_ACCUMULATOR_OUT_DATA_1 = 8'h70,
    ADDR_ACCUMULATOR_OUT_CTRL   = 8'h74,
    ADDR_MODE_DATA_0            = 8'h78,
    ADDR_MODE_CTRL              = 8'h7c,
    ADDR_CIN_DATA_0             = 8'h80,
    ADDR_CIN_CTRL               = 8'h84,
    ADDR_COUT_DATA_0            = 8'h88,
    ADDR_COUT_CTRL              = 8'h8c,
    ADDR_FREQ_DATA_0            = 8'h90,
    ADDR_FREQ_CTRL              = 8'h94,
    ADDR_FRAMES_DATA_0          = 8'h98,
    ADDR_FRAMES_CTRL            = 8'h9c,
    ADDR_KERNEL_DATA_0          = 8'ha0,
    ADDR_KERNEL_CTRL            = 8'ha4,
    ADDR_STRIDE_F_DATA_0        = 8'ha8,
    ADDR_STRIDE_F_CTRL          = 8'hac,
    ADDR_INPUT_ZP_DATA_0        = 8'hb0,
    ADDR_INPUT_ZP_CTRL          = 8'hb4,
    ADDR_OUTPUT_ZP_DATA_0       = 8'hb8,
    ADDR_OUTPUT_ZP_CTRL         = 8'hbc,
    ADDR_REQUANT_SHIFT_DATA_0   = 8'hc0,
    ADDR_REQUANT_SHIFT_CTRL     = 8'hc4,
    ADDR_FLAGS_DATA_0           = 8'hc8,
    ADDR_FLAGS_CTRL             = 8'hcc,
    WRIDLE                      = 2'd0,
    WRDATA                      = 2'd1,
    WRRESP                      = 2'd2,
    WRRESET                     = 2'd3,
    RDIDLE                      = 2'd0,
    RDDATA                      = 2'd1,
    RDRESET                     = 2'd2,
    ADDR_BITS                = 8;

//------------------------Local signal-------------------
    reg  [1:0]                    wstate = WRRESET;
    reg  [1:0]                    wnext;
    reg  [ADDR_BITS-1:0]          waddr;
    wire [C_S_AXI_DATA_WIDTH-1:0] wmask;
    wire                          aw_hs;
    wire                          w_hs;
    reg  [1:0]                    rstate = RDRESET;
    reg  [1:0]                    rnext;
    reg  [C_S_AXI_DATA_WIDTH-1:0] rdata;
    wire                          ar_hs;
    wire [ADDR_BITS-1:0]          raddr;
    // internal registers
    reg                           int_ap_idle = 1'b0;
    reg                           int_ap_ready = 1'b0;
    wire                          task_ap_ready;
    reg                           int_ap_done = 1'b0;
    wire                          task_ap_done;
    reg                           int_task_ap_done = 1'b0;
    reg                           int_ap_start = 1'b0;
    reg                           int_interrupt = 1'b0;
    reg                           int_auto_restart = 1'b0;
    reg                           auto_restart_status = 1'b0;
    wire                          auto_restart_done;
    reg                           int_gie = 1'b0;
    reg  [1:0]                    int_ier = 2'b0;
    reg  [1:0]                    int_isr = 2'b0;
    reg  [31:0]                   int_ap_return;
    reg  [63:0]                   int_input_r = 'b0;
    reg  [63:0]                   int_weights = 'b0;
    reg  [63:0]                   int_bias = 'b0;
    reg  [63:0]                   int_multiplier = 'b0;
    reg  [63:0]                   int_post_lut = 'b0;
    reg  [63:0]                   int_residual = 'b0;
    reg  [63:0]                   int_output_r = 'b0;
    reg  [63:0]                   int_accumulator_out = 'b0;
    reg  [31:0]                   int_mode = 'b0;
    reg  [31:0]                   int_cin = 'b0;
    reg  [31:0]                   int_cout = 'b0;
    reg  [31:0]                   int_freq = 'b0;
    reg  [31:0]                   int_frames = 'b0;
    reg  [31:0]                   int_kernel = 'b0;
    reg  [31:0]                   int_stride_f = 'b0;
    reg  [31:0]                   int_input_zp = 'b0;
    reg  [31:0]                   int_output_zp = 'b0;
    reg  [31:0]                   int_requant_shift = 'b0;
    reg  [31:0]                   int_flags = 'b0;

//------------------------Instantiation------------------


//------------------------AXI write fsm------------------
assign AWREADY = (wstate == WRIDLE);
assign WREADY  = (wstate == WRDATA);
assign BVALID  = (wstate == WRRESP);
assign BRESP   = 2'b00;  // OKAY
assign wmask   = { {8{WSTRB[3]}}, {8{WSTRB[2]}}, {8{WSTRB[1]}}, {8{WSTRB[0]}} };
assign aw_hs   = AWVALID & AWREADY;
assign w_hs    = WVALID & WREADY;

// wstate
always @(posedge ACLK) begin
    if (ARESET)
        wstate <= WRRESET;
    else if (ACLK_EN)
        wstate <= wnext;
end

// wnext
always @(*) begin
    case (wstate)
        WRIDLE:
            if (AWVALID)
                wnext = WRDATA;
            else
                wnext = WRIDLE;
        WRDATA:
            if (WVALID)
                wnext = WRRESP;
            else
                wnext = WRDATA;
        WRRESP:
            if (BREADY & BVALID)
                wnext = WRIDLE;
            else
                wnext = WRRESP;
        default:
            wnext = WRIDLE;
    endcase
end

// waddr
always @(posedge ACLK) begin
    if (ACLK_EN) begin
        if (aw_hs)
            waddr <= {AWADDR[ADDR_BITS-1:2], {2{1'b0}}};
    end
end

//------------------------AXI read fsm-------------------
assign ARREADY = (rstate == RDIDLE);
assign RDATA   = rdata;
assign RRESP   = 2'b00;  // OKAY
assign RVALID  = (rstate == RDDATA);
assign ar_hs   = ARVALID & ARREADY;
assign raddr   = ARADDR[ADDR_BITS-1:0];

// rstate
always @(posedge ACLK) begin
    if (ARESET)
        rstate <= RDRESET;
    else if (ACLK_EN)
        rstate <= rnext;
end

// rnext
always @(*) begin
    case (rstate)
        RDIDLE:
            if (ARVALID)
                rnext = RDDATA;
            else
                rnext = RDIDLE;
        RDDATA:
            if (RREADY & RVALID)
                rnext = RDIDLE;
            else
                rnext = RDDATA;
        default:
            rnext = RDIDLE;
    endcase
end

// rdata
always @(posedge ACLK) begin
    if (ACLK_EN) begin
        if (ar_hs) begin
            rdata <= 'b0;
            case (raddr)
                ADDR_AP_CTRL: begin
                    rdata[0] <= int_ap_start;
                    rdata[1] <= int_task_ap_done;
                    rdata[2] <= int_ap_idle;
                    rdata[3] <= int_ap_ready;
                    rdata[7] <= int_auto_restart;
                    rdata[9] <= int_interrupt;
                end
                ADDR_GIE: begin
                    rdata <= int_gie;
                end
                ADDR_IER: begin
                    rdata <= int_ier;
                end
                ADDR_ISR: begin
                    rdata <= int_isr;
                end
                ADDR_AP_RETURN_0: begin
                    rdata <= int_ap_return[31:0];
                end
                ADDR_INPUT_R_DATA_0: begin
                    rdata <= int_input_r[31:0];
                end
                ADDR_INPUT_R_DATA_1: begin
                    rdata <= int_input_r[63:32];
                end
                ADDR_WEIGHTS_DATA_0: begin
                    rdata <= int_weights[31:0];
                end
                ADDR_WEIGHTS_DATA_1: begin
                    rdata <= int_weights[63:32];
                end
                ADDR_BIAS_DATA_0: begin
                    rdata <= int_bias[31:0];
                end
                ADDR_BIAS_DATA_1: begin
                    rdata <= int_bias[63:32];
                end
                ADDR_MULTIPLIER_DATA_0: begin
                    rdata <= int_multiplier[31:0];
                end
                ADDR_MULTIPLIER_DATA_1: begin
                    rdata <= int_multiplier[63:32];
                end
                ADDR_POST_LUT_DATA_0: begin
                    rdata <= int_post_lut[31:0];
                end
                ADDR_POST_LUT_DATA_1: begin
                    rdata <= int_post_lut[63:32];
                end
                ADDR_RESIDUAL_DATA_0: begin
                    rdata <= int_residual[31:0];
                end
                ADDR_RESIDUAL_DATA_1: begin
                    rdata <= int_residual[63:32];
                end
                ADDR_OUTPUT_R_DATA_0: begin
                    rdata <= int_output_r[31:0];
                end
                ADDR_OUTPUT_R_DATA_1: begin
                    rdata <= int_output_r[63:32];
                end
                ADDR_ACCUMULATOR_OUT_DATA_0: begin
                    rdata <= int_accumulator_out[31:0];
                end
                ADDR_ACCUMULATOR_OUT_DATA_1: begin
                    rdata <= int_accumulator_out[63:32];
                end
                ADDR_MODE_DATA_0: begin
                    rdata <= int_mode[31:0];
                end
                ADDR_CIN_DATA_0: begin
                    rdata <= int_cin[31:0];
                end
                ADDR_COUT_DATA_0: begin
                    rdata <= int_cout[31:0];
                end
                ADDR_FREQ_DATA_0: begin
                    rdata <= int_freq[31:0];
                end
                ADDR_FRAMES_DATA_0: begin
                    rdata <= int_frames[31:0];
                end
                ADDR_KERNEL_DATA_0: begin
                    rdata <= int_kernel[31:0];
                end
                ADDR_STRIDE_F_DATA_0: begin
                    rdata <= int_stride_f[31:0];
                end
                ADDR_INPUT_ZP_DATA_0: begin
                    rdata <= int_input_zp[31:0];
                end
                ADDR_OUTPUT_ZP_DATA_0: begin
                    rdata <= int_output_zp[31:0];
                end
                ADDR_REQUANT_SHIFT_DATA_0: begin
                    rdata <= int_requant_shift[31:0];
                end
                ADDR_FLAGS_DATA_0: begin
                    rdata <= int_flags[31:0];
                end
            endcase
        end
    end
end


//------------------------Register logic-----------------
assign interrupt         = int_interrupt;
assign ap_start          = int_ap_start;
assign task_ap_done      = (ap_done && !auto_restart_status) || auto_restart_done;
assign task_ap_ready     = ap_ready && !int_auto_restart;
assign auto_restart_done = auto_restart_status && (ap_idle && !int_ap_idle);
assign input_r           = int_input_r;
assign weights           = int_weights;
assign bias              = int_bias;
assign multiplier        = int_multiplier;
assign post_lut          = int_post_lut;
assign residual          = int_residual;
assign output_r          = int_output_r;
assign accumulator_out   = int_accumulator_out;
assign mode              = int_mode;
assign cin               = int_cin;
assign cout              = int_cout;
assign freq              = int_freq;
assign frames            = int_frames;
assign kernel            = int_kernel;
assign stride_f          = int_stride_f;
assign input_zp          = int_input_zp;
assign output_zp         = int_output_zp;
assign requant_shift     = int_requant_shift;
assign flags             = int_flags;
// int_interrupt
always @(posedge ACLK) begin
    if (ARESET)
        int_interrupt <= 1'b0;
    else if (ACLK_EN) begin
        if (int_gie && (|int_isr))
            int_interrupt <= 1'b1;
        else
            int_interrupt <= 1'b0;
    end
end

// int_ap_start
always @(posedge ACLK) begin
    if (ARESET)
        int_ap_start <= 1'b0;
    else if (ACLK_EN) begin
        if (w_hs && waddr == ADDR_AP_CTRL && WSTRB[0] && WDATA[0])
            int_ap_start <= 1'b1;
        else if (ap_ready)
            int_ap_start <= int_auto_restart; // clear on handshake/auto restart
    end
end

// int_ap_done
always @(posedge ACLK) begin
    if (ARESET)
        int_ap_done <= 1'b0;
    else if (ACLK_EN) begin
            int_ap_done <= ap_done;
    end
end

// int_task_ap_done
always @(posedge ACLK) begin
    if (ARESET)
        int_task_ap_done <= 1'b0;
    else if (ACLK_EN) begin
        if (task_ap_done)
            int_task_ap_done <= 1'b1;
        else if (ar_hs && raddr == ADDR_AP_CTRL)
            int_task_ap_done <= 1'b0; // clear on read
    end
end

// int_ap_idle
always @(posedge ACLK) begin
    if (ARESET)
        int_ap_idle <= 1'b0;
    else if (ACLK_EN) begin
            int_ap_idle <= ap_idle;
    end
end

// int_ap_ready
always @(posedge ACLK) begin
    if (ARESET)
        int_ap_ready <= 1'b0;
    else if (ACLK_EN) begin
        if (task_ap_ready)
            int_ap_ready <= 1'b1;
        else if (ar_hs && raddr == ADDR_AP_CTRL)
            int_ap_ready <= 1'b0;
    end
end

// int_auto_restart
always @(posedge ACLK) begin
    if (ARESET)
        int_auto_restart <= 1'b0;
    else if (ACLK_EN) begin
        if (w_hs && waddr == ADDR_AP_CTRL && WSTRB[0])
            int_auto_restart <= WDATA[7];
    end
end

// auto_restart_status
always @(posedge ACLK) begin
    if (ARESET)
        auto_restart_status <= 1'b0;
    else if (ACLK_EN) begin
        if (int_auto_restart)
            auto_restart_status <= 1'b1;
        else if (ap_idle)
            auto_restart_status <= 1'b0;
    end
end

// int_gie
always @(posedge ACLK) begin
    if (ARESET)
        int_gie <= 1'b0;
    else if (ACLK_EN) begin
        if (w_hs && waddr == ADDR_GIE && WSTRB[0])
            int_gie <= WDATA[0];
    end
end

// int_ier
always @(posedge ACLK) begin
    if (ARESET)
        int_ier <= 1'b0;
    else if (ACLK_EN) begin
        if (w_hs && waddr == ADDR_IER && WSTRB[0])
            int_ier <= WDATA[1:0];
    end
end

// int_isr[0]
always @(posedge ACLK) begin
    if (ARESET)
        int_isr[0] <= 1'b0;
    else if (ACLK_EN) begin
        if (int_ier[0] & ap_done)
            int_isr[0] <= 1'b1;
        else if (w_hs && waddr == ADDR_ISR && WSTRB[0])
            int_isr[0] <= int_isr[0] ^ WDATA[0]; // toggle on write
    end
end

// int_isr[1]
always @(posedge ACLK) begin
    if (ARESET)
        int_isr[1] <= 1'b0;
    else if (ACLK_EN) begin
        if (int_ier[1] & ap_ready)
            int_isr[1] <= 1'b1;
        else if (w_hs && waddr == ADDR_ISR && WSTRB[0])
            int_isr[1] <= int_isr[1] ^ WDATA[1]; // toggle on write
    end
end

// int_ap_return
always @(posedge ACLK) begin
    if (ARESET)
        int_ap_return <= 0;
    else if (ACLK_EN) begin
        if (ap_done)
            int_ap_return <= ap_return;
    end
end

// int_input_r[31:0]
always @(posedge ACLK) begin
    if (ARESET)
        int_input_r[31:0] <= 0;
    else if (ACLK_EN) begin
        if (w_hs && waddr == ADDR_INPUT_R_DATA_0)
            int_input_r[31:0] <= (WDATA[31:0] & wmask) | (int_input_r[31:0] & ~wmask);
    end
end

// int_input_r[63:32]
always @(posedge ACLK) begin
    if (ARESET)
        int_input_r[63:32] <= 0;
    else if (ACLK_EN) begin
        if (w_hs && waddr == ADDR_INPUT_R_DATA_1)
            int_input_r[63:32] <= (WDATA[31:0] & wmask) | (int_input_r[63:32] & ~wmask);
    end
end

// int_weights[31:0]
always @(posedge ACLK) begin
    if (ARESET)
        int_weights[31:0] <= 0;
    else if (ACLK_EN) begin
        if (w_hs && waddr == ADDR_WEIGHTS_DATA_0)
            int_weights[31:0] <= (WDATA[31:0] & wmask) | (int_weights[31:0] & ~wmask);
    end
end

// int_weights[63:32]
always @(posedge ACLK) begin
    if (ARESET)
        int_weights[63:32] <= 0;
    else if (ACLK_EN) begin
        if (w_hs && waddr == ADDR_WEIGHTS_DATA_1)
            int_weights[63:32] <= (WDATA[31:0] & wmask) | (int_weights[63:32] & ~wmask);
    end
end

// int_bias[31:0]
always @(posedge ACLK) begin
    if (ARESET)
        int_bias[31:0] <= 0;
    else if (ACLK_EN) begin
        if (w_hs && waddr == ADDR_BIAS_DATA_0)
            int_bias[31:0] <= (WDATA[31:0] & wmask) | (int_bias[31:0] & ~wmask);
    end
end

// int_bias[63:32]
always @(posedge ACLK) begin
    if (ARESET)
        int_bias[63:32] <= 0;
    else if (ACLK_EN) begin
        if (w_hs && waddr == ADDR_BIAS_DATA_1)
            int_bias[63:32] <= (WDATA[31:0] & wmask) | (int_bias[63:32] & ~wmask);
    end
end

// int_multiplier[31:0]
always @(posedge ACLK) begin
    if (ARESET)
        int_multiplier[31:0] <= 0;
    else if (ACLK_EN) begin
        if (w_hs && waddr == ADDR_MULTIPLIER_DATA_0)
            int_multiplier[31:0] <= (WDATA[31:0] & wmask) | (int_multiplier[31:0] & ~wmask);
    end
end

// int_multiplier[63:32]
always @(posedge ACLK) begin
    if (ARESET)
        int_multiplier[63:32] <= 0;
    else if (ACLK_EN) begin
        if (w_hs && waddr == ADDR_MULTIPLIER_DATA_1)
            int_multiplier[63:32] <= (WDATA[31:0] & wmask) | (int_multiplier[63:32] & ~wmask);
    end
end

// int_post_lut[31:0]
always @(posedge ACLK) begin
    if (ARESET)
        int_post_lut[31:0] <= 0;
    else if (ACLK_EN) begin
        if (w_hs && waddr == ADDR_POST_LUT_DATA_0)
            int_post_lut[31:0] <= (WDATA[31:0] & wmask) | (int_post_lut[31:0] & ~wmask);
    end
end

// int_post_lut[63:32]
always @(posedge ACLK) begin
    if (ARESET)
        int_post_lut[63:32] <= 0;
    else if (ACLK_EN) begin
        if (w_hs && waddr == ADDR_POST_LUT_DATA_1)
            int_post_lut[63:32] <= (WDATA[31:0] & wmask) | (int_post_lut[63:32] & ~wmask);
    end
end

// int_residual[31:0]
always @(posedge ACLK) begin
    if (ARESET)
        int_residual[31:0] <= 0;
    else if (ACLK_EN) begin
        if (w_hs && waddr == ADDR_RESIDUAL_DATA_0)
            int_residual[31:0] <= (WDATA[31:0] & wmask) | (int_residual[31:0] & ~wmask);
    end
end

// int_residual[63:32]
always @(posedge ACLK) begin
    if (ARESET)
        int_residual[63:32] <= 0;
    else if (ACLK_EN) begin
        if (w_hs && waddr == ADDR_RESIDUAL_DATA_1)
            int_residual[63:32] <= (WDATA[31:0] & wmask) | (int_residual[63:32] & ~wmask);
    end
end

// int_output_r[31:0]
always @(posedge ACLK) begin
    if (ARESET)
        int_output_r[31:0] <= 0;
    else if (ACLK_EN) begin
        if (w_hs && waddr == ADDR_OUTPUT_R_DATA_0)
            int_output_r[31:0] <= (WDATA[31:0] & wmask) | (int_output_r[31:0] & ~wmask);
    end
end

// int_output_r[63:32]
always @(posedge ACLK) begin
    if (ARESET)
        int_output_r[63:32] <= 0;
    else if (ACLK_EN) begin
        if (w_hs && waddr == ADDR_OUTPUT_R_DATA_1)
            int_output_r[63:32] <= (WDATA[31:0] & wmask) | (int_output_r[63:32] & ~wmask);
    end
end

// int_accumulator_out[31:0]
always @(posedge ACLK) begin
    if (ARESET)
        int_accumulator_out[31:0] <= 0;
    else if (ACLK_EN) begin
        if (w_hs && waddr == ADDR_ACCUMULATOR_OUT_DATA_0)
            int_accumulator_out[31:0] <= (WDATA[31:0] & wmask) | (int_accumulator_out[31:0] & ~wmask);
    end
end

// int_accumulator_out[63:32]
always @(posedge ACLK) begin
    if (ARESET)
        int_accumulator_out[63:32] <= 0;
    else if (ACLK_EN) begin
        if (w_hs && waddr == ADDR_ACCUMULATOR_OUT_DATA_1)
            int_accumulator_out[63:32] <= (WDATA[31:0] & wmask) | (int_accumulator_out[63:32] & ~wmask);
    end
end

// int_mode[31:0]
always @(posedge ACLK) begin
    if (ARESET)
        int_mode[31:0] <= 0;
    else if (ACLK_EN) begin
        if (w_hs && waddr == ADDR_MODE_DATA_0)
            int_mode[31:0] <= (WDATA[31:0] & wmask) | (int_mode[31:0] & ~wmask);
    end
end

// int_cin[31:0]
always @(posedge ACLK) begin
    if (ARESET)
        int_cin[31:0] <= 0;
    else if (ACLK_EN) begin
        if (w_hs && waddr == ADDR_CIN_DATA_0)
            int_cin[31:0] <= (WDATA[31:0] & wmask) | (int_cin[31:0] & ~wmask);
    end
end

// int_cout[31:0]
always @(posedge ACLK) begin
    if (ARESET)
        int_cout[31:0] <= 0;
    else if (ACLK_EN) begin
        if (w_hs && waddr == ADDR_COUT_DATA_0)
            int_cout[31:0] <= (WDATA[31:0] & wmask) | (int_cout[31:0] & ~wmask);
    end
end

// int_freq[31:0]
always @(posedge ACLK) begin
    if (ARESET)
        int_freq[31:0] <= 0;
    else if (ACLK_EN) begin
        if (w_hs && waddr == ADDR_FREQ_DATA_0)
            int_freq[31:0] <= (WDATA[31:0] & wmask) | (int_freq[31:0] & ~wmask);
    end
end

// int_frames[31:0]
always @(posedge ACLK) begin
    if (ARESET)
        int_frames[31:0] <= 0;
    else if (ACLK_EN) begin
        if (w_hs && waddr == ADDR_FRAMES_DATA_0)
            int_frames[31:0] <= (WDATA[31:0] & wmask) | (int_frames[31:0] & ~wmask);
    end
end

// int_kernel[31:0]
always @(posedge ACLK) begin
    if (ARESET)
        int_kernel[31:0] <= 0;
    else if (ACLK_EN) begin
        if (w_hs && waddr == ADDR_KERNEL_DATA_0)
            int_kernel[31:0] <= (WDATA[31:0] & wmask) | (int_kernel[31:0] & ~wmask);
    end
end

// int_stride_f[31:0]
always @(posedge ACLK) begin
    if (ARESET)
        int_stride_f[31:0] <= 0;
    else if (ACLK_EN) begin
        if (w_hs && waddr == ADDR_STRIDE_F_DATA_0)
            int_stride_f[31:0] <= (WDATA[31:0] & wmask) | (int_stride_f[31:0] & ~wmask);
    end
end

// int_input_zp[31:0]
always @(posedge ACLK) begin
    if (ARESET)
        int_input_zp[31:0] <= 0;
    else if (ACLK_EN) begin
        if (w_hs && waddr == ADDR_INPUT_ZP_DATA_0)
            int_input_zp[31:0] <= (WDATA[31:0] & wmask) | (int_input_zp[31:0] & ~wmask);
    end
end

// int_output_zp[31:0]
always @(posedge ACLK) begin
    if (ARESET)
        int_output_zp[31:0] <= 0;
    else if (ACLK_EN) begin
        if (w_hs && waddr == ADDR_OUTPUT_ZP_DATA_0)
            int_output_zp[31:0] <= (WDATA[31:0] & wmask) | (int_output_zp[31:0] & ~wmask);
    end
end

// int_requant_shift[31:0]
always @(posedge ACLK) begin
    if (ARESET)
        int_requant_shift[31:0] <= 0;
    else if (ACLK_EN) begin
        if (w_hs && waddr == ADDR_REQUANT_SHIFT_DATA_0)
            int_requant_shift[31:0] <= (WDATA[31:0] & wmask) | (int_requant_shift[31:0] & ~wmask);
    end
end

// int_flags[31:0]
always @(posedge ACLK) begin
    if (ARESET)
        int_flags[31:0] <= 0;
    else if (ACLK_EN) begin
        if (w_hs && waddr == ADDR_FLAGS_DATA_0)
            int_flags[31:0] <= (WDATA[31:0] & wmask) | (int_flags[31:0] & ~wmask);
    end
end

//synthesis translate_off
always @(posedge ACLK) begin
    if (ACLK_EN) begin
        if (int_gie & ~int_isr[0] & int_ier[0] & ap_done)
            $display ("// Interrupt Monitor : interrupt for ap_done detected @ \"%0t\"", $time);
        if (int_gie & ~int_isr[1] & int_ier[1] & ap_ready)
            $display ("// Interrupt Monitor : interrupt for ap_ready detected @ \"%0t\"", $time);
    end
end
//synthesis translate_on

//------------------------Memory logic-------------------

endmodule
