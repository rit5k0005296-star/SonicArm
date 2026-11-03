"""Desktop-only exercise of the production baseline profile/report pipeline.

Real native ORT and independent software integer models. Hardware chunk counts
are injected solely to exercise report orchestration. No board evidence created.
"""
from pathlib import Path
from contextlib import contextmanager
import json
import sys

sys.dont_write_bytecode = True
WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[1]
sys.path.insert(0, str(ROOT.parents[1] / 'consistency-test/codex'))
from common import import_runtime
import_runtime('cpu')
sys.path.insert(0, str(WORK))
import numpy as np
import optimization_profile as tests
from native_ort_bridge import API, Session


def main():
    tests.validate_files()
    output = WORK / 'diagnostics/profile_flow'
    output.mkdir(parents=True, exist_ok=True)
    prior = output / 'desktop_reference'
    prior.mkdir(exist_ok=True)
    api = API(ROOT / 'desktop_validation/ort_audit/windows1171/onnxruntime-win-x64-1.17.1/lib/onnxruntime.dll', verify=False)
    factory = lambda path, threads=1, optimize=False: Session(path, threads, optimize, api=api)
    _, _, features = tests.bench.data()
    capacity = max(x.shape[1] for x in features.values())
    original_execution, original_make = tests.execution, tests.make
    for mode in ('cpu_int8', 'v3_off', 'v4_off'):
        with original_execution(tests.optimized(mode), factory=factory):
            model = original_make(mode, capacity, hardware=False)
            try:
                for name, x in features.items():
                    raw, _ = model.run(x, audit=False)
                    old_mode = mode.split('_')[0] if mode.startswith(('v3_', 'v4_')) else mode
                    np.save(prior / (old_mode + '.' + name + '.npy'), raw, allow_pickle=False)
            finally:
                tests.bench.close(model)

    @contextmanager
    def desktop_execution(optimize, collector=None):
        with original_execution(optimize, collector, factory) as value:
            yield value

    def desktop_make(mode, capacity, hardware=True, debug=False):
        model = original_make(mode, capacity, hardware=False, debug=False)
        original_run = model.run

        def run(x, audit=False):
            raw, detail = original_run(x, audit=False)
            for row in detail['layers']:
                row['chunks'] = 1  # simulated receipt, never a real hardware claim
            return raw, detail

        model.run = run
        return model

    old_save = tests.save

    def desktop_save(path, value):
        if isinstance(value, dict) and 'actual_hardware' in value:
            value = dict(value, actual_hardware=False,
                         test_scope='Desktop orchestration only: software integer callbacks, simulated chunk counts')
        old_save(path, value)

    # Only in this separate desktop test process; production guards unchanged.
    tests.execution = desktop_execution
    tests.make = desktop_make
    tests.save = desktop_save
    tests.check_setup = lambda run: (output, dict(previous_run=str(prior), prior_integration_sha256='desktop_reference_only'))
    tests.identity = lambda: dict(desktop_runtime=api.version, actual_hardware=False)
    try:
        summary = tests.profile(output, repeats=1, warmup=1, baseline_only=True)
        raw = json.loads((output / 'baseline_profile_raw.json').read_text(encoding='utf8'))
        if len(raw) != 6 or len(summary) != 2 * (1 + 56 + 55 + 57 + 67):
            raise AssertionError('Missing CPU/FPGA summary rows')
        for record in raw:
            if record['mode'] == 'v4_off' and len(record['fpga_layers']) != 67:
                raise AssertionError('Missing V4 layers')
            for layer in record['fpga_layers']:
                if layer['input_bytes'] != int(np.prod(layer['input_shape'])) or layer['output_bytes'] != int(np.prod(layer['output_shape'])):
                    raise AssertionError('Wrong actual INT8 tensor shape byte accounting')
        # The previous-reference equality check must reject a changed vector.
        name = list(features)[0]
        bad = np.load(prior / ('v3.' + name + '.npy'), allow_pickle=False)
        bad = bad.copy()
        bad.flat[0] += 1
        try:
            tests.expected_previous(dict(previous_run=str(prior)), 'v3_off', name, bad)
        except AssertionError:
            pass
        else:
            raise AssertionError('Baseline reference mismatch was accepted')
        final = json.loads((output / 'baseline_profile_summary.json').read_text(encoding='utf8'))
        if final['actual_hardware']:
            raise AssertionError('Desktop test must not create true board receipt')
        old_save(WORK / 'diagnostics/profile_flow_validation.json',
                 dict(pass_=True, actual_hardware=False, records=len(raw), summary_rows=len(summary),
                      csv_exists=(output / 'baseline_profile_summary.csv').is_file(),
                      previous_vector_mismatch_rejected=True,
                      scope='Actual native CPU/subgraph runs and software integer callbacks; simulated chunk counts',
                      package_sha256=tests.core.digest(ROOT / 'updates/cpu_optimization_profile.zip')))
        print('DESKTOP_PROFILE_FLOW_PASS', len(raw), len(summary), flush=True)
    finally:
        tests.execution, tests.make, tests.save = original_execution, original_make, old_save


if __name__ == '__main__':
    main()
