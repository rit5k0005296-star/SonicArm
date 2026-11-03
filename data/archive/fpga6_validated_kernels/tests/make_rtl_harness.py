"""Independent RTL-level AXI test; avoids the failing vendor UVM testbench.

The generated DUT is unchanged. The oracle is the existing INT64 Python FCM
reference. This does not turn a failed HLS cosim report into a passed report.
"""
from pathlib import Path
import importlib.util
import json
import re
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BASELINE = '--v5' in sys.argv
KROOT = ROOT.parent / 'FPGA-5' if BASELINE else ROOT
TOP = 'fcm_v5' if BASELINE else 'fcm_v6'
OUT = ROOT / ('rtl_v5_reference' if BASELINE else 'rtl_kernel_sim')
OUT.mkdir(exist_ok=True)
legacy = ROOT.parent / 'FPGA-4/fcm_engine/deploy/fcm_board.py'
spec = importlib.util.spec_from_file_location('fcm_reference', legacy)
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)
fields = reference.SCALARS


def hexfile(name, array):
    data = np.ascontiguousarray(array).view(np.uint8).ravel()
    p = OUT / (name + '.hex')
    p.write_text(''.join('%02x\n' % v for v in data) + '55\n' * 16, encoding='ascii')
    return 'V:/' + OUT.name + '/' + p.name


cases = []
for name in (ROOT / 'tests/fcm_cases/rtl_cases.txt').read_text().splitlines():
    path = ROOT / 'tests/fcm_cases' / name
    cfg = dict(zip(fields, map(int, (path / 'config.txt').read_text().split())))
    ci, co, f, t, k, s = (cfg[n] for n in fields[:6])
    of = (f + s - 1) // s
    values = dict(input_r=np.fromfile(path / 'input_int8.bin', np.int8).reshape(ci, f, t)[..., :5].copy(),
        residual=np.fromfile(path / 'residual_int8.bin', np.int8).reshape(co, of, t)[..., :5].copy(),
        weights=np.fromfile(path / 'weights_int8.bin', np.int8).reshape(co, ci, k, k),
        bias=np.fromfile(path / 'bias_int32.bin', '<i4'),
        multiplier=np.fromfile(path / 'multiplier_uint32.bin', '<u4'),
        post_lut=np.fromfile(path / 'post_lut_int8.bin', np.int8))
    cfg['frames'] = 5
    cases.append((name, cfg, values))
rng = np.random.default_rng(5020)
for i, args in enumerate([(3, 9, 7, 35, 3, 2, 11, -7, 38, 7),
                          (1, 1, 1, 2048, 1, 1, -128, 127, 40, 0),
                          (32, 32, 3, 33, 3, 1, -128, 0, 38, 2),
                          (1, 9, 7, 489, 3, 1, -11, 7, 38, 1),
                          (1, 9, 7, 529, 3, 1, -11, 7, 38, 3),
                          (3, 9, 7, 245, 3, 2, 11, -7, 38, 7),
                          (3, 9, 7, 265, 3, 2, 11, -7, 38, 7)]):
    cfg = dict(zip(fields, args))
    ci, co, f, t, k, s = args[:6]
    of = (f + s - 1) // s
    values = dict(input_r=rng.integers(-128, 128, (ci, f, t), dtype=np.int8),
        residual=rng.integers(-128, 128, (co, of, t), dtype=np.int8),
        weights=rng.integers(-128, 128, (co, ci, k, k), dtype=np.int8),
        bias=np.arange(co, dtype=np.int32) * 7919,
        multiplier=np.full(co, 1073741824, np.uint32),
        post_lut=rng.integers(-128, 128, 65536 if args[-1] & 4 else 256, dtype=np.int8))
    cases.append(('synthetic_' + str(i), cfg, values))

tb = ['`timescale 1ns/1ps', 'module tb_fcm_axi;', 'reg clk=0,resetn=0;always #5 clk=~clk;',
      'wire interrupt;reg [7:0] awaddr=0,araddr=0;reg awvalid=0,wvalid=0,arvalid=0,rready=0;',
      'reg [31:0] wdata=0;wire awready,wready,arready,rvalid,bvalid;',
      'wire [31:0] rdata;wire [1:0] bresp,rresp;', 'reg [31:0] rv;integer i,n,waited,old_reads,old_writes;reg [7:0] gold[0:1048575];']
