# Run from Vivado 2025.2 Tcl Console: source W:/create_vivado.tcl
# Creates only a NEW project in this V2 subdirectory. Does not run implementation.
set root [file normalize [file dirname [info script]]]
set project_dir "$root/vivado_workspace/conv_relu_vivado"
if {[file exists "$project_dir/conv_relu_vivado.xpr"]} {
    error "V2 project already exists. Open $project_dir/conv_relu_vivado.xpr instead of recreating it."
}
set iprepo "$root/hls_workspace/conv_relu/hls/impl/ip"
if {![file exists "$iprepo/component.xml"]} { error "Run HLS Package first: missing $iprepo/component.xml" }
create_project conv_relu_vivado $project_dir -part xc7z020clg400-1
set_property target_language Verilog [current_project]
set_property ip_repo_paths [list $iprepo] [current_project]
update_ip_catalog
create_bd_design system
create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 processing_system7_0
source "$root/ps7_config.tcl"
create_bd_cell -type ip -vlnv xilinx.com:hls:conv_relu:1.0 conv_relu_0
create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 axi_smc
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {1}] [get_bd_cells axi_smc]
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 axi_mem_intercon
set_property -dict [list CONFIG.NUM_SI {3} CONFIG.NUM_MI {1}] [get_bd_cells axi_mem_intercon]
create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_ps7_0_100M
# Reset polarity is propagated from FCLK_RESET0_N; C_EXT_RESET_HIGH is read-only
# in this version. Validate Design resolves the active-low external reset.
create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 locked_one
set_property -dict [list CONFIG.CONST_WIDTH {1} CONFIG.CONST_VAL {1}] [get_bd_cells locked_one]
make_bd_intf_pins_external [get_bd_intf_pins processing_system7_0/DDR]
make_bd_intf_pins_external [get_bd_intf_pins processing_system7_0/FIXED_IO]
set_property name DDR [get_bd_intf_ports DDR_0]
set_property name FIXED_IO [get_bd_intf_ports FIXED_IO_0]
connect_bd_intf_net [get_bd_intf_pins processing_system7_0/M_AXI_GP0] [get_bd_intf_pins axi_smc/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_smc/M00_AXI] [get_bd_intf_pins conv_relu_0/s_axi_control]
set index 0
foreach name {gmem_input gmem_params gmem_output} {
    connect_bd_intf_net [get_bd_intf_pins conv_relu_0/m_axi_$name] [get_bd_intf_pins axi_mem_intercon/S0${index}_AXI]
    incr index
}
connect_bd_intf_net [get_bd_intf_pins axi_mem_intercon/M00_AXI] [get_bd_intf_pins processing_system7_0/S_AXI_HP0]
set clocks [list processing_system7_0/M_AXI_GP0_ACLK processing_system7_0/S_AXI_HP0_ACLK \
    conv_relu_0/ap_clk axi_smc/aclk axi_mem_intercon/ACLK axi_mem_intercon/M00_ACLK \
    axi_mem_intercon/S00_ACLK axi_mem_intercon/S01_ACLK axi_mem_intercon/S02_ACLK rst_ps7_0_100M/slowest_sync_clk]
foreach pin $clocks { connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins $pin] }
connect_bd_net [get_bd_pins processing_system7_0/FCLK_RESET0_N] [get_bd_pins rst_ps7_0_100M/ext_reset_in]
connect_bd_net [get_bd_pins locked_one/dout] [get_bd_pins rst_ps7_0_100M/dcm_locked]
foreach pin {axi_mem_intercon/ARESETN axi_smc/aresetn} {
    connect_bd_net [get_bd_pins rst_ps7_0_100M/interconnect_aresetn] [get_bd_pins $pin]
}
foreach pin {conv_relu_0/ap_rst_n axi_mem_intercon/M00_ARESETN axi_mem_intercon/S00_ARESETN axi_mem_intercon/S01_ARESETN axi_mem_intercon/S02_ARESETN} {
    connect_bd_net [get_bd_pins rst_ps7_0_100M/peripheral_aresetn] [get_bd_pins $pin]
}
assign_bd_address -offset 0x40000000 -range 64K -target_address_space [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs conv_relu_0/s_axi_control/Reg]
foreach name {gmem_input gmem_params gmem_output} {
    assign_bd_address -offset 0x00000000 -range 512M -target_address_space [get_bd_addr_spaces conv_relu_0/Data_m_axi_$name] [get_bd_addr_segs processing_system7_0/S_AXI_HP0/HP0_DDR_LOWOCM]
}
validate_bd_design
save_bd_design
set bd [get_files system.bd]
generate_target all $bd
set wrapper [make_wrapper -files $bd -top]
add_files -norecurse $wrapper
set_property top system_wrapper [current_fileset]
update_compile_order -fileset sources_1
puts "READY: new V2 project $project_dir/conv_relu_vivado.xpr; BD validated; bitstream not built."
