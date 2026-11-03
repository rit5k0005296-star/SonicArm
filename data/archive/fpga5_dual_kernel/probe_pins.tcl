set root [file normalize [file dirname [info script]]]
create_project -in_memory -part xc7z020clg400-1
set_property ip_repo_paths [list "C:/Users/Lenovo/Desktop/SonicArm/pynq_voiceprint/CAM-pretrained_models/FPGA-4/fcm_engine/vendor/pointwise_v3"] [current_project]
update_ip_catalog
create_bd_design probe
create_bd_cell -type ip -vlnv xilinx.com:hls:pointwise:1.0 pw
puts "V5_PROBE_PINS [get_bd_pins -quiet pw/m_axi_gmem_input_RVALID]"
puts "V5_PROBE_WVALID [get_bd_pins -quiet pw/s_axi_control_WVALID]"
puts "V5_PROBE_ALL [get_bd_pins -quiet pw/*]"
close_project
exit