ports = ['.ap_clk(clk)', '.ap_rst_n(resetn)', '.interrupt(interrupt)']
for signal in ('AWADDR', 'AWVALID', 'AWREADY', 'WDATA', 'WVALID', 'WREADY', 'ARADDR', 'ARVALID', 'ARREADY', 'RDATA', 'RVALID', 'RREADY', 'BRESP', 'BVALID', 'RRESP'):
    ports.append('.s_axi_control_' + signal + '(' + signal.lower() + ')')
ports += [".s_axi_control_WSTRB(4'hf)", ".s_axi_control_BREADY(1'b1)"]
signals = dict(AWADDR=64, AWID=1, AWLEN=8, AWSIZE=3, AWBURST=2, AWVALID=1, AWREADY=1,
    WDATA=64, WSTRB=8, WLAST=1, WVALID=1, WREADY=1, BID=1, BRESP=2, BVALID=1, BREADY=1,
    ARADDR=64, ARID=1, ARLEN=8, ARSIZE=3, ARBURST=2, ARVALID=1, ARREADY=1,
    RDATA=64, RID=1, RLAST=1, RVALID=1, RREADY=1, RRESP=2)
for bundle in ('input', 'params', 'output'):
    bindings = ['.clk(clk)', '.resetn(resetn)']
    for signal, width in signals.items():
        local = bundle + '_' + signal.lower()
        tb.append('wire ' + ('[%d:0] ' % (width-1) if width > 1 else '') + local + ';')
        ports.append('.m_axi_gmem_' + bundle + '_' + signal + '(' + local + ')')
        bindings.append('.' + signal.lower() + '(' + local + ')')
    ports += [".m_axi_gmem_" + bundle + "_RUSER(1'b0)", ".m_axi_gmem_" + bundle + "_BUSER(1'b0)"]
    tb.append('axi_ram_model mem_' + bundle + '(' + ','.join(bindings) + ');')
tb.append(TOP+' dut(' + ','.join(ports) + ');')
tb.append('''
task wr(input [7:0] addr,input [31:0] value);
 begin
  @(negedge clk);awaddr=addr;awvalid=1;
  @(posedge clk);while(!awready) @(posedge clk);
  @(negedge clk);awvalid=0;wdata=value;wvalid=1;
  @(posedge clk);while(!wready) @(posedge clk);
  @(negedge clk);wvalid=0;
  @(posedge clk);while(!bvalid) @(posedge clk);
 end
endtask
task rd(input [7:0] addr,output [31:0] value);
 begin
  @(negedge clk);araddr=addr;arvalid=1;rready=1;
  @(posedge clk);while(!arready) @(posedge clk);
  @(negedge clk);arvalid=0;
  @(posedge clk);while(!rvalid) @(posedge clk);value=rdata;
  @(negedge clk);rready=0;
 end
endtask
initial begin #300000000;$fatal(1,"Global timeout");end
initial begin
 repeat(10) @(negedge clk);resetn=1;
''')
control = (KROOT / ('hls/fcm/hls/syn/verilog/'+TOP+'_control_s_axi.v')).read_text()
offset = {k + '_DATA': int(v, 16) for k, v in re.findall(r"ADDR_(\w+)_DATA_0\s*=\s*8'h([0-9a-f]+)", control)}
addresses = dict(input_r=('input', 0x10000), residual=('output', 0x100000),
                 weights=('params', 0x10000), bias=('params', 0x20000), multiplier=('params', 0x30000),
                 post_lut=('params', 0x40000), output_r=('output', 0x10000), accumulator_out=('output', 0x200000))
