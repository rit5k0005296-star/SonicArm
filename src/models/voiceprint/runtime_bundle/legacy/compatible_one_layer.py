"""Manual board validation against a same-board, pooling-compatible CPU baseline.
Desktop cross-architecture parity remains a separate, failed diagnostic.
"""
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import argparse
import gc
import json
import platform
import sys
import runtime_core as core
from native_ort_bridge import backend_details
from run_full_model import correctness

ASSETS = core.HERE / 'compatible_one_assets'


def validate():
    core.verify_manifest()
    manifest = json.loads((ASSETS / 'manifest.json').read_text(encoding='utf-8'))
    for name, expected in manifest['files'].items():
        path = (core.HERE / name).resolve()
        if not path.is_relative_to(core.HERE):
            raise ValueError('Package path escapes root')
        if path.suffix == '.ipynb':
            if core.notebook_sources(path) != manifest['notebook_cells'][name]:
                raise ValueError('Notebook source changed: ' + name)
        elif core.digest(path) != expected:
            raise ValueError('Compatible one-layer package changed: ' + name)
    mapping = json.loads((ASSETS / 'mapping.json').read_text(encoding='utf-8'))
    for name, row in mapping.items():
        if core.digest(core.HERE / name) != row['original_sha256']:
            raise ValueError('Original graph changed: ' + name)
    return manifest, mapping


@contextmanager
def route(mapping, factory=None):
    original = core.ort_session
    factory = factory or original
    def selected(path, threads=1, optimize=False):
        name = Path(path).resolve().relative_to(core.HERE).as_posix()
        target = core.HERE / mapping[name]['compatible_file'] if name in mapping else path
        return factory(target, threads, optimize)
    core.ort_session = selected
    try:
        yield
    finally:
        core.ort_session = original


def run(stage, directory, cpu_report=None, factory=None, backend=None):
    directory = Path(directory).resolve()
    if not directory.is_relative_to(core.HERE):
        raise ValueError('Output must stay in full_model_test')
    directory.mkdir(parents=True, exist_ok=True)
    manifest, mapping = validate()
    args = SimpleNamespace(mode='integer' if stage == 'cpu' else 'fpga', plan='one',
        frontend='numpy16k', threads=1, threshold=None, threshold_source=None,
        near_threshold=0.02, integer_cosine_min=0.99999, integer_relative_max=0.01,
        score_delta_max=0.001)
    prerequisite = None
    if stage == 'fpga':
        if cpu_report is None:
            raise ValueError('Run the compatible software gate first')
        cpu_report = Path(cpu_report).resolve()
        if not cpu_report.is_relative_to(core.HERE):
            raise ValueError('CPU prerequisite path escapes root')
        prior = json.loads(cpu_report.read_text(encoding='utf-8'))
        if not (prior.get('pass') and prior.get('compatible_manifest') == core.digest(ASSETS / 'manifest.json')
                and prior.get('stage') == 'cpu' and prior.get('native_backend') == (backend or backend_details())):
            raise ValueError('Missing passing CPU gate for this exact package and backend')
        prerequisite = {'file': str(cpu_report), 'sha256': core.digest(cpu_report)}
    info = {'stage': stage, 'scope': 'full-recording, one-layer hardware integration correctness only',
            'model_variant': 'zero-explicit-padding AveragePool compatible derivative',
            'CPU_reference': 'same-board complete compatible QDQ model, graph optimization OFF',
            'desktop_strict_parity': False, 'desktop_parity_status': 'known unresolved architecture-dependent float-to-INT8 drift; not relaxed or claimed passed',
            'compatible_manifest': core.digest(ASSETS / 'manifest.json'), 'mapping': mapping,
            'native_backend': backend or backend_details(), 'CPU_prerequisite': prerequisite,
            'threshold': None, 'performance_claim': False, 'dataset_accuracy_claim': False}
    core.save(directory / 'variant.json', info)
    try:
        with route(mapping, factory):
            # Reuse existing per-layer accumulator/INT8 checks and embedding/score gates.
            result = correctness(args, directory)
        result.update(info)
        result['pass'] = True
        core.save(directory / 'correctness.json', result)
        print('COMPATIBLE_SOFTWARE_GATE_PASS' if stage == 'cpu' else 'ONE_LAYER_FPGA_INTEGRATION_PASS', flush=True)
        print('DESKTOP_STRICT_PARITY: False (separate diagnostic, unchanged)', flush=True)
        print('REPORT:', directory / 'correctness.json', flush=True)
        return result
    except Exception as error:
        core.save(directory / 'failure.json', {**info, 'pass': False, 'error': repr(error)})
        print('STOPPED; return complete output:', directory, flush=True)
        raise
    finally:
        gc.collect()


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
