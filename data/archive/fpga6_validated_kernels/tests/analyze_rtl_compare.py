"""Same deterministic AXI testbench comparison. Never a board speed claim."""
from pathlib import Path
import hashlib,json,re,xml.etree.ElementTree as ET
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def parse(name,marker):
    s=(R/'logs'/name).read_text(errors='replace')
    assert marker in s and 'Fatal:' not in s
    cycles={int(i):dict(name=n,cycles=int(c)) for i,n,c in re.findall(r'FCM_RTL_CASE_PASS (\d+) (\S+) cycles=(\d+)',s)}
    for i,n,rd,wr in re.findall(r'FCM_RTL_BUS (\d+) (\S+) output_read_beats=(\d+) output_write_beats=(\d+)',s):
        assert cycles[int(i)]['name']==n
        cycles[int(i)].update(output_read_beats=int(rd),output_write_beats=int(wr))
    assert len(cycles)==12 and all(len(v)==4 for v in cycles.values())
    return cycles
a=parse('v5_reference_rtl.log','V5_REFERENCE_FCM_RTL_PASS')
b=parse('fcm_independent_rtl.log','V6_FCM_INDEPENDENT_RTL_PASS')
cases=json.loads((R/'rtl_kernel_sim/cases.json').read_text())
assert cases==json.loads((R/'rtl_v5_reference/cases.json').read_text())
rows=[]
for i,c in enumerate(cases):
    assert a[i]['name']==b[i]['name']==c['name']
    rows.append(dict(**c,v5=a[i],v6=b[i],v5_over_v6_cycles=a[i]['cycles']/b[i]['cycles']))
report=dict(pass_=True,actual_hardware=False,cases=rows,
 scope='Both generated RTL DUTs; identical 100MHz clock, byte RAM and deterministic independent AXI stalls; all INT8/INT32 and guards checked',
 caveat='Single-outstanding synthetic RAM is not PS7 DDR. These cycle ratios do not establish board or complete CAM++ speedup.',
 fcm_source_sha256=sha(R/'src/fcm.cpp'),reference_v5_source_sha256=sha(R.parent/'FPGA-5/src/fcm.cpp'),
 ram_model_sha256=sha(R/'rtl/axi_ram_model.sv'),
 generated_rtl_sha256={v:{p.name:sha(p) for p in sorted(d.glob('*.v'))} for v,d in [('v5',R.parent/'FPGA-5/hls/fcm/hls/syn/verilog'),('v6',R/'hls/fcm/hls/syn/verilog')]})
(R/'reports/rtl_v5_v6_comparison.json').write_text(json.dumps(report,indent=2))
for r in rows:print(r['name'],'V5/V6 cycles %.3fx'%r['v5_over_v6_cycles'],r['v5']['cycles'],r['v6']['cycles'])
print('V6_SAME_HARNESS_RTL_COMPARISON_PASS no_board_claim')
