set script_path [string map {\\ /} [info script]]
set root [file dirname $script_path]
set project_dir "$root/vivado/v8_audio_final"
set project_file "$project_dir/v8_audio.xpr"
set unified_repo "$root/ip/unified_v7"
set audio_repo "$root/ip/audio_codec_ctrl_v1.0"
set audio_xdc "$root/constraints/pynq_z2_audio.xdc"

if {[file exists $project_file]} {
    error "FPGA-8 project already exists: $project_file"
}
foreach required [list "$unified_repo/component.xml" "$audio_repo/component.xml" $audio_xdc "$root/ps7_config_v8.tcl"] {
    if {![file exists $required]} {error "Missing FPGA-8 input: $required"}
}

create_project v8_audio $project_dir -part xc7z020clg400-1
set_property target_language Verilog [current_project]
set_property simulator_language Mixed [current_project]
set_property ip_repo_paths [list $unified_repo $audio_repo] [current_project]
update_ip_catalog

foreach vlnv [list xilinx.com:hls:unified_v7:1.0 xilinx.com:user:audio_codec_ctrl:1.0] {
    if {[llength [get_ipdefs -all $vlnv]] == 0} {error "Required IP not found: $vlnv"}
}

create_bd_design system
create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 processing_system7_0
source "$root/ps7_config_v8.tcl"
set_property -dict [list \
    CONFIG.PCW_USE_S_AXI_HP0 {1} \
    CONFIG.PCW_USE_S_AXI_HP1 {1} \
    CONFIG.PCW_USE_S_AXI_HP2 {1} \
    CONFIG.PCW_S_AXI_HP0_DATA_WIDTH {64} \
    CONFIG.PCW_S_AXI_HP1_DATA_WIDTH {64} \
    CONFIG.PCW_S_AXI_HP2_DATA_WIDTH {64} \
] [get_bd_cells processing_system7_0]

create_bd_cell -type ip -vlnv xilinx.com:hls:unified_v7:1.0 unified_0
create_bd_cell -type ip -vlnv xilinx.com:user:audio_codec_ctrl:1.0 audio_codec_ctrl_0
create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 axi_control
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {2}] [get_bd_cells axi_control]
create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_ps7_0_100M
create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 locked_one
set_property -dict [list CONFIG.CONST_WIDTH {1} CONFIG.CONST_VAL {1}] [get_bd_cells locked_one]
create_bd_cell -type ip -vlnv xilinx.com:ip:clk_wiz:6.0 clk_wiz_10MHz
set_property -dict [list \
    CONFIG.PRIM_IN_FREQ {100.000} \
    CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {10.000} \
    CONFIG.RESET_PORT {resetn} \
    CONFIG.RESET_TYPE {ACTIVE_LOW} \
] [get_bd_cells clk_wiz_10MHz]

puts "===== PS7 DIAGNOSTICS ====="
puts "DDR enabled: [get_property CONFIG.PCW_EN_DDR [get_bd_cells processing_system7_0]]"
puts "DDR interface: [get_bd_intf_pins -quiet processing_system7_0/DDR]"
puts "FIXED_IO interface: [get_bd_intf_pins -quiet processing_system7_0/FIXED_IO]"
puts "All PS7 interfaces: [get_bd_intf_pins -of_objects [get_bd_cells processing_system7_0]]"
puts "===== END DIAGNOSTICS ====="

if {[llength [get_bd_intf_pins -quiet processing_system7_0/DDR]] == 0} {
    error "PS7 DDR interface missing"
}

make_bd_intf_pins_external [get_bd_intf_pins processing_system7_0/DDR]
set_property name DDR [get_bd_intf_ports DDR_0]
make_bd_intf_pins_external [get_bd_intf_pins processing_system7_0/FIXED_IO]
set_property name FIXED_IO [get_bd_intf_ports FIXED_IO_0]
set iic_port [create_bd_intf_port -mode Master -vlnv xilinx.com:interface:iic_rtl:1.0 IIC_1]
connect_bd_intf_net $iic_port [get_bd_intf_pins processing_system7_0/IIC_1]

set bclk_port [create_bd_port -dir O bclk]
set lrclk_port [create_bd_port -dir O lrclk]
set sdata_i_port [create_bd_port -dir I sdata_i]
set sdata_o_port [create_bd_port -dir O sdata_o]
set codec_addr_port [create_bd_port -dir O -from 1 -to 0 codec_addr]
connect_bd_net $bclk_port [get_bd_pins audio_codec_ctrl_0/bclk]
connect_bd_net $lrclk_port [get_bd_pins audio_codec_ctrl_0/lrclk]
connect_bd_net $sdata_i_port [get_bd_pins audio_codec_ctrl_0/sdata_i]
connect_bd_net $sdata_o_port [get_bd_pins audio_codec_ctrl_0/sdata_o]
connect_bd_net $codec_addr_port [get_bd_pins audio_codec_ctrl_0/codec_address]
set audio_clk_port [create_bd_port -dir O -type clk audio_clk_10MHz]
connect_bd_net [get_bd_pins clk_wiz_10MHz/clk_out1] $audio_clk_port

