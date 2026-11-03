set script_path [string map {\\ /} [info script]]
set tcl_root [file dirname $script_path]
set build_root [file normalize "$tcl_root/.."]
set project_file "$build_root/vivado/fpga10_audio_hdmi/fpga10_audio_hdmi.xpr"
if {![file exists $project_file]} { error "Project not found: $project_file" }
open_project $project_file
reset_run synth_1
# Vivado 2025.2 can race while multiple OOC runs load the shared Tcl app cache.
# A single synthesis worker is slower but reproducible in a clean environment.
launch_runs synth_1 -jobs 1
wait_on_run synth_1
if {[get_property STATUS [get_runs synth_1]] ne "synth_design Complete!"} {
    error "Synthesis failed: [get_property STATUS [get_runs synth_1]]"
}
open_run synth_1
report_utilization -file "$build_root/reports/synth_utilization.rpt"
report_timing_summary -file "$build_root/reports/synth_timing_summary.rpt"
report_drc -file "$build_root/reports/synth_drc.rpt"
close_design

reset_run impl_1
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
if {[get_property STATUS [get_runs impl_1]] ne "write_bitstream Complete!"} {
    error "Implementation failed: [get_property STATUS [get_runs impl_1]]"
}
open_run impl_1
report_utilization -file "$build_root/reports/impl_utilization.rpt"
report_timing_summary -file "$build_root/reports/impl_timing_summary.rpt"
report_route_status -file "$build_root/reports/impl_route_status.rpt"
report_drc -file "$build_root/reports/impl_drc.rpt"
report_methodology -file "$build_root/reports/impl_methodology.rpt"
report_clock_interaction -file "$build_root/reports/impl_clock_interaction.rpt"
report_cdc -details -file "$build_root/reports/impl_cdc.rpt"
check_timing -verbose -file "$build_root/reports/impl_check_timing.rpt"

file mkdir "$build_root/export"
file copy -force "$build_root/vivado/fpga10_audio_hdmi/fpga10_audio_hdmi.runs/impl_1/system_wrapper.bit" "$build_root/export/fpga10_audio_hdmi.bit"
file copy -force "$build_root/vivado/fpga10_audio_hdmi/fpga10_audio_hdmi.gen/sources_1/bd/system/hw_handoff/system.hwh" "$build_root/export/fpga10_audio_hdmi.hwh"
# PYNQ Overlay deployment requires the matched BIT/HWH pair, not an XSA.
# Vivado 2025.2 requires additional platform metadata for write_hw_platform;
# keep XSA generation outside the mandatory Overlay build path.
puts "FPGA10_BUILD_COMPLETE"
