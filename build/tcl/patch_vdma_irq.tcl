set script_path [string map {\\ /} [info script]]
set tcl_root [file dirname $script_path]
set build_root [file normalize "$tcl_root/.."]
set project_file "$build_root/vivado/fpga10_audio_hdmi/fpga10_audio_hdmi.xpr"
open_project $project_file
open_bd_design "$build_root/vivado/fpga10_audio_hdmi/fpga10_audio_hdmi.srcs/sources_1/bd/system/system.bd"
set_property -dict [list \
    CONFIG.PCW_USE_FABRIC_INTERRUPT {1} \
    CONFIG.PCW_IRQ_F2P_INTR {1}] [get_bd_cells processing_system7_0]
if {[llength [get_bd_nets -quiet vdma_mm2s_irq]] == 0} {
    connect_bd_net -net vdma_mm2s_irq \
        [get_bd_pins axi_vdma_0/mm2s_introut] \
        [get_bd_pins processing_system7_0/IRQ_F2P]
}
validate_bd_design
save_bd_design
generate_target all [get_files system.bd]
update_compile_order -fileset sources_1
close_project
puts "FPGA10_VDMA_IRQ_PATCH_COMPLETE"
