set root [file normalize [file dirname [info script]]]
set project_dir "$root/vivado/v7_final"
if {[file exists "$project_dir/v7.xpr"]} {error "V7 project exists; use build/open, not create."}
set repo "$root/hls/shared_pw/hls/impl/ip"
if {![file exists "$repo/component.xml"]} {error "Missing packaged unified_v7 IP: $repo"}

create_project v7 $project_dir -part xc7z020clg400-1
set_property target_language Verilog [current_project]
set_property ip_repo_paths [list $repo] [current_project]
update_ip_catalog
create_bd_design system
create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 processing_system7_0
source "$root/ps7_config.tcl"
set_property -dict [list CONFIG.PCW_USE_S_AXI_HP0 {1} CONFIG.PCW_USE_S_AXI_HP1 {1} CONFIG.PCW_USE_S_AXI_HP2 {1} \
    CONFIG.PCW_S_AXI_HP0_DATA_WIDTH {64} CONFIG.PCW_S_AXI_HP1_DATA_WIDTH {64} CONFIG.PCW_S_AXI_HP2_DATA_WIDTH {64}] \
    [get_bd_cells processing_system7_0]
create_bd_cell -type ip -vlnv xilinx.com:hls:unified_v7:1.0 unified_0
create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 axi_control
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {1}] [get_bd_cells axi_control]
create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_ps7_0_100M
create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 locked_one
set_property -dict [list CONFIG.CONST_WIDTH {1} CONFIG.CONST_VAL {1}] [get_bd_cells locked_one]

make_bd_intf_pins_external [get_bd_intf_pins processing_system7_0/DDR]
make_bd_intf_pins_external [get_bd_intf_pins processing_system7_0/FIXED_IO]
set_property name DDR [get_bd_intf_ports DDR_0]
set_property name FIXED_IO [get_bd_intf_ports FIXED_IO_0]
connect_bd_intf_net [get_bd_intf_pins processing_system7_0/M_AXI_GP0] [get_bd_intf_pins axi_control/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_control/M00_AXI] [get_bd_intf_pins unified_0/s_axi_control]

set clocks [list processing_system7_0/M_AXI_GP0_ACLK unified_0/ap_clk axi_control/aclk rst_ps7_0_100M/slowest_sync_clk]
set resets [list unified_0/ap_rst_n]
foreach {h name} {0 gmem_input 1 gmem_params 2 gmem_output} {
    set inter "mem_hp$h"
    create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 $inter
    set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {1}] [get_bd_cells $inter]
    connect_bd_intf_net [get_bd_intf_pins unified_0/m_axi_$name] [get_bd_intf_pins $inter/S00_AXI]
    connect_bd_intf_net [get_bd_intf_pins $inter/M00_AXI] [get_bd_intf_pins processing_system7_0/S_AXI_HP$h]
    lappend clocks processing_system7_0/S_AXI_HP${h}_ACLK $inter/ACLK $inter/S00_ACLK $inter/M00_ACLK
    lappend resets $inter/S00_ARESETN $inter/M00_ARESETN
    connect_bd_net [get_bd_pins rst_ps7_0_100M/interconnect_aresetn] [get_bd_pins $inter/ARESETN]
    assign_bd_address -offset 0x00000000 -range 512M -target_address_space \
        [get_bd_addr_spaces unified_0/Data_m_axi_$name] \
        [get_bd_addr_segs processing_system7_0/S_AXI_HP$h/HP${h}_DDR_LOWOCM]
}
foreach pin $clocks {connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins $pin]}
connect_bd_net [get_bd_pins processing_system7_0/FCLK_RESET0_N] [get_bd_pins rst_ps7_0_100M/ext_reset_in]
connect_bd_net [get_bd_pins locked_one/dout] [get_bd_pins rst_ps7_0_100M/dcm_locked]
connect_bd_net [get_bd_pins rst_ps7_0_100M/interconnect_aresetn] [get_bd_pins axi_control/aresetn]
foreach pin $resets {connect_bd_net [get_bd_pins rst_ps7_0_100M/peripheral_aresetn] [get_bd_pins $pin]}
assign_bd_address -offset 0x40000000 -range 64K -target_address_space \
    [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs unified_0/s_axi_control/Reg]

validate_bd_design
save_bd_design
set bd [get_files system.bd]
generate_target all $bd
add_files -norecurse [make_wrapper -files $bd -top]
set_property top system_wrapper [current_fileset]
set_property AUTO_INCREMENTAL_CHECKPOINT 0 [get_runs synth_1]
set_property AUTO_INCREMENTAL_CHECKPOINT 0 [get_runs impl_1]
update_compile_order -fileset sources_1
puts "V7_BD_READY unified PW/FCM engine, 3x64-bit HP paths, 100 MHz, no inherited checkpoint."