connect_bd_intf_net [get_bd_intf_pins processing_system7_0/M_AXI_GP0] [get_bd_intf_pins axi_control/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_control/M00_AXI] [get_bd_intf_pins unified_0/s_axi_control]
connect_bd_intf_net [get_bd_intf_pins axi_control/M01_AXI] [get_bd_intf_pins audio_codec_ctrl_0/S_AXI]

set clocks [list \
    processing_system7_0/M_AXI_GP0_ACLK \
    unified_0/ap_clk \
    audio_codec_ctrl_0/s_axi_aclk \
    axi_control/aclk \
    rst_ps7_0_100M/slowest_sync_clk \
    clk_wiz_10MHz/clk_in1 \
]
set resets [list unified_0/ap_rst_n audio_codec_ctrl_0/s_axi_aresetn]
foreach {hp bundle} {0 gmem_input 1 gmem_params 2 gmem_output} {
    set inter "mem_hp$hp"
    create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 $inter
    set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {1}] [get_bd_cells $inter]
    connect_bd_intf_net [get_bd_intf_pins unified_0/m_axi_$bundle] [get_bd_intf_pins $inter/S00_AXI]
    connect_bd_intf_net [get_bd_intf_pins $inter/M00_AXI] [get_bd_intf_pins processing_system7_0/S_AXI_HP$hp]
    lappend clocks processing_system7_0/S_AXI_HP${hp}_ACLK $inter/ACLK $inter/S00_ACLK $inter/M00_ACLK
    lappend resets $inter/S00_ARESETN $inter/M00_ARESETN
    connect_bd_net [get_bd_pins rst_ps7_0_100M/interconnect_aresetn] [get_bd_pins $inter/ARESETN]
    assign_bd_address -offset 0x00000000 -range 512M -target_address_space \
        [get_bd_addr_spaces unified_0/Data_m_axi_$bundle] \
        [get_bd_addr_segs processing_system7_0/S_AXI_HP$hp/HP${hp}_DDR_LOWOCM]
}

foreach pin $clocks {
    connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins $pin]
}
connect_bd_net [get_bd_pins processing_system7_0/FCLK_RESET0_N] [get_bd_pins rst_ps7_0_100M/ext_reset_in]
connect_bd_net [get_bd_pins locked_one/dout] [get_bd_pins rst_ps7_0_100M/dcm_locked]
connect_bd_net [get_bd_pins rst_ps7_0_100M/interconnect_aresetn] [get_bd_pins axi_control/aresetn]
connect_bd_net [get_bd_pins rst_ps7_0_100M/peripheral_aresetn] [get_bd_pins clk_wiz_10MHz/resetn]
foreach pin $resets {
    connect_bd_net [get_bd_pins rst_ps7_0_100M/peripheral_aresetn] [get_bd_pins $pin]
}

assign_bd_address -offset 0x40000000 -range 64K -target_address_space \
    [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs unified_0/s_axi_control/Reg]
assign_bd_address -offset 0x43C00000 -range 64K -target_address_space \
    [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs audio_codec_ctrl_0/S_AXI/reg0]

add_files -fileset constrs_1 -norecurse $audio_xdc
set_property PROCESSING_ORDER NORMAL [get_files $audio_xdc]
validate_bd_design
save_bd_design
set bd [get_files system.bd]
generate_target all $bd
add_files -norecurse [make_wrapper -files $bd -top]
set_property top system_wrapper [current_fileset]
set_property AUTO_INCREMENTAL_CHECKPOINT 0 [get_runs synth_1]
set_property AUTO_INCREMENTAL_CHECKPOINT 0 [get_runs impl_1]
update_compile_order -fileset sources_1
save_project_as v8_audio $project_dir

set receipt [open "$root/reports/project_creation.txt" w]
puts $receipt "stage=project_creation_only"
puts $receipt "project=$project_file"
puts $receipt "part=[get_property PART [current_project]]"
puts $receipt "tool=[version -short]"
puts $receipt "bd=[get_property NAME [current_bd_design]]"
puts $receipt "validated=true"
puts $receipt "synthesis_started=false"
puts $receipt "implementation_started=false"
puts $receipt "bitstream_generated=false"
close $receipt
puts "FPGA8_PROJECT_CREATED project=$project_file bd=system synthesis_started=false"
