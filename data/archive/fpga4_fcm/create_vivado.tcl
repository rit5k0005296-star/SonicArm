# New V4 dual-IP project only. The V3 project is never opened or modified.
set root [file normalize [file dirname [info script]]]
if {![string match -nocase "V:/*" $root]} { error "Run through V: short path using run_vivado.ps1." }
set project_dir "$root/vivado_workspace/fcm_vivado"
if {[file exists "$project_dir/fcm_vivado.xpr"]} { error "V4 project exists; open it instead of recreating it." }
set fcm_repo "$root/hls_workspace/fcm/hls/impl/ip"
set pw_repo "$root/vendor/pointwise_v3"
foreach repo [list $fcm_repo $pw_repo] {
    if {![file exists "$repo/component.xml"]} { error "Missing packaged IP: $repo" }
}
create_project fcm_vivado $project_dir -part xc7z020clg400-1
set_property target_language Verilog [current_project]
set_property ip_repo_paths [list $fcm_repo $pw_repo] [current_project]
update_ip_catalog
create_bd_design system
create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 processing_system7_0
source "$root/ps7_config.tcl"
create_bd_cell -type ip -vlnv xilinx.com:hls:fcm:1.0 fcm_0
create_bd_cell -type ip -vlnv xilinx.com:hls:pointwise:1.0 pointwise_0
create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 axi_control
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {2}] [get_bd_cells axi_control]
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 axi_mem_intercon
set_property -dict [list CONFIG.NUM_SI {6} CONFIG.NUM_MI {1}] [get_bd_cells axi_mem_intercon]
create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_ps7_0_100M
create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 locked_one
set_property -dict [list CONFIG.CONST_WIDTH {1} CONFIG.CONST_VAL {1}] [get_bd_cells locked_one]
make_bd_intf_pins_external [get_bd_intf_pins processing_system7_0/DDR]
make_bd_intf_pins_external [get_bd_intf_pins processing_system7_0/FIXED_IO]
set_property name DDR [get_bd_intf_ports DDR_0]
set_property name FIXED_IO [get_bd_intf_ports FIXED_IO_0]
connect_bd_intf_net [get_bd_intf_pins processing_system7_0/M_AXI_GP0] [get_bd_intf_pins axi_control/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_control/M00_AXI] [get_bd_intf_pins pointwise_0/s_axi_control]
connect_bd_intf_net [get_bd_intf_pins axi_control/M01_AXI] [get_bd_intf_pins fcm_0/s_axi_control]
set index 0
foreach ip {pointwise_0 fcm_0} {
    foreach name {gmem_input gmem_params gmem_output} {
        connect_bd_intf_net [get_bd_intf_pins $ip/m_axi_$name] [get_bd_intf_pins axi_mem_intercon/S0${index}_AXI]
        incr index
    }
}
connect_bd_intf_net [get_bd_intf_pins axi_mem_intercon/M00_AXI] [get_bd_intf_pins processing_system7_0/S_AXI_HP0]
set clocks [list processing_system7_0/M_AXI_GP0_ACLK processing_system7_0/S_AXI_HP0_ACLK \
    fcm_0/ap_clk pointwise_0/ap_clk axi_control/aclk axi_mem_intercon/ACLK \
    axi_mem_intercon/M00_ACLK rst_ps7_0_100M/slowest_sync_clk]
for {set i 0} {$i<6} {incr i} { lappend clocks axi_mem_intercon/S0${i}_ACLK }
foreach pin $clocks { connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins $pin] }
connect_bd_net [get_bd_pins processing_system7_0/FCLK_RESET0_N] [get_bd_pins rst_ps7_0_100M/ext_reset_in]
connect_bd_net [get_bd_pins locked_one/dout] [get_bd_pins rst_ps7_0_100M/dcm_locked]
foreach pin {axi_mem_intercon/ARESETN axi_control/aresetn} {
    connect_bd_net [get_bd_pins rst_ps7_0_100M/interconnect_aresetn] [get_bd_pins $pin]
}
set resets [list pointwise_0/ap_rst_n fcm_0/ap_rst_n axi_mem_intercon/M00_ARESETN]
for {set i 0} {$i<6} {incr i} { lappend resets axi_mem_intercon/S0${i}_ARESETN }
foreach pin $resets { connect_bd_net [get_bd_pins rst_ps7_0_100M/peripheral_aresetn] [get_bd_pins $pin] }
assign_bd_address -offset 0x40000000 -range 64K -target_address_space [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs pointwise_0/s_axi_control/Reg]
assign_bd_address -offset 0x40010000 -range 64K -target_address_space [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs fcm_0/s_axi_control/Reg]
foreach ip {pointwise_0 fcm_0} {
    foreach name {gmem_input gmem_params gmem_output} {
        assign_bd_address -offset 0x00000000 -range 512M -target_address_space [get_bd_addr_spaces $ip/Data_m_axi_$name] [get_bd_addr_segs processing_system7_0/S_AXI_HP0/HP0_DDR_LOWOCM]
    }
}
validate_bd_design
save_bd_design
set bd [get_files system.bd]
generate_target all $bd
add_files -norecurse [make_wrapper -files $bd -top]
set_property top system_wrapper [current_fileset]
update_compile_order -fileset sources_1
puts "V4_READY dual IP: fcm_0 + unchanged V3 pointwise_0, clock 100 MHz. No board execution."
