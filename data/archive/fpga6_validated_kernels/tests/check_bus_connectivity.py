"""Check generated top-level wiring: master, slave and passive probe share nets."""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
p = ROOT / 'vivado/v6/v6.gen/sources_1/bd/system/synth/system.v'
if not p.is_file():
    p = p.with_suffix('.sv')
s = p.read_text()
instances = {}
for name in ('pointwise_0','fcm_0','axi_control','perf_0','mem_hp0','mem_hp1','mem_hp2'):
    block = re.search(r'\b\w+\s+'+name+r'\s*\((.*?)\);',s,re.S)
    if block is None:
        raise ValueError('Missing generated instance '+name)
    instances[name] = {port.lower():net.strip() for port,net in re.findall(r'\.(\w+)\s*\(([^)]*)\)',block[1])}
records=[]
unused=[]
def same(label, endpoints):
    nets=[instances[cell][port.lower()] for cell,port in endpoints]
    if any(not n for n in nets) or len(set(nets)) != 1:
        raise AssertionError('Disconnected or overridden AXI net '+label+': '+repr(nets))
    records.append(dict(signal=label,net=nets[0],endpoints=[c+'/'+p for c,p in endpoints]))
for index,(ip,prefix) in enumerate([('pointwise_0','pw'),('fcm_0','fcm')]):
    for signal in ('WVALID','WREADY','WDATA','WSTRB'):
        same(ip+'/control/'+signal,[(ip,'s_axi_control_'+signal),
             ('axi_control','M%02d_AXI_'%index+signal),('perf_0',prefix+'_'+signal)])
    for hp,bundle in enumerate(('input','params','output')):
        for signal in ('ARVALID','ARREADY','RVALID','RREADY','RLAST','AWVALID','AWREADY','WVALID','WREADY'):
            if bundle != 'output' and signal in ('AWREADY','WREADY'):
                values=[instances[ip]['m_axi_gmem_'+bundle+'_'+signal.lower()],
                        instances['perf_0'][prefix+'_'+bundle+'_'+signal.lower()]]
                if values != ["1'b0","1'b0"]:
                    raise AssertionError('Unused read-only write READY is not tied off')
                unused.append(ip+'/'+bundle+'/'+signal)
                continue
            same(ip+'/'+bundle+'/'+signal,[(ip,'m_axi_gmem_'+bundle+'_'+signal),
                 ('mem_hp%d'%hp,'S%02d_AXI_'%index+signal),('perf_0',prefix+'_'+bundle+'_'+signal)])
(ROOT/'reports/bus_connectivity.json').write_text(json.dumps(dict(pass_=True,actual_hardware=False,
    signals=len(records),records=records,unused_read_only_ready_tied_low=unused),indent=2)+'\n',encoding='utf8')
print('V6_BUS_CONNECTIVITY_PASS',len(records),'master/slave/passive monitor signal triples')
