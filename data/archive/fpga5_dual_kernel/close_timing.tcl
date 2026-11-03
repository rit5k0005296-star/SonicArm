# Resume only after routing; preserve functional RTL and the routed checkpoint.
set root [file normalize [file dirname [info script]]]
set project "$root/vivado/v5/v5.xpr"
open_project $project
set run [get_runs impl_1]
if {![file exists "$root/vivado/v5/v5.runs/impl_1/system_wrapper_routed.dcp"]} {
    error "A complete routed checkpoint is required."
}
set_property STEPS.POST_ROUTE_PHYS_OPT_DESIGN.IS_ENABLED true $run
set_property STEPS.POST_ROUTE_PHYS_OPT_DESIGN.ARGS.DIRECTIVE AggressiveExplore $run
foreach name {system_wrapper_timing_summary_routed.rpt system_wrapper_utilization_placed.rpt runme.log} {
    set source "$root/vivado/v5/v5.runs/impl_1/$name"
    if {[file exists $source]} {file copy -force $source "$root/reports/before_postroute_$name"}
}
reset_runs -from_step {phys_opt_design (Post-Route)} $run
launch_runs $run -to_step write_bitstream -jobs 1
wait_on_run $run
if {![string match "*write_bitstream Complete*" [get_property STATUS $run]]} {error "V5 post-route closure failed."}
source "$root/collect_vivado.tcl"
