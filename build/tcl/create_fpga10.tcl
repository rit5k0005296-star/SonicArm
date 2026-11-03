set script_path [string map {\\ /} [info script]]
set tcl_root [file dirname $script_path]
set repo_root [file normalize "$tcl_root/../.."]
set build_root "$repo_root/build"
set project_dir "$build_root/vivado/fpga10_audio_hdmi"
set project_file "$project_dir/fpga10_audio_hdmi.xpr"

set unified_repo "$repo_root/src/ip/unified_v7"
set audio_repo "$repo_root/src/ip/audio_codec_ctrl_v1.0"
if {[info exists ::env(PYNQ_IP_ROOT)]} {
    set pynq_ip [file normalize $::env(PYNQ_IP_ROOT)]
} else {
    set pynq_ip "$repo_root/src/vendor/PYNQ/boards/ip"
}
set color_ip "$pynq_ip/hls/color_convert/solution1/impl/ip"
set unpack_ip "$pynq_ip/hls/pixel_unpack/solution1/impl/ip"
set xdc "$build_root/constraints/pynq_z2_audio_hdmi_out.xdc"

if {[file exists $project_file]} { error "FPGA-10 project already exists: $project_file" }
foreach required [list \
    "$unified_repo/component.xml" \
    "$audio_repo/component.xml" \
    "$pynq_ip/axi_dynclk_v1_0/component.xml" \
    "$pynq_ip/rgb2dvi_v1_2/component.xml" \
    "$pynq_ip/color_swap_1.1/component.xml" \
    "$pynq_ip/if/tmds_v1_0/tmds.xml" \
    "$pynq_ip/if/tmds_v1_0/tmds_rtl.xml" \
    "$color_ip/component.xml" \
    "$unpack_ip/component.xml" \
    "$tcl_root/ps7_config_v8.tcl" $xdc] {
    if {![file exists $required]} { error "Missing FPGA-10 input: $required" }
}

file mkdir "$build_root/reports"
create_project fpga10_audio_hdmi $project_dir -part xc7z020clg400-1
set_property target_language Verilog [current_project]
set_property simulator_language Mixed [current_project]
set_property ip_repo_paths [list $unified_repo $audio_repo $pynq_ip $color_ip $unpack_ip] [current_project]
update_ip_catalog

foreach vlnv [list \
    xilinx.com:hls:unified_v7:1.0 \
    xilinx.com:user:audio_codec_ctrl:1.0 \
    digilentinc.com:ip:axi_dynclk:1.0 \
    digilentinc.com:ip:rgb2dvi:1.2 \
    xilinx.com:user:color_swap:1.1 \
    xilinx.com:hls:color_convert:1.0 \
    xilinx.com:hls:pixel_unpack:1.0] {
    if {[llength [get_ipdefs -all $vlnv]] == 0} { error "Required IP not found: $vlnv" }
}

create_bd_design system
create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 processing_system7_0
source "$tcl_root/ps7_config_v8.tcl"
set_property -dict [list \
    CONFIG.PCW_USE_M_AXI_GP0 {1} \
    CONFIG.PCW_USE_S_AXI_HP0 {1} CONFIG.PCW_S_AXI_HP0_DATA_WIDTH {64} \
    CONFIG.PCW_USE_S_AXI_HP1 {1} CONFIG.PCW_S_AXI_HP1_DATA_WIDTH {64} \
    CONFIG.PCW_USE_S_AXI_HP2 {1} CONFIG.PCW_S_AXI_HP2_DATA_WIDTH {64} \
    CONFIG.PCW_USE_S_AXI_HP3 {1} CONFIG.PCW_S_AXI_HP3_DATA_WIDTH {64} \
    CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100} \
    CONFIG.PCW_FPGA1_PERIPHERAL_FREQMHZ {142.857143} \
    CONFIG.PCW_EN_CLK1_PORT {1} \
    CONFIG.PCW_FPGA_FCLK1_ENABLE {1} \
] [get_bd_cells processing_system7_0]

