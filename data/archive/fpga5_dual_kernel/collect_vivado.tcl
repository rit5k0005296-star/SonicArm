set root [file normalize [file dirname [info script]]]
set project "$root/vivado/v5/v5.xpr"
if {[llength [get_projects -quiet]]==0} {open_project $project}
if {[file normalize [get_property DIRECTORY [current_project]]] ne [file dirname $project]} {error "Wrong project."}
if {![string match "*write_bitstream Complete*" [get_property STATUS [get_runs impl_1]]]} {error "Bitstream incomplete."}
if {[get_property NEEDS_REFRESH [get_runs impl_1]] || [get_property NEEDS_REFRESH [get_runs synth_1]]} {error "Project inputs require rebuilding; no stale export."}
open_run impl_1
source "$root/implementation_reports.tcl"
set setup_paths [get_timing_paths -delay_type max -max_paths 1]
set hold_paths [get_timing_paths -delay_type min -max_paths 1]
if {[llength $setup_paths]==0 || [llength $hold_paths]==0} {error "No timing paths."}
set wns [get_property SLACK $setup_paths];set whs [get_property SLACK $hold_paths]
if {$wns<=0 || $whs<=0} {error "Positive routed setup/hold margins required; deployment files withheld."}
if {[llength [get_drc_violations -quiet -filter {SEVERITY == Error}]]>0} {error "DRC errors; deployment files withheld."}
file copy -force "$root/vivado/v5/v5.runs/impl_1/system_wrapper.bit" "$root/deploy/cam_v5.bit"
file copy -force "$root/vivado/v5/v5.gen/sources_1/bd/system/hw_handoff/system.hwh" "$root/deploy/cam_v5.hwh"
set facts [open "$root/reports/routed_summary.json" w]
puts $facts [format {{"wns_ns":%.6f,"whs_ns":%.6f,"drc_errors":0,"run_complete":true,"needs_refresh":false,"part":"xc7z020clg400-1","tool":"Vivado 2025.2","clock_mhz":100,"actual_hardware":false,"production_signoff":false,"additional_report_audit_required":true}} $wns $whs]
close $facts
puts "V5_IMPLEMENTATION_CANDIDATE_READY matched bit/hwh; run tests/audit_implementation.py before packaging; warnings and board validation remain explicit."
