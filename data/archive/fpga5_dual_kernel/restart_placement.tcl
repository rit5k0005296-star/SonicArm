# Retain the current synthesized/optimized new RTL; discard a physical reference.
set root [file normalize [file dirname [info script]]]
open_project "$root/vivado/v5/v5.xpr"
set run [get_runs impl_1]
foreach name {runme.log system_wrapper.tcl} {
    file copy -force "$root/vivado/v5/v5.runs/impl_1/$name" "$root/reports/incremental_clock_$name"
}
set_property INCREMENTAL_CHECKPOINT {} $run
if {[lsearch -exact [list_property $run] AUTO_INCREMENTAL_CHECKPOINT]>=0} {
    set_property AUTO_INCREMENTAL_CHECKPOINT 0 $run
}
reset_runs -from_step place_design $run
launch_runs $run -to_step write_bitstream -jobs 1
wait_on_run $run
if {![string match "*write_bitstream Complete*" [get_property STATUS $run]]} {error "V5 ordinary implementation failed."}
source "$root/collect_vivado.tcl"
