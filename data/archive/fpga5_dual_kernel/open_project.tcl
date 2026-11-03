set root [file normalize [file dirname [info script]]]
open_project "$root/vivado/v5/v5.xpr"
open_bd_design [get_files system.bd]
