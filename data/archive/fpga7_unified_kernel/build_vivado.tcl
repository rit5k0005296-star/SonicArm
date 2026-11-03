set root [file normalize [file dirname [info script]]]
set project "$root/vivado/v7_final/v7.xpr"
if {[llength [get_projects -quiet]]==0} {open_project $project}
if {[get_property NAME [current_project]] ne "v7"} {error "Wrong Vivado project name."}
if {[get_property PART [current_project]] ne "xc7z020clg400-1"} {error "Wrong V7 FPGA part."}
if {[get_property TOP [get_filesets sources_1]] ne "system_wrapper"} {error "Wrong V7 top module."}
if {![string match "*Complete*" [get_property STATUS [get_runs synth_1]]]} {
    launch_runs synth_1 -jobs 2
    wait_on_run synth_1
    if {![string match "*Complete*" [get_property STATUS [get_runs synth_1]]]} {error "V7 synthesis failed."}
}
if {![string match "*write_bitstream Complete*" [get_property STATUS [get_runs impl_1]]]} {
    if {![string match "*route_design Complete*" [get_property STATUS [get_runs impl_1]]]} {
        launch_runs impl_1 -to_step route_design -jobs 1
        wait_on_run impl_1
        if {![string match "*route_design Complete*" [get_property STATUS [get_runs impl_1]]]} {error "V7 routing failed."}
    }
    open_run impl_1
    source "$root/implementation_reports.tcl"
    if {[catch {exec E:/condaData/envs_dirs/python3.11/python.exe -I -B "$root/tests/prebit_gate.py"} gate]} {
        error "V7 pre-bitstream gate failed: $gate"
    }
    puts $gate
    close_design
    launch_runs impl_1 -to_step write_bitstream -jobs 1
    wait_on_run impl_1
    if {![string match "*write_bitstream Complete*" [get_property STATUS [get_runs impl_1]]]} {error "V7 implementation failed."}
}
source "$root/collect_vivado.tcl"