for case_index, (name, cfg, values) in enumerate(cases):
    expected = reference.software_reference(values, cfg)
    n = expected['output_r'].size
    tb.append('$display("FCM_RTL_BEGIN %d %s");' % (case_index, name))
    tb.append('old_reads=mem_output.read_beats;old_writes=mem_output.write_beats;')
    for key, value in values.items():
        bundle, address = addresses[key]
        filename = hexfile('%d_%s' % (case_index, key), value)
        tb.append('$readmemh("%s",mem_%s.mem,%d,%d);' % (filename, bundle, address, address+value.nbytes+15))
    tb.append('for(i=0;i<%d;i=i+1) mem_output.mem[65536+i]=8\'h55;' % (n+16))
    tb.append('for(i=0;i<%d;i=i+1) mem_output.mem[2097152+i]=8\'h5a;' % (n*4+16))
    for key, (_, address) in addresses.items():
        off = offset[key.upper() + '_DATA']
        tb.append("wr(8'h%02x,32'h%08x);wr(8'h%02x,0);" % (off, address, off+4))
    for key, value in cfg.items():
        tb.append("wr(8'h%02x,32'h%08x);" % (offset[key.upper()+'_DATA'], value & 0xffffffff))
    tb.append("rd(8'h0c,rv);if(rv!=0) wr(8'h0c,rv);wr(8'h04,1);wr(8'h08,1);wr(8'h00,1);")
    tb.append('waited=0;while(!interrupt && waited<5000000) begin @(negedge clk);waited=waited+1;end')
    tb.append('if(!interrupt) $fatal(1,"Kernel timeout");rd(0,rv);if(!(rv&2)) $fatal(1,"No ap_done");rd(16,rv);if(rv!=0) $fatal(1,"Kernel status");')
    filename = hexfile('%d_expected_q' % case_index, expected['output_r'])
    tb.append('$readmemh("%s",gold,0,%d);' % (filename, n+15))
    tb.append('for(i=0;i<%d;i=i+1) if(mem_output.mem[65536+i]!==gold[i]) $fatal(1,"INT8 or guard mismatch case %d byte %%0d got %%h expected %%h",i,mem_output.mem[65536+i],gold[i]);' % (n+16,case_index))
    if cfg['flags'] & 2:
        filename = hexfile('%d_expected_a' % case_index, expected['accumulator_out'])
        tb.append('$readmemh("%s",gold,0,%d);' % (filename, n*4+15))
        tb.append('for(i=0;i<%d;i=i+1) if(mem_output.mem[2097152+i]!==gold[i]) $fatal(1,"INT32 mismatch case %d byte %%0d",i);' % (n*4,case_index))
    else:
        tb.append('for(i=0;i<%d;i=i+1) if(mem_output.mem[2097152+i]!==8\'h5a) $fatal(1,"Debug-off output modified");' % (n*4))
    tb.append('for(i=%d;i<%d;i=i+1) if(mem_output.mem[2097152+i]!==8\'h5a) $fatal(1,"INT32 guard overwritten");' % (n*4,n*4+16))
    tb.append('$display("FCM_RTL_CASE_PASS %d %s cycles=%%0d",waited);' % (case_index,name))
    tb.append('$display("FCM_RTL_BUS %d %s output_read_beats=%%0d output_write_beats=%%0d",mem_output.read_beats-old_reads,mem_output.write_beats-old_writes);' % (case_index,name))
    if not BASELINE and not cfg['flags'] & 6:
        rows = cfg['cout']*((cfg['freq']+cfg['stride_f']-1)//cfg['stride_f'])
        expected_writes = sum(((r*cfg['frames'])%8+cfg['frames']+7)//8 for r in range(rows))
        tb.append('if(mem_output.write_beats-old_writes!=%d) $fatal(1,"Row packing write count");' % expected_writes)
        tb.append('if(mem_output.read_beats-old_reads>%d) $fatal(1,"Repeated fragment RMW reads remain");' % (2*rows))
marker='V5_REFERENCE_FCM_RTL_PASS' if BASELINE else 'V6_FCM_INDEPENDENT_RTL_PASS'
tb += ['$display("'+marker+' cases=12 real=5 synthetic=7 AXI_backpressure INT8_INT32 guards debug_off row_traffic");$finish;', 'end', 'endmodule']
(OUT / 'tb_fcm_axi.sv').write_text('\n'.join(tb)+'\n', encoding='ascii')
(OUT / 'cases.json').write_text(json.dumps([dict(name=n,config=c) for n,c,_ in cases], indent=2), encoding='utf8')
files = list((KROOT / 'hls/fcm/hls/syn/verilog').glob('*.v')) + [ROOT / 'rtl/axi_ram_model.sv', OUT / 'tb_fcm_axi.sv']
def shortpath(p):
    if BASELINE and p.is_relative_to(KROOT): return 'W:/'+p.relative_to(KROOT).as_posix()
    return 'V:/'+p.relative_to(ROOT).as_posix()
(OUT / 'sources.prj').write_text(''.join('sv xil_defaultlib "%s"\n' % shortpath(p) for p in files), encoding='ascii')
print('V6_RTL_HARNESS_READY', len(cases))
