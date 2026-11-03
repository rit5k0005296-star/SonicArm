# Read-only inspection of the current project and final implementation reports.
set root [file normalize [file dirname [info script]]]
open_project "$root/vivado/v5/v5.xpr"
set run [get_runs impl_1]
puts "V5_IMPL_STATUS=[get_property STATUS $run]"
puts "V5_IMPL_PROGRESS=[get_property PROGRESS $run]"
puts "V5_IMPL_NEEDS_REFRESH=[get_property NEEDS_REFRESH $run]"
report_property $run -file "$root/reports/implementation_run_properties.rpt"
open_run impl_1
source "$root/implementation_reports.tcl"
puts "V5_IMPLEMENTATION_INSPECTION_COMPLETE no design mutation or hardware access"
