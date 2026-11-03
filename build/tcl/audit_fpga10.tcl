set script_path [string map {\\ /} [info script]]
set tcl_root [file dirname $script_path]
set build_root [file normalize "$tcl_root/.."]
open_project "$build_root/vivado/fpga10_audio_hdmi/fpga10_audio_hdmi.xpr"
open_run impl_1
file mkdir "$build_root/reports"
report_timing_summary -report_unconstrained -file "$build_root/reports/impl_timing_summary_audit.rpt"
report_route_status -file "$build_root/reports/impl_route_status_audit.rpt"
report_drc -file "$build_root/reports/impl_drc_audit.rpt"
report_methodology -file "$build_root/reports/impl_methodology_audit.rpt"
report_clock_interaction -file "$build_root/reports/impl_clock_interaction_audit.rpt"
report_cdc -details -file "$build_root/reports/impl_cdc_audit.rpt"
report_bus_skew -file "$build_root/reports/impl_bus_skew_audit.rpt"
check_timing -verbose -file "$build_root/reports/impl_check_timing.rpt"
puts "FPGA10_AUDIT_COMPLETE"
close_project
