set script_path [string map {\\ /} [info script]]
set tcl_root [file dirname $script_path]
set build_root [file normalize "$tcl_root/.."]
set project_file "$build_root/vivado/fpga10_audio_hdmi/fpga10_audio_hdmi.xpr"
open_project $project_file
open_bd_design "$build_root/vivado/fpga10_audio_hdmi/fpga10_audio_hdmi.srcs/sources_1/bd/system/system.bd"

set irq_net [get_bd_nets -quiet vdma_mm2s_irq]
if {[llength $irq_net] != 0} {
    delete_bd_objs $irq_net
}
set_property -dict [list \
    CONFIG.PCW_USE_FABRIC_INTERRUPT {0} \
    CONFIG.PCW_IRQ_F2P_INTR {0}] [get_bd_cells processing_system7_0]

validate_bd_design
save_bd_design
generate_target all [get_files system.bd]
puts "FPGA10_VDMA_IRQ_REVERTED"
close_project
