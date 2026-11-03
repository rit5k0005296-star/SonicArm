"""Record a Python launch repair; all netlist/constraint inputs must stay exact."""
from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
before=json.loads((R/'experiments/03_python_environment_repair/design_inputs.json').read_text())
after={name:sha(R/name) for name in before}
changed=[k for k in before if before[k]!=after[k]]
assert changed==['build_vivado.tcl'],changed
record=dict(reason='Vivado Python 3.13 PYTHONHOME/PYTHONPATH leaked into external Python 3.11; use -I and explicitly add validator script directory',
    changed_flow_scripts=changed,old_sha256={k:before[k] for k in changed},new_sha256={k:after[k] for k in changed},
    other_design_inputs_unchanged=len(after)-len(changed),kernel_constraints_and_ip_unchanged=True,
    gate_criteria_unchanged=True,vivado_run_metadata_manually_changed=False,
    routed_checkpoint_sha256=sha(R/'vivado/v6/v6.runs/impl_1/system_wrapper_routed.dcp'),actual_hardware=False)
(R/'reports/python_environment_repair.json').write_text(json.dumps(record,indent=2))
(R/'reports/design_inputs.json').write_text(json.dumps(after,indent=2))
print('V6_FLOW_ENVIRONMENT_REPAIR_RECORDED only external Python invocation; physical inputs unchanged')
