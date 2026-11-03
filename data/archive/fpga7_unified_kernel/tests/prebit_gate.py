"""Reject incomplete route, timing/coverage or DRC errors before bit generation."""
from pathlib import Path
import json
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from audit_implementation import timing_metrics, findings
R=Path(__file__).resolve().parents[1]/'reports'
metrics=timing_metrics((R/'timing_routed.rpt').read_text())
checks=dict((k,int(v)) for k,v in re.findall(r'checking (\w+) \((\d+)\)',(R/'check_timing_routed.rpt').read_text()))
assert len(checks)>=12 and not any(checks.values()), checks
route=(R/'route_status_routed.rpt').read_text()
counts={k:int(re.search(r'# of '+k+r'\.+\s*:\s*(\d+)',route)[1]) for k in ('routable nets','fully routed nets','nets with routing errors')}
assert counts['routable nets']==counts['fully routed nets'] and not counts['nets with routing errors']
drc=findings((R/'drc_routed.rpt').read_text())
assert not any(v['severity'] in ('Error','Critical Warning') for v in drc.values()),drc
methodology=findings((R/'methodology_routed.rpt').read_text())
assert not any(v['severity'] in ('Error','Critical Warning') for v in methodology.values()),methodology
assert set(drc).issubset({'DPIP-1','DPOP-1','DPOP-2','PDCN-1569','REQP-1839','RTSTAT-10'}),drc
assert set(methodology).issubset({'LUTAR-1'}),methodology
assert 'All paths are Safely Timed.' in (R/'cdc_routed.rpt').read_text()
assert re.search(r'^clk_fpga_0\s+10\.000\s+\{0\.000 5\.000\}',(R/'clocks_routed.rpt').read_text(),re.M)
assert 'Clean' in (R/'clock_interaction_routed.rpt').read_text()
assert 'No bus skew constraints' in (R/'bus_skew_routed.rpt').read_text()
exceptions=(R/'exceptions_routed.rpt').read_text()
exception_rows=[line for line in exceptions.splitlines() if re.match(r'^\d+\s',line)]
assert exception_rows and all('src_arst' in line or 'syncstages_ff_reg[0]' in line for line in exception_rows),exception_rows
assert 'Ignored' not in exceptions and 'Invalid' not in exceptions
text=(R/'implemented_constraints.xdc').read_text()
assert 'create_clock -period 10.000 -name clk_fpga_0' in text
assert not re.search(r'CLOCK_DEDICATED_ROUTE\s+(FALSE|false|0)',text)
(R/'prebit_gate.json').write_text(json.dumps(dict(pass_=True,metrics=metrics,timing_coverage=checks,route=counts,
    cdc_safely_timed=True,vendor_reset_exception_rows=len(exception_rows),drc_warnings=drc,methodology_warnings=methodology,actual_hardware=False),indent=2))
print('V7_PREBIT_ROUTE_TIMING_COVERAGE_GATE_PASS')
