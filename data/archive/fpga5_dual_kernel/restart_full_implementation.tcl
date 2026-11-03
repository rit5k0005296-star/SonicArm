# Re-enter init_design with the current synthesized sources and no incremental
# reference. Preserve the positive-timing physical candidate and its diagnostics.
set root [file normalize [file dirname [info script]]]
open_project "$root/vivado/v5/v5.xpr"
set run [get_runs impl_1]
puts "V5_PARENT_STATUS=[get_property STATUS [get_runs synth_1]]"
if {[get_property NEEDS_REFRESH [get_runs synth_1]]} {
    error "Synthesis inputs changed; full synthesis must be rebuilt first."
}
set archive "$root/reports/masked_normal_candidate"
file mkdir $archive
foreach name {system_wrapper_postroute_physopt.dcp system_wrapper.bit system_wrapper_timing_summary_postroute_physopted.rpt runme.log gen_run.xml system_wrapper.tcl} {
    file copy -force "$root/vivado/v5/v5.runs/impl_1/$name" "$archive/$name"
}
foreach name {timing_routed.rpt drc_routed.rpt methodology_routed.rpt cdc_routed.rpt route_status_routed.rpt implementation_run_properties.rpt} {
    file copy -force "$root/reports/$name" "$archive/$name"
}
set_property INCREMENTAL_CHECKPOINT {} $run
set_property AUTO_INCREMENTAL_CHECKPOINT 0 $run
set_property STEPS.POST_ROUTE_PHYS_OPT_DESIGN.IS_ENABLED true $run
set_property STEPS.POST_ROUTE_PHYS_OPT_DESIGN.ARGS.DIRECTIVE AggressiveExplore $run
reset_runs $run
launch_runs $run -to_step write_bitstream -jobs 1
wait_on_run $run
puts "V5_FINAL_RUN_STATUS=[get_property STATUS $run]"
if {![string match "*write_bitstream Complete*" [get_property STATUS $run]]} {
    error "Fresh implementation did not finish cleanly; preserved candidate retained."
}
source "$root/collect_vivado.tcl"
