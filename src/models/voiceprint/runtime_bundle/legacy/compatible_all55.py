"""Manual all55 diagnosis: distinguish hardware fidelity from QDQ model drift.
No performance, authentication, or accuracy acceptance is inferred from this run.
"""
from pathlib import Path
from types import SimpleNamespace
import argparse
import json
import platform
import sys
import numpy as np
import runtime_core as core
from compatible_one_layer import route, validate as validate_one
from native_ort_bridge import backend_details
from run_full_model import correctness

ASSETS = core.HERE / 'compatible_all55_assets'


def validate():
    core.verify_manifest()
    manifest = json.loads((ASSETS / 'manifest.json').read_text(encoding='utf-8'))
    for name, sha in manifest['files'].items():
        path = (core.HERE / name).resolve()
        if not path.is_relative_to(core.HERE):
            raise ValueError('Package path escapes root')
        if path.suffix == '.ipynb':
            if core.notebook_sources(path) != manifest['notebook_cells'][name]:
                raise ValueError('Notebook code changed: ' + name)
        elif core.digest(path) != sha:
            raise ValueError('All55 diagnosis package changed: ' + name)
    mapping = json.loads((ASSETS / 'mapping.json').read_text(encoding='utf-8'))
    for name, row in mapping.items():
        if core.digest(core.HERE / name) != row['original_sha256']:
            raise ValueError('Original CPU graph changed: ' + name)
    return mapping


def require_one_layer(backend):
    validate_one()
    expected = core.digest(core.HERE / 'compatible_one_assets/manifest.json')
    matches = []
    for path in (core.HERE / 'test_results').glob('compatible_one_*/fpga/correctness.json'):
        value = json.loads(path.read_text(encoding='utf-8'))
        if (value.get('pass') and value.get('fpga_executed') and value.get('plan') == 'one'
                and value.get('compatible_manifest') == expected and value.get('native_backend') == backend):
            matches.append(path)
    if not matches:
        raise ValueError('Passing actual 01a FPGA report required for this exact backend/package')
    path = sorted(matches, key=lambda v: v.stat().st_mtime)[-1]
    return {'file': str(path), 'sha256': core.digest(path)}


