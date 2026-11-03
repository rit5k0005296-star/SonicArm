# The IP presents one AXI-Lite slave plus eight read-only monitor interfaces.
create_project perf_pack "$root/vivado/perf_pack" -part xc7z020clg400-1 -force
add_files -norecurse [list "$root/rtl/axi_perf_monitor.v" "$root/rtl/axi_perf_wrapper.v"]
set_property top axi_perf_wrapper [current_fileset]
update_compile_order -fileset sources_1
ipx::package_project -root_dir "$root/rtl/ip" -vendor sonicarm.org -library user -taxonomy /UserIP -import_files -set_current true -force
set perf_core [ipx::current_core]
set_property name axi_perf_monitor $perf_core
set_property version 1.1 $perf_core
foreach bus [ipx::get_bus_interfaces MON_* -of_objects $perf_core] {
    set_property interface_mode monitor $bus
}
set perf_map [ipx::get_memory_maps S_AXI -of_objects $perf_core]
if {[llength $perf_map]==0} {set perf_map [ipx::add_memory_map S_AXI $perf_core]}
set perf_block [ipx::get_address_blocks Reg -of_objects $perf_map]
if {[llength $perf_block]==0} {set perf_block [ipx::add_address_block Reg $perf_map]}
set_property range 256 $perf_block
set_property width 32 $perf_block
set_property usage register $perf_block
set_property slave_memory_map_ref S_AXI [ipx::get_bus_interfaces S_AXI -of_objects $perf_core]
ipx::save_core $perf_core
close_project
