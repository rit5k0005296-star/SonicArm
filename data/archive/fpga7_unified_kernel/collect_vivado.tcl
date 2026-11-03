set root [file normalize [file dirname [info script]]]
set project "$root/vivado/v7_final/v7.xpr"
if {[llength [get_projects -quiet]]==0} {open_project $project}
if {[get_property NAME [current_project]] ne "v7"} {error "Wrong Vivado project name."}
if {[get_property PART [current_project]] ne "xc7z020clg400-1"} {error "Wrong V7 FPGA part."}
if {[get_property TOP [get_filesets sources_1]] ne "system_wrapper"} {error "Wrong V7 top module."}
if {![string match "*write_bitstream Complete*" [get_property STATUS [get_runs impl_1]]]} {error "Bitstream incomplete."}
if {[get_property NEEDS_REFRESH [get_runs impl_1]] || [get_property NEEDS_REFRESH [get_runs synth_1]]} {
    error "Project inputs require rebuilding; no stale export."
}
open_run impl_1
source "$root/implementation_reports.tcl"
set setup_paths [get_timing_paths -delay_type max -max_paths 1]
set hold_paths [get_timing_paths -delay_type min -max_paths 1]
if {[llength $setup_paths]==0 || [llength $hold_paths]==0} {error "No timing paths."}
set wns [get_property SLACK $setup_paths]
set whs [get_property SLACK $hold_paths]
if {$wns<=0 || $whs<=0} {error "Positive routed setup/hold margins required; deployment files withheld."}
if {[llength [get_drc_violations -quiet -filter {SEVERITY == Error}]]>0} {error "DRC errors; deployment files withheld."}
file mkdir "$root/deploy"
file copy -force "$root/vivado/v7_final/v7.runs/impl_1/system_wrapper.bit" "$root/deploy/cam_v7.bit"
file copy -force "$root/vivado/v7_final/v7.gen/sources_1/bd/system/hw_handoff/system.hwh" "$root/deploy/cam_v7.hwh"
set facts [open "$root/reports/routed_summary.json" w]
puts $facts [format {{"wns_ns":%.6f,"whs_ns":%.6f,"drc_errors":0,"run_complete":true,"needs_refresh":false,"part":"xc7z020clg400-1","tool":"Vivado 2025.2","clock_mhz":100,"actual_hardware":false,"profile_monitor":false,"production_signoff":false}} $wns $whs]
close $facts
puts "V7_IMPLEMENTATION_CANDIDATE_READY matched bit/hwh; board untested."
