"""Expose passive AXI Monitor interfaces; never split individual BD bus nets."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'rtl/axi_perf_monitor.v').read_text()
header = source.split('module axi_perf_monitor(', 1)[1].split('    input wire pw_wvalid', 1)[0]
header = header.replace('output reg ', 'output wire ')
interfaces = ['S_AXI', 'MON_PW_CTRL', 'MON_FCM_CTRL']
memory = [(ip, group) for ip in ('PW', 'FCM') for group in ('INPUT', 'PARAMS', 'OUTPUT')]
interfaces += ['MON_'+ip+'_'+group for ip, group in memory]
header = header.replace('ASSOCIATED_BUSIF S_AXI,', 'ASSOCIATED_BUSIF '+':'.join(interfaces)+',')
ports = [header.rstrip()]
connections = ['.%s(%s)' % (n,n) for n in re.findall(r'(?:input|output)\s+(?:wire|reg)\s*(?:\[[^]]+\])?\s+(\w+)', header)]
tb_connections = []
ctrl_signals = [('AWADDR',8),('AWPROT',3),('AWVALID',1),('AWREADY',1),
                ('WDATA',32),('WSTRB',4),('WVALID',1),('WREADY',1),
                ('BRESP',2),('BVALID',1),('BREADY',1),('ARADDR',8),('ARPROT',3),
                ('ARVALID',1),('ARREADY',1),('RDATA',32),('RRESP',2),('RVALID',1),('RREADY',1)]
for ip in ('PW', 'FCM'):
    for signal, width in ctrl_signals:
        name = ip.lower()+'_'+signal.lower()
        attr = '(* X_INTERFACE_MODE="monitor" *) ' if signal == 'WVALID' else ''
        ports.append('    '+attr+'(* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 MON_'+ip+'_CTRL '+signal+'" *) input wire '+('[%d:0] ' % (width-1) if width>1 else '')+name+',')
        if signal in ('WVALID','WREADY','WDATA','WSTRB'):
            connections.append('.%s(%s)' % (name,name))
        else:
            tb_connections.append('.'+name+"("+str(width)+"'d0)")
    ports.append('    input wire '+ip.lower()+'_irq,')
    connections.append('.'+ip.lower()+'_irq('+ip.lower()+'_irq)')
signals = ['ARVALID','ARREADY','RVALID','RREADY','RLAST','AWVALID','AWREADY','WVALID','WREADY']
data_signals = [('AWADDR',64),('AWID',1),('AWLEN',8),('AWSIZE',3),('AWBURST',2),('AWVALID',1),('AWREADY',1),
                ('WDATA',64),('WSTRB',8),('WLAST',1),('WVALID',1),('WREADY',1),
                ('BID',1),('BRESP',2),('BVALID',1),('BREADY',1),
                ('ARADDR',64),('ARID',1),('ARLEN',8),('ARSIZE',3),('ARBURST',2),('ARVALID',1),('ARREADY',1),
                ('RDATA',64),('RID',1),('RRESP',2),('RLAST',1),('RVALID',1),('RREADY',1)]
for bit, (ip,group) in enumerate(memory):
    for signal,width in data_signals:
        name = ip.lower()+'_'+group.lower()+'_'+signal.lower()
        attr = '(* X_INTERFACE_MODE="monitor" *) ' if signal == 'ARVALID' else ''
        ports.append('    '+attr+'(* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 MON_'+ip+'_'+group+' '+signal+'" *) input wire '+('[%d:0] ' % (width-1) if width>1 else '')+name+',')
        tb_connections.append('.'+name+'(mon_'+signal.lower()+'[%d])' % bit if signal in signals else '.'+name+"("+str(width)+"'d0)")
for signal in signals:
    names = [ip.lower()+'_'+group.lower()+'_'+signal.lower() for ip,group in reversed(memory)]
    connections.append('.mon_'+signal.lower()+'({'+','.join(names)+'})')
ports[-1] = ports[-1].rstrip(',')
text = '`timescale 1ns/1ps\n// Passive monitoring via complete interface nets, never per-pin BD overrides.\nmodule axi_perf_wrapper(\n'+'\n'.join(ports)+'\n);\naxi_perf_monitor counters(\n'+',\n'.join(connections)+'\n);\nendmodule\n'
(ROOT / 'rtl/axi_perf_wrapper.v').write_text(text, encoding='ascii')
tb = (ROOT / 'rtl/tb_axi_perf_monitor.sv').read_text().replace('module tb_axi_perf_monitor;', 'module tb_axi_perf_wrapper;')
tb = tb.replace('axi_perf_monitor dut(.*);', 'axi_perf_wrapper dut(.*, '+', '.join(tb_connections)+');')
tb = tb.replace('V6_MONITOR_RTL_PASS', 'V6_MONITOR_WRAPPER_RTL_PASS')
(ROOT / 'rtl/tb_axi_perf_wrapper.sv').write_text(tb, encoding='ascii')
print('V6_PASSIVE_MONITOR_WRAPPER_READY', len(interfaces)-1, 'monitor interfaces')
