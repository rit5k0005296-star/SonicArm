"""Read all current board evidence and independently check the formal medians."""
from pathlib import Path
import json,statistics,hashlib
R=Path(__file__).resolve().parents[1]
P=R.parent/'FPGA-5/analysis/run_4c5e10fec13d43d9a055a4042888adb5'
data={p.name:json.loads(p.read_text(encoding='utf-8-sig')) for p in P.glob('*.json')}
raw=data['raw_samples.json'];perf=data['performance.json'];hw=data['hardware_correctness.json']
assert len(raw)==80 and hw['actual_hardware'] and hw['integer_exact'] and hw['debug_on_off_exact']
assert not perf['accuracy_matched_claim'] and perf['authentication_threshold'] is None
assert perf['strict_optimized_INT8_gate']['v5'] is False
rows=[]
for item in perf['summary']:
    samples=[x['model_ms'] for x in raw if x['audio']==item['audio'] and x['mode']==item['mode']]
    assert len(samples)==10
    median=statistics.median(samples)
    assert abs(median-item['median_ms'])<1e-7
    rows.append(dict(audio=item['audio'],mode=item['mode'],n=len(samples),median_ms=median))
records=data['profile_raw.json']['records']
assert len(records)==24 and data['setup.json']['scope']==perf['scope']
package=R.parent/'FPGA-5/board_package/fpga_v5/manifest.json'
assert hashlib.sha256(package.read_bytes()).hexdigest()==perf['v5_manifest_sha256']
report=dict(pass_=True,board_evidence_version=5,board_run=P.name,actual_v6_hardware=False,
    formal_rows=rows,profile_records=len(records),correctness_records=len(hw['records']),
    accuracy_matched_claim=False,authentication_threshold=None,package_sha256=perf['v5_manifest_sha256'],
    note='setup.actual_hardware=false is a pre-test snapshot; final V5 hardware correctness is true. No V6 board result exists.')
(R/'reports/v5_baseline_audit.json').write_text(json.dumps(report,indent=2))
print('V5_CURRENT_BOARD_BASELINE_AUDIT_PASS 80 formal samples, 24 profiles, exact package identity; quality failure retained')