make_bd_intf_pins_external [get_bd_intf_pins processing_system7_0/DDR]
set_property name DDR [get_bd_intf_ports DDR_0]
make_bd_intf_pins_external [get_bd_intf_pins processing_system7_0/FIXED_IO]
set_property name FIXED_IO [get_bd_intf_ports FIXED_IO_0]
set iic_port [create_bd_intf_port -mode Master -vlnv xilinx.com:interface:iic_rtl:1.0 IIC_1]
connect_bd_intf_net $iic_port [get_bd_intf_pins processing_system7_0/IIC_1]

# Existing V8 audio and voiceprint accelerator.
create_bd_cell -type ip -vlnv xilinx.com:hls:unified_v7:1.0 unified_0
create_bd_cell -type ip -vlnv xilinx.com:user:audio_codec_ctrl:1.0 audio_codec_ctrl_0
create_bd_cell -type ip -vlnv xilinx.com:ip:clk_wiz:6.0 clk_wiz_10MHz
set_property -dict [list CONFIG.PRIM_IN_FREQ {100.000} \
    CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {10.000} CONFIG.RESET_PORT {resetn} \
    CONFIG.RESET_TYPE {ACTIVE_LOW}] [get_bd_cells clk_wiz_10MHz]

foreach spec {{bclk O} {lrclk O} {sdata_i I} {sdata_o O}} {
    lassign $spec pname pdir
    create_bd_port -dir $pdir $pname
}
create_bd_port -dir O -from 1 -to 0 codec_addr
create_bd_port -dir O -type clk audio_clk_10MHz
connect_bd_net [get_bd_ports bclk] [get_bd_pins audio_codec_ctrl_0/bclk]
connect_bd_net [get_bd_ports lrclk] [get_bd_pins audio_codec_ctrl_0/lrclk]
connect_bd_net [get_bd_ports sdata_i] [get_bd_pins audio_codec_ctrl_0/sdata_i]
connect_bd_net [get_bd_ports sdata_o] [get_bd_pins audio_codec_ctrl_0/sdata_o]
connect_bd_net [get_bd_ports codec_addr] [get_bd_pins audio_codec_ctrl_0/codec_address]
connect_bd_net [get_bd_ports audio_clk_10MHz] [get_bd_pins clk_wiz_10MHz/clk_out1]

# HDMI OUT path: DDR -> HP3 -> VDMA MM2S -> unpack -> color -> AXI4S video -> RGB2DVI.
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_vdma:6.3 axi_vdma_0
set_property -dict [list \
    CONFIG.c_include_s2mm {0} \
    CONFIG.c_m_axi_mm2s_data_width {32} \
    CONFIG.c_m_axis_mm2s_tdata_width {32} \
    CONFIG.c_mm2s_genlock_mode {1} \
    CONFIG.c_mm2s_linebuffer_depth {512} \
    CONFIG.c_mm2s_max_burst_length {32} \
    CONFIG.c_num_fstores {4}] [get_bd_cells axi_vdma_0]
create_bd_cell -type ip -vlnv xilinx.com:hls:pixel_unpack:1.0 pixel_unpack_0
create_bd_cell -type ip -vlnv xilinx.com:ip:axis_register_slice:1.1 axis_register_slice_0
create_bd_cell -type ip -vlnv xilinx.com:hls:color_convert:1.0 color_convert_0
create_bd_cell -type ip -vlnv xilinx.com:ip:v_axi4s_vid_out:4.0 axi4s_vid_out_0
set_property -dict [list CONFIG.C_ADDR_WIDTH {11} CONFIG.C_HAS_ASYNC_CLK {1} \
    CONFIG.C_HYSTERESIS_LEVEL {1024} CONFIG.C_VTG_MASTER_SLAVE {1}] [get_bd_cells axi4s_vid_out_0]
create_bd_cell -type ip -vlnv xilinx.com:ip:v_tc:6.2 vtc_out_0
set_property -dict [list CONFIG.enable_detection {false}] [get_bd_cells vtc_out_0]
create_bd_cell -type ip -vlnv xilinx.com:user:color_swap:1.1 color_swap_0
create_bd_cell -type ip -vlnv digilentinc.com:ip:rgb2dvi:1.2 rgb2dvi_0
set_property -dict [list CONFIG.kClkRange {2} CONFIG.kGenerateSerialClk {false} \
    CONFIG.kRstActiveHigh {false}] [get_bd_cells rgb2dvi_0]
