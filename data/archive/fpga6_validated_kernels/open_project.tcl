set root [file normalize [file dirname [info script]]]
open_project "$root/vivado/v6/v6.xpr"
open_bd_design [get_files system.bd]
