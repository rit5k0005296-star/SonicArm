set root [file normalize [file dirname [info script]]]
set project "$root/vivado/v5/v5.xpr"
if {[llength [get_projects -quiet]]==0} {open_project $project}
if {[file normalize [get_property DIRECTORY [current_project]]] ne [file dirname $project]} {error "Wrong project."}
if {![string match "*Complete*" [get_property STATUS [get_runs synth_1]]]} {
launch_runs synth_1 -jobs 2
    wait_on_run synth_1
    if {![string match "*Complete*" [get_property STATUS [get_runs synth_1]]]} {error "V5 synthesis failed."}
}
if {![string match "*write_bitstream Complete*" [get_property STATUS [get_runs impl_1]]]} {
    launch_runs impl_1 -to_step write_bitstream -jobs 1
    wait_on_run impl_1
    if {![string match "*write_bitstream Complete*" [get_property STATUS [get_runs impl_1]]]} {error "V5 implementation failed."}
}
source "$root/collect_vivado.tcl"
