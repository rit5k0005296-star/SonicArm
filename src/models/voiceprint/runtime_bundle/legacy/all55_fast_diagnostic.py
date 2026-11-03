"""Run existing all55 gates with an exactly equivalent, faster software oracle."""
from contextlib import contextmanager
from pathlib import Path
import argparse
import json
import platform
import sys
import time
import numpy as np
import runtime_core as core
import compatible_all55 as all55
from exact_block_reference import integer_pointwise


def validate():
    manifest = json.loads((core.HERE / 'all55_fast_manifest.json').read_text(encoding='utf-8'))
    for name, expected in manifest['files'].items():
        path = (core.HERE / name).resolve()
        if not path.is_relative_to(core.HERE):
            raise ValueError('Fast diagnosis path escapes root')
        if path.suffix == '.ipynb':
            if core.notebook_sources(path) != manifest['notebook_cells'][name]:
                raise ValueError('Fast diagnostic notebook code changed')
        elif core.digest(path) != expected:
            raise ValueError('Fast diagnosis file changed: ' + name)
    return core.digest(core.HERE / 'all55_fast_manifest.json')


def self_check(original):
    layers = json.loads((core.BUNDLE / 'layers.json').read_text())
    rng = np.random.default_rng(20261015); rows = []
    for index in (1, 2, 27, 52, 55):
        layer = layers[index-1]
        with np.load(core.BUNDLE / layer['params'], allow_pickle=False) as p:
            params = {k: p[k].copy() for k in p.files}
        x = rng.integers(-128, 128, size=(1, layer['cin'], 7), dtype=np.int8)
        start = time.perf_counter(); old_q, old_acc = original(layer, params, x, True)
        old_ms = (time.perf_counter()-start)*1000
        start = time.perf_counter(); q, acc = integer_pointwise(layer, params, x, True)
        new_ms = (time.perf_counter()-start)*1000
        if not (np.array_equal(old_q, q) and np.array_equal(old_acc, acc)):
            raise AssertionError('Exact reference self-check failed at layer ' + str(index))
        rows.append({'layer': index, 'INT8_exact': True, 'INT32_exact': True,
                     'old_reference_ms': old_ms, 'block_reference_ms': new_ms})
    print('EXACT_REFERENCE_SELF_CHECK: PASS 5/5 (INT8 and INT32)', flush=True)
    return rows


@contextmanager
def reference_and_progress():
    original = core.integer_pointwise; original_run = core.Hybrid.run
    def progress_run(self, features, audit=False):
        sink = self.audit_sink
        def report(row):
            if sink is not None:
                sink(row)
            if row['index'] == 1 or row['index'] % 10 == 0 or row['index'] == 55:
                print('[LAYER]', self.mode, str(row['index'])+'/55', 'frames', row['frames'], flush=True)
        self.audit_sink = report
        try:
            return original_run(self, features, audit)
        finally:
            self.audit_sink = sink
    core.integer_pointwise = integer_pointwise; core.Hybrid.run = progress_run
    try:
        yield original
    finally:
        core.integer_pointwise = original; core.Hybrid.run = original_run


def run(stage, directory, cpu_report=None, factory=None, backend=None):
    fingerprint = validate()
    directory = Path(directory).resolve()
    if not directory.is_relative_to(core.HERE):
        raise ValueError('Results must stay in full_model_test')
    directory.mkdir(parents=True, exist_ok=True)
    if stage == 'fpga':
        if cpu_report is None:
            raise ValueError('Run 03b software diagnosis first')
        path = Path(cpu_report).resolve()
        if not path.is_relative_to(core.HERE):
            raise ValueError('CPU receipt escapes root')
        prior = json.loads(path.read_text(encoding='utf-8'))
        if prior.get('exact_reference_manifest') != fingerprint:
            raise ValueError('03b CPU receipt must match this exact reference implementation')
    with reference_and_progress() as original:
        checks = self_check(original)
        core.save(directory / 'reference_check.json', {
            'exact_reference_manifest': fingerprint, 'checks': checks,
            'proof': '128*255*128 < 2**24; partial integer sums exact in FP32; INT64 block accumulation',
            'performance_claim': False, 'scope': 'software oracle self-check only'})
        result = all55.run(stage, directory, cpu_report, factory, backend)
    result['exact_reference_manifest'] = fingerprint
    result['reference_self_check'] = checks
    result['reference_note'] = 'Exactly equivalent blocked integer reference; original model/FPGA gates unchanged'
    core.save(directory / 'correctness.json', result)
    return result


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['cpu', 'fpga'], required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--cpu-report', type=Path)
    args = parser.parse_args()
    if platform.system() != 'Linux' or platform.machine().lower() not in ('armv7l', 'armv8l'):
        parser.error('Execute manually on ARM Linux')
    run(args.stage, args.output, args.cpu_report)