create_bd_cell -type ip -vlnv digilentinc.com:ip:axi_dynclk:1.0 axi_dynclk_0
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 hdmi_out_hpd_gpio
set_property -dict [list CONFIG.C_ALL_OUTPUTS {1} CONFIG.C_GPIO_WIDTH {1} \
    CONFIG.C_INTERRUPT_PRESENT {0}] [get_bd_cells hdmi_out_hpd_gpio]

connect_bd_intf_net [get_bd_intf_pins axi_vdma_0/M_AXIS_MM2S] [get_bd_intf_pins pixel_unpack_0/stream_in_32]
connect_bd_intf_net [get_bd_intf_pins pixel_unpack_0/stream_out_24] [get_bd_intf_pins axis_register_slice_0/S_AXIS]
connect_bd_intf_net [get_bd_intf_pins axis_register_slice_0/M_AXIS] [get_bd_intf_pins color_convert_0/stream_in_24]
connect_bd_intf_net [get_bd_intf_pins color_convert_0/stream_out_24] [get_bd_intf_pins axi4s_vid_out_0/video_in]
connect_bd_intf_net [get_bd_intf_pins vtc_out_0/vtiming_out] [get_bd_intf_pins axi4s_vid_out_0/vtiming_in]
connect_bd_intf_net [get_bd_intf_pins axi4s_vid_out_0/vid_io_out] [get_bd_intf_pins color_swap_0/pixel_input]
connect_bd_intf_net [get_bd_intf_pins color_swap_0/pixel_output] [get_bd_intf_pins rgb2dvi_0/RGB]
make_bd_intf_pins_external [get_bd_intf_pins rgb2dvi_0/TMDS]
set_property name hdmi_out [get_bd_intf_ports TMDS_0]
create_bd_port -dir O -from 0 -to 0 hdmi_out_hpd
connect_bd_net [get_bd_ports hdmi_out_hpd] [get_bd_pins hdmi_out_hpd_gpio/gpio_io_o]
# AXI-Lite control fanout.
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 axi_control
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {8}] [get_bd_cells axi_control]
connect_bd_intf_net [get_bd_intf_pins processing_system7_0/M_AXI_GP0] [get_bd_intf_pins axi_control/S00_AXI]
foreach pair [list \
    {M00_AXI unified_0/s_axi_control} \
    {M01_AXI audio_codec_ctrl_0/S_AXI} \
    {M02_AXI axi_vdma_0/S_AXI_LITE} \
    {M03_AXI pixel_unpack_0/s_axi_control} \
    {M04_AXI color_convert_0/s_axi_control} \
    {M05_AXI axi_dynclk_0/s00_axi} \
    {M06_AXI vtc_out_0/ctrl} \
    {M07_AXI hdmi_out_hpd_gpio/S_AXI}] {
    lassign $pair mi slave
    connect_bd_intf_net [get_bd_intf_pins axi_control/$mi] [get_bd_intf_pins $slave]
}

# Independent DDR masters: preserve V8 HP0..2 mapping; reserve HP3 for video.
foreach {hp bundle} {0 gmem_input 1 gmem_params 2 gmem_output} {
    set inter "mem_hp$hp"
    create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 $inter
    set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {1}] [get_bd_cells $inter]
    connect_bd_intf_net [get_bd_intf_pins unified_0/m_axi_$bundle] [get_bd_intf_pins $inter/S00_AXI]
    connect_bd_intf_net [get_bd_intf_pins $inter/M00_AXI] [get_bd_intf_pins processing_system7_0/S_AXI_HP$hp]
    assign_bd_address -offset 0x00000000 -range 512M -target_address_space \
        [get_bd_addr_spaces unified_0/Data_m_axi_$bundle] \
        [get_bd_addr_segs processing_system7_0/S_AXI_HP$hp/HP${hp}_DDR_LOWOCM]
}
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 video_hp3
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {1}] [get_bd_cells video_hp3]
connect_bd_intf_net [get_bd_intf_pins axi_vdma_0/M_AXI_MM2S] [get_bd_intf_pins video_hp3/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins video_hp3/M00_AXI] [get_bd_intf_pins processing_system7_0/S_AXI_HP3]
assign_bd_address -offset 0x10000000 -range 256M -target_address_space \
    [get_bd_addr_spaces axi_vdma_0/Data_MM2S] \
    [get_bd_addr_segs processing_system7_0/S_AXI_HP3/HP3_DDR_LOWOCM]

