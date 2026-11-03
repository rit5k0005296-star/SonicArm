set root [file normalize [file dirname [info script]]]
if {![string match -nocase "W:/*" $root]} {error "Use run_vivado.ps1 to establish W: in THIS process."}
set project_dir "$root/vivado/v5"
if {[file exists "$project_dir/v5.xpr"]} {error "V5 project exists; use build/open, not create."}
set repos [list "$root/hls/pw/hls/impl/ip" "$root/hls/fcm/hls/impl/ip"]
foreach repo $repos {if {![file exists "$repo/component.xml"]} {error "Missing V5 packaged IP: $repo"}}
source "$root/package_monitor.tcl"
lappend repos "$root/rtl/ip"
create_project v5 $project_dir -part xc7z020clg400-1
set_property target_language Verilog [current_project]
set_property ip_repo_paths $repos [current_project]
update_ip_catalog
update_compile_order -fileset sources_1
create_bd_design system
create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 processing_system7_0
source "$root/ps7_config.tcl"
set_property -dict [list CONFIG.PCW_USE_S_AXI_HP0 {1} CONFIG.PCW_USE_S_AXI_HP1 {1} CONFIG.PCW_USE_S_AXI_HP2 {1} \
    CONFIG.PCW_S_AXI_HP0_DATA_WIDTH {64} CONFIG.PCW_S_AXI_HP1_DATA_WIDTH {64} CONFIG.PCW_S_AXI_HP2_DATA_WIDTH {64}] [get_bd_cells processing_system7_0]
create_bd_cell -type ip -vlnv xilinx.com:hls:pointwise_v5:1.0 pointwise_0
create_bd_cell -type ip -vlnv xilinx.com:hls:fcm_v5:1.0 fcm_0
create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 axi_control
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {3}] [get_bd_cells axi_control]
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
set clocks [list processing_system7_0/M_AXI_GP0_ACLK pointwise_0/ap_clk fcm_0/ap_clk \
    axi_control/aclk rst_ps7_0_100M/slowest_sync_clk]
set resets [list pointwise_0/ap_rst_n fcm_0/ap_rst_n]
for {set h 0} {$h<3} {incr h} {
    set name [lindex {gmem_input gmem_params gmem_output} $h]
    set inter "mem_hp$h"
    create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 $inter
    set_property -dict [list CONFIG.NUM_SI {2} CONFIG.NUM_MI {1}] [get_bd_cells $inter]
    connect_bd_intf_net [get_bd_intf_pins pointwise_0/m_axi_$name] [get_bd_intf_pins $inter/S00_AXI]
    connect_bd_intf_net [get_bd_intf_pins fcm_0/m_axi_$name] [get_bd_intf_pins $inter/S01_AXI]
    connect_bd_intf_net [get_bd_intf_pins $inter/M00_AXI] [get_bd_intf_pins processing_system7_0/S_AXI_HP$h]
    lappend clocks processing_system7_0/S_AXI_HP${h}_ACLK $inter/ACLK $inter/S00_ACLK $inter/S01_ACLK $inter/M00_ACLK
    lappend resets $inter/S00_ARESETN $inter/S01_ARESETN $inter/M00_ARESETN
    connect_bd_net [get_bd_pins rst_ps7_0_100M/interconnect_aresetn] [get_bd_pins $inter/ARESETN]
    foreach ip {pointwise_0 fcm_0} {
        assign_bd_address -offset 0x00000000 -range 512M -target_address_space [get_bd_addr_spaces $ip/Data_m_axi_$name] \
            [get_bd_addr_segs processing_system7_0/S_AXI_HP$h/HP${h}_DDR_LOWOCM]
    }
}
foreach pin $clocks {connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins $pin]}
connect_bd_net [get_bd_pins processing_system7_0/FCLK_RESET0_N] [get_bd_pins rst_ps7_0_100M/ext_reset_in]
connect_bd_net [get_bd_pins locked_one/dout] [get_bd_pins rst_ps7_0_100M/dcm_locked]
connect_bd_net [get_bd_pins rst_ps7_0_100M/interconnect_aresetn] [get_bd_pins axi_control/aresetn]
foreach pin $resets {connect_bd_net [get_bd_pins rst_ps7_0_100M/peripheral_aresetn] [get_bd_pins $pin]}
assign_bd_address -offset 0x40000000 -range 64K -target_address_space [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs pointwise_0/s_axi_control/Reg]
assign_bd_address -offset 0x40010000 -range 64K -target_address_space [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs fcm_0/s_axi_control/Reg]
source "$root/connect_monitor.tcl"
validate_bd_design
save_bd_design
set bd [get_files system.bd]
generate_target all $bd
add_files -norecurse [make_wrapper -files $bd -top]
set_property top system_wrapper [current_fileset]
set_property STEPS.POST_ROUTE_PHYS_OPT_DESIGN.IS_ENABLED true [get_runs impl_1]
set_property STEPS.POST_ROUTE_PHYS_OPT_DESIGN.ARGS.DIRECTIVE AggressiveExplore [get_runs impl_1]
update_compile_order -fileset sources_1
puts "V5_BD_READY new PW/FCM, 3x64-bit HP paths, passive RTL monitor, 100 MHz."