def run(stage, directory, cpu_report=None, factory=None, backend=None):
    directory = Path(directory).resolve()
    if not directory.is_relative_to(core.HERE):
        raise ValueError('Output must stay in full_model_test')
    directory.mkdir(parents=True, exist_ok=True)
    mapping = validate()
    backend = backend or backend_details()
    fingerprint = core.digest(ASSETS / 'manifest.json')
    prerequisite = None
    if stage == 'fpga':
        if cpu_report is None:
            raise ValueError('Complete the all55 software diagnosis before FPGA')
        cpu_report = Path(cpu_report).resolve()
        if not cpu_report.is_relative_to(core.HERE):
            raise ValueError('Software prerequisite escapes root')
        prior = json.loads(cpu_report.read_text(encoding='utf-8'))
        if not (prior.get('stage') == 'cpu' and prior.get('diagnostic_completed')
                and prior.get('software_reconstruction_gate')
                and prior.get('diagnostic_manifest') == fingerprint and prior.get('native_backend') == backend):
            raise ValueError('Matching all55 CPU reconstruction gate required')
        prerequisite = {'all55_cpu': {'file': str(cpu_report), 'sha256': core.digest(cpu_report)},
                        'actual_one_layer_fpga': require_one_layer(backend)}
    args = SimpleNamespace(mode='integer' if stage == 'cpu' else 'fpga', plan='all55',
        frontend='numpy16k', threads=1, threshold=None, threshold_source=None,
        near_threshold=0.02, integer_cosine_min=0.99999, integer_relative_max=0.01,
        score_delta_max=0.001)
    info = {'stage': stage, 'diagnostic_manifest': fingerprint, 'native_backend': backend,
            'model_variant': 'zero-explicit-padding AveragePool compatible derivative',
            'CPU_reference': 'same-board complete compatible QDQ model, optimization OFF',
            'desktop_strict_parity': False, 'prerequisites': prerequisite,
            'threshold': None, 'performance_claim': False, 'dataset_accuracy_claim': False,
            'diagnostic_policy': 'Original QDQ drift limits unchanged. Hardware diagnostic may run when QDQ drift fails; it does not turn that gate into a pass.'}
    core.save(directory / 'variant.json', info)
    try:
        with route(mapping, factory):
            try:
                result = correctness(args, directory)
            except AssertionError as error:
                # Only the known end-of-run aggregate gate is a completed diagnosis.
                # Local INT8/accumulator, guard, timeout, and reconstruction errors remain fatal.
                if str(error) != 'Embedding/score gate failed; see correctness.json. Performance not run.':
                    raise
                result = json.loads((directory / 'correctness.json').read_text(encoding='utf-8'))
        reconstruction = [v for v in result['embedding'] if v['mode'] == 'bypass']
        reconstruction_gate = len(reconstruction) == 3 and all(v['pass'] for v in reconstruction)
        if not reconstruction_gate:
            raise AssertionError('All55 CPU graph reconstruction differs from complete compatible model')
        qdq = [v for v in result['embedding'] if v['mode'] == 'integer']
        score_rows = result['scores']['integer']
        qdq_gate = (len(qdq) == 3 and all(v['pass'] for v in qdq)
                    and all(abs(v['score_delta']) <= 0.001 for v in score_rows))
        hardware = None
        if stage == 'fpga':
            checks = [v for v in result['embedding'] if v['mode'] in ('fpga_debug', 'fpga')]
            hardware = len(checks) == 6 and all(v['pass'] for v in checks)
            for mode in ('fpga_debug', 'fpga'):
                for integer, actual in zip(result['scores']['integer'], result['scores'][mode]):
                    hardware = hardware and integer['audio'] == actual['audio'] and integer['score'] == actual['score']
                for audio in json.loads((core.BUNDLE / 'smoke_protocol.json').read_text())['audio']:
                    integer = np.load(directory / ('integer.' + audio['id'] + '.embedding.npy'), allow_pickle=False)
                    actual = np.load(directory / (mode + '.' + audio['id'] + '.embedding.npy'), allow_pickle=False)
                    hardware = hardware and bool(np.array_equal(integer, actual))
            if not hardware:
                raise AssertionError('All55 FPGA outputs/embeddings/scores differ from integer reference')
        # Retain original pass (possibly False); never relabel QDQ drift as acceptance.
        result.update(info)
        result.update(diagnostic_completed=True, software_reconstruction_gate=reconstruction_gate,
                      QDQ_drift_gate=qdq_gate, hardware_consistency_gate=hardware,
                      all55_model_acceptance=bool(result['pass'] and qdq_gate and hardware is True))
        core.save(directory / 'correctness.json', result)
        print('ALL55_SOFTWARE_RECONSTRUCTION_GATE:', reconstruction_gate, flush=True)
        print('ALL55_QDQ_DRIFT_GATE:', qdq_gate, flush=True)
        for v in qdq:
            print('  INTEGER_VS_CPU', v['audio'], 'cosine', v['cosine'], 'relative_l2', v['relative_l2'], flush=True)
        print('ALL55_HARDWARE_CONSISTENCY_GATE:', hardware, flush=True)
        print('ALL55_MODEL_ACCEPTANCE:', result['all55_model_acceptance'], flush=True)
        print('DESKTOP_STRICT_PARITY: False (separate diagnostic, unchanged)', flush=True)
        print('DIAGNOSTIC_COMPLETED:', directory / 'correctness.json', flush=True)
        return result
    except Exception as error:
        core.save(directory / 'failure.json', {**info, 'diagnostic_completed': False, 'error': repr(error)})
        print('STOPPED; return full output:', directory, flush=True)
        raise


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['cpu', 'fpga'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cpu-report', type=Path)
    args = parser.parse_args()
    if platform.system() != 'Linux' or platform.machine().lower() not in ('armv7l', 'armv8l'):
        parser.error('Execute manually on ARM Linux')
    run(args.stage, args.output, args.cpu_report)
