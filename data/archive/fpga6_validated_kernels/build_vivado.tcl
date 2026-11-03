set root [file normalize [file dirname [info script]]]
set project "$root/vivado/v6/v6.xpr"
if {[llength [get_projects -quiet]]==0} {open_project $project}
if {[file normalize [get_property DIRECTORY [current_project]]] ne [file dirname $project]} {error "Wrong project."}
if {![string match "*Complete*" [get_property STATUS [get_runs synth_1]]]} {
launch_runs synth_1 -jobs 2
    wait_on_run synth_1
    if {![string match "*Complete*" [get_property STATUS [get_runs synth_1]]]} {error "V6 synthesis failed."}
}
if {![string match "*write_bitstream Complete*" [get_property STATUS [get_runs impl_1]]]} {
  if {![string match "*route_design Complete*" [get_property STATUS [get_runs impl_1]]]} {
    launch_runs impl_1 -to_step route_design -jobs 1
    wait_on_run impl_1
    if {![string match "*route_design Complete*" [get_property STATUS [get_runs impl_1]]]} {error "V6 routing failed."}
  }
    open_run impl_1
    source "$root/implementation_reports.tcl"
    # Vivado sets its own PYTHONHOME/PYTHONPATH (Python 3.13). Isolate the
    # external 3.11 validator; preserve the actual gate and all design state.
    if {[catch {exec E:/condaData/envs_dirs/python3.11/python.exe -I -B "$root/tests/prebit_gate.py"} gate]} {error "V6 pre-bitstream gate failed: $gate"}
    puts $gate
    close_design
    launch_runs impl_1 -to_step write_bitstream -jobs 1
    wait_on_run impl_1
    if {![string match "*write_bitstream Complete*" [get_property STATUS [get_runs impl_1]]]} {error "V6 implementation failed."}
}
source "$root/collect_vivado.tcl"