# Clock and reset domains.
create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_100M
create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_142M
create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_pixel
create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 locked_one
set_property -dict [list CONFIG.CONST_WIDTH {1} CONFIG.CONST_VAL {1}] [get_bd_cells locked_one]
set clk100 [get_bd_pins processing_system7_0/FCLK_CLK0]
set clk142 [get_bd_pins processing_system7_0/FCLK_CLK1]
foreach pin [list processing_system7_0/M_AXI_GP0_ACLK unified_0/ap_clk \
    audio_codec_ctrl_0/s_axi_aclk axi_control/ACLK axi_control/S00_ACLK \
    axi_control/M00_ACLK axi_control/M01_ACLK axi_control/M02_ACLK \
    axi_control/M05_ACLK axi_control/M06_ACLK axi_control/M07_ACLK rst_100M/slowest_sync_clk \
    clk_wiz_10MHz/clk_in1 axi_vdma_0/s_axi_lite_aclk axi_dynclk_0/REF_CLK_I \
    axi_dynclk_0/s00_axi_aclk vtc_out_0/s_axi_aclk hdmi_out_hpd_gpio/s_axi_aclk] {
    connect_bd_net $clk100 [get_bd_pins $pin]
}
foreach hp {0 1 2} {
    foreach pin [list processing_system7_0/S_AXI_HP${hp}_ACLK mem_hp${hp}/ACLK \
        mem_hp${hp}/S00_ACLK mem_hp${hp}/M00_ACLK] { connect_bd_net $clk100 [get_bd_pins $pin] }
}
foreach pin [list processing_system7_0/S_AXI_HP3_ACLK video_hp3/ACLK video_hp3/S00_ACLK \
    video_hp3/M00_ACLK rst_142M/slowest_sync_clk axi_vdma_0/m_axi_mm2s_aclk \
    axi_vdma_0/m_axis_mm2s_aclk pixel_unpack_0/ap_clk axis_register_slice_0/aclk \
    color_convert_0/ap_clk axi4s_vid_out_0/aclk axi_control/M03_ACLK axi_control/M04_ACLK] {
    connect_bd_net $clk142 [get_bd_pins $pin]
}
connect_bd_net [get_bd_pins processing_system7_0/FCLK_RESET0_N] \
    [get_bd_pins rst_100M/ext_reset_in] [get_bd_pins rst_142M/ext_reset_in] [get_bd_pins rst_pixel/ext_reset_in]
connect_bd_net [get_bd_pins locked_one/dout] [get_bd_pins rst_100M/dcm_locked] [get_bd_pins rst_142M/dcm_locked]
set rst100i [get_bd_pins rst_100M/interconnect_aresetn]
set rst100p [get_bd_pins rst_100M/peripheral_aresetn]
connect_bd_net $rst100i [get_bd_pins axi_control/ARESETN]
connect_bd_net $rst100p [get_bd_pins axi_control/S00_ARESETN] [get_bd_pins axi_control/M00_ARESETN] \
    [get_bd_pins axi_control/M01_ARESETN] [get_bd_pins axi_control/M02_ARESETN] \
    [get_bd_pins axi_control/M05_ARESETN] [get_bd_pins axi_control/M06_ARESETN] [get_bd_pins axi_control/M07_ARESETN]
