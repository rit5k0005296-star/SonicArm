create_bd_cell -type ip -vlnv sonicarm.org:user:axi_perf_monitor:1.1 perf_0
connect_bd_intf_net [get_bd_intf_pins axi_control/M02_AXI] [get_bd_intf_pins perf_0/S_AXI]
connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins perf_0/aclk]
connect_bd_net [get_bd_pins rst_ps7_0_100M/peripheral_aresetn] [get_bd_pins perf_0/aresetn]
assign_bd_address -offset 0x40020000 -range 64K -target_address_space [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs perf_0/S_AXI/Reg]
foreach {ip label} {pointwise_0 PW fcm_0 FCM} {
    set si [expr {$label eq "PW" ? 0:1}]
    set control_partner [format "axi_control/M%02d_AXI" $si]
    set endpoints [list [get_bd_intf_pins $control_partner] [get_bd_intf_pins $ip/s_axi_control]]
    foreach net [get_bd_intf_nets -quiet -of_objects $endpoints] {delete_bd_objs $net}
    connect_bd_intf_net {*}$endpoints
    connect_bd_intf_net [lindex $endpoints 0] [get_bd_intf_pins perf_0/MON_${label}_CTRL]
    connect_bd_net [get_bd_pins $ip/interrupt] [get_bd_pins perf_0/[string tolower $label]_irq]
    foreach {bundle group hp} {gmem_input INPUT 0 gmem_params PARAMS 1 gmem_output OUTPUT 2} {
        set partner [format "mem_hp%d/S%02d_AXI" $hp $si]
        set endpoints [list [get_bd_intf_pins $ip/m_axi_$bundle] [get_bd_intf_pins $partner]]
        foreach net [get_bd_intf_nets -quiet -of_objects $endpoints] {delete_bd_objs $net}
        connect_bd_intf_net {*}$endpoints
        connect_bd_intf_net [lindex $endpoints 0] [get_bd_intf_pins perf_0/MON_${label}_$group]
    }
}
