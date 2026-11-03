set root [file normalize [file dirname [info script]]]
source "$root/package_monitor.tcl"
open_project "$root/vivado/v5/v5.xpr"
update_ip_catalog -rebuild
open_bd_design [get_files system.bd]
delete_bd_objs [get_bd_cells perf_0]
set old_concat [get_bd_cells -quiet mon_*]
if {[llength $old_concat]} {delete_bd_objs $old_concat}
# Delete only explicit per-pin probe nets. Removing those overrides restores
# each signal's original connection through its existing AXI interface net.
foreach ip {pointwise_0 fcm_0} {
    set pins {}
    foreach signal {WVALID WREADY WDATA WSTRB} {lappend pins $ip/s_axi_control_$signal}
    foreach bundle {gmem_input gmem_params gmem_output} {
        foreach signal {ARVALID ARREADY RVALID RREADY RLAST AWVALID AWREADY WVALID WREADY} {
            lappend pins $ip/m_axi_${bundle}_$signal
        }
    }
    foreach pin $pins {
        foreach net [get_bd_nets -quiet -of_objects [get_bd_pins $pin]] {
            if {[llength [get_bd_pins -of_objects $net]]!=1} {error "Unexpected remaining users of probe net $net"}
            delete_bd_objs $net
        }
    }
}
source "$root/connect_monitor.tcl"
validate_bd_design
save_bd_design
generate_target all [get_files system.bd]
update_compile_order -fileset sources_1
reset_run synth_1
puts "V5_MONITOR_REPAIRED passive interfaces; previous HLS OOC checkpoints preserved."