foreach hp {0 1 2} {
    connect_bd_net $rst100i [get_bd_pins mem_hp${hp}/ARESETN]
    connect_bd_net $rst100p [get_bd_pins mem_hp${hp}/S00_ARESETN] [get_bd_pins mem_hp${hp}/M00_ARESETN]
}
connect_bd_net $rst100p [get_bd_pins unified_0/ap_rst_n] [get_bd_pins audio_codec_ctrl_0/s_axi_aresetn] \
    [get_bd_pins clk_wiz_10MHz/resetn] [get_bd_pins axi_vdma_0/axi_resetn] \
    [get_bd_pins axi_dynclk_0/s00_axi_aresetn] \
    [get_bd_pins hdmi_out_hpd_gpio/s_axi_aresetn]
set rst142i [get_bd_pins rst_142M/interconnect_aresetn]
set rst142p [get_bd_pins rst_142M/peripheral_aresetn]
connect_bd_net $rst142i [get_bd_pins video_hp3/ARESETN]
connect_bd_net $rst142p [get_bd_pins video_hp3/S00_ARESETN] [get_bd_pins video_hp3/M00_ARESETN] \
    [get_bd_pins pixel_unpack_0/ap_rst_n] [get_bd_pins axis_register_slice_0/aresetn] \
    [get_bd_pins color_convert_0/ap_rst_n] [get_bd_pins axi_control/M03_ARESETN] [get_bd_pins axi_control/M04_ARESETN]

connect_bd_net [get_bd_pins axi_dynclk_0/LOCKED_O] [get_bd_pins rgb2dvi_0/aRst_n]
connect_bd_net [get_bd_pins axi_dynclk_0/LOCKED_O] [get_bd_pins rst_pixel/dcm_locked]
connect_bd_net [get_bd_pins axi_dynclk_0/PXL_CLK_5X_O] [get_bd_pins rgb2dvi_0/SerialClk]
connect_bd_net [get_bd_pins axi_dynclk_0/PXL_CLK_O] [get_bd_pins rgb2dvi_0/PixelClk] \
    [get_bd_pins axi4s_vid_out_0/vid_io_out_clk] [get_bd_pins vtc_out_0/clk] [get_bd_pins rst_pixel/slowest_sync_clk]
connect_bd_net [get_bd_pins rst_pixel/peripheral_aresetn] [get_bd_pins vtc_out_0/resetn]

# Stable address map; V8 accelerator address remains unchanged.
foreach spec [list \
    {0x40000000 unified_0/s_axi_control/Reg} \
    {0x43C00000 audio_codec_ctrl_0/S_AXI/reg0} \
    {0x43000000 axi_vdma_0/S_AXI_LITE/Reg} \
    {0x43C70000 pixel_unpack_0/s_axi_control/Reg} \
    {0x43C60000 color_convert_0/s_axi_control/Reg} \
    {0x43C10000 axi_dynclk_0/s00_axi/reg0} \
    {0x43C20000 vtc_out_0/ctrl/Reg} \
    {0x41230000 hdmi_out_hpd_gpio/S_AXI/Reg}] {
    lassign $spec offset segment
    assign_bd_address -offset $offset -range 64K -target_address_space \
        [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs $segment]
}

add_files -fileset constrs_1 -norecurse $xdc
validate_bd_design
save_bd_design
set bd [get_files system.bd]
generate_target all $bd
add_files -norecurse [make_wrapper -files $bd -top]
set_property top system_wrapper [current_fileset]
set_property AUTO_INCREMENTAL_CHECKPOINT 0 [get_runs synth_1]
set_property AUTO_INCREMENTAL_CHECKPOINT 0 [get_runs impl_1]
update_compile_order -fileset sources_1

set receipt [open "$build_root/reports/project_creation.txt" w]
puts $receipt "project=$project_file"
puts $receipt "part=[get_property PART [current_project]]"
puts $receipt "tool=[version -short]"
puts $receipt "validated=true"
puts $receipt "synthesis_started=false"
puts $receipt "implementation_started=false"
puts $receipt "bitstream_generated=false"
close $receipt
puts "FPGA10_PROJECT_CREATED project=$project_file"
