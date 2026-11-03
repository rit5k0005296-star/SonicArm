# FPGA-10 PYNQ-Z2 audio + HDMI OUT constraints.
# Audio and HDMI pins are copied from the official PYNQ v3.0.1 base overlay
# at commit 93ddd21ab623883590a8c8b07f0b157b2855da4b.

# ADAU1761 I2C and audio serial interface
set_property -dict {PACKAGE_PIN U9 IOSTANDARD LVCMOS33} [get_ports IIC_1_scl_io]
set_property PULLUP true [get_ports IIC_1_scl_io]
set_property -dict {PACKAGE_PIN T9 IOSTANDARD LVCMOS33} [get_ports IIC_1_sda_io]
set_property PULLUP true [get_ports IIC_1_sda_io]
set_property -dict {PACKAGE_PIN U5 IOSTANDARD LVCMOS33} [get_ports audio_clk_10MHz]
set_property -dict {PACKAGE_PIN R18 IOSTANDARD LVCMOS33} [get_ports bclk]
set_property -dict {PACKAGE_PIN T17 IOSTANDARD LVCMOS33} [get_ports lrclk]
set_property -dict {PACKAGE_PIN G18 IOSTANDARD LVCMOS33} [get_ports sdata_o]
set_property -dict {PACKAGE_PIN F17 IOSTANDARD LVCMOS33} [get_ports sdata_i]
set_property -dict {PACKAGE_PIN M17 IOSTANDARD LVCMOS33} [get_ports {codec_addr[0]}]
set_property -dict {PACKAGE_PIN M18 IOSTANDARD LVCMOS33} [get_ports {codec_addr[1]}]

# HDMI TX
set_property -dict {PACKAGE_PIN L17 IOSTANDARD TMDS_33} [get_ports hdmi_out_clk_n]
set_property -dict {PACKAGE_PIN L16 IOSTANDARD TMDS_33} [get_ports hdmi_out_clk_p]
set_property -dict {PACKAGE_PIN K18 IOSTANDARD TMDS_33} [get_ports {hdmi_out_data_n[0]}]
set_property -dict {PACKAGE_PIN K17 IOSTANDARD TMDS_33} [get_ports {hdmi_out_data_p[0]}]
set_property -dict {PACKAGE_PIN J19 IOSTANDARD TMDS_33} [get_ports {hdmi_out_data_n[1]}]
set_property -dict {PACKAGE_PIN K19 IOSTANDARD TMDS_33} [get_ports {hdmi_out_data_p[1]}]
set_property -dict {PACKAGE_PIN H18 IOSTANDARD TMDS_33} [get_ports {hdmi_out_data_n[2]}]
set_property -dict {PACKAGE_PIN J18 IOSTANDARD TMDS_33} [get_ports {hdmi_out_data_p[2]}]
set_property -dict {PACKAGE_PIN R19 IOSTANDARD LVCMOS33} [get_ports {hdmi_out_hpd[0]}]
