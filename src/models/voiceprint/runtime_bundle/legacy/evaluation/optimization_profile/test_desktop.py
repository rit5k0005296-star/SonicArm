"""Actual desktop native ORT1.17.1 model/optimization/profile validation.

Never runs PYNQ, creates board receipts, or interprets desktop times as ARM times.
"""
from pathlib import Path
import ast
import ctypes as ct
import json
import sys
import time
import zipfile

sys.dont_write_bytecode = True
WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[1]
MODELS = ROOT.parents[1]
sys.path.insert(0, str(MODELS / 'consistency-test/codex'))
from common import import_runtime
import_runtime('cpu')
sys.path.insert(0, str(WORK))
import numpy as np
import optimization_profile as tests
from native_ort_bridge import API, Session


def main():
    tests.validate_files()
    for name in ('optimization_profile.py', 'build_package.py'):
        ast.parse((WORK / name).read_text(encoding='utf8'))
    api = API(ROOT / 'desktop_validation/ort_audit/windows1171/onnxruntime-win-x64-1.17.1/lib/onnxruntime.dll', verify=False)
    if api.version != '1.17.1':
        raise AssertionError('Wrong native runtime')
    factory_calls = []

    def factory(path, threads=1, optimize=False):
        factory_calls.append(dict(path=str(path), optimize=optimize, threads=threads))
        return Session(path, threads, optimize, api=api)

    protocol, _, features = tests.bench.data()
    capacity = max(x.shape[1] for x in features.values())
    vectors, quality, profile_checks = {}, {}, []
    start = time.perf_counter()
    original_session_factory = tests.core.ort_session
    for mode in ('cpu_reference', *tests.MODES):
        print('[DESKTOP OPT]', mode, flush=True)
        vectors[mode] = {}
        before = len(factory_calls)
        with tests.execution(tests.optimized(mode), factory=factory):
            model = tests.core.FullCPU(1, False) if mode == 'cpu_reference' else tests.make(mode, capacity, hardware=False)
            try:
                for name, x in features.items():
                    raw, detail = model.run(x, audit=False)
                    tests.valid_vector(raw)
                    vectors[mode][name] = raw.copy()
                    print('[DESKTOP VECTOR]', mode, name, 'norm', float(np.linalg.norm(raw)), flush=True)
            finally:
                tests.bench.close(model)
        calls = factory_calls[before:]
        wanted = 1 if mode in ('cpu_reference', 'cpu_int8') else (57 if mode.startswith('v4') else 56)
        if len(calls) != wanted or any(c['optimize'] != tests.optimized(mode) for c in calls):
            raise AssertionError('Not every actual CPU session used requested optimization policy')
        if tests.core.ort_session is not original_session_factory:
            raise AssertionError('Session factory was not restored')
        quality[mode] = {n: tests.strict(vectors['cpu_reference'][n], v) for n, v in vectors[mode].items()}

    # The separate profiling path must preserve exact vectors and actual CPU
    # interfaces on both complete query lengths, for all optimized/OFF modes.
    profile_records = []
    for mode in tests.MODES:
        collector = []
        with tests.execution(tests.optimized(mode), collector, factory=factory):
            model = tests.make(mode, capacity, hardware=False)
            try:
                for trial in protocol['trials']:
                    name = trial['audio']
                    collector.clear()
                    raw, detail = model.run(features[name], audit=False)
                    if not np.array_equal(raw, vectors[mode][name]):
                        raise AssertionError('Profiler changed vector')
                    wanted = 1 if mode == 'cpu_int8' else (57 if mode.startswith('v4') else 56)
                    if len(collector) != wanted:
                        raise AssertionError('Missing CPU profiling rows')
                    if mode != 'cpu_int8' and collector[0 if mode.startswith('v3') else 1]['outputs']['count'] != 1205:
                        raise AssertionError('Original large graph interface not captured')
                    for row in collector:
                        for key in ('inputs', 'outputs'):
                            meta = row[key]
                            if len(meta['tensors']) != meta['count'] or sum(t['bytes'] for t in meta['tensors']) != meta['bytes']:
                                raise AssertionError('Incorrect tensor shape/byte accounting')
                    profile_records.append(dict(mode=mode, audio=name, cpu_sessions=[dict(r) for r in collector], fpga_layers=[]))
                    profile_checks.append(dict(mode=mode, audio=name, cpu_sessions=len(collector), embedding_exact=True))
                    print('[DESKTOP PROFILE EXACT]', mode, name, len(collector), flush=True)
            finally:
                tests.bench.close(model)

    # The new optimization policies change FCM inputs; exercise the real compiled
    # FCM implementation on those live inputs, compared to independent INT64.
    native = ct.CDLL(str(MODELS / 'FPGA-4/fcm_engine/diagnostics/fcm_native.dll')).fcm
    p8, pi, pu = ct.POINTER(ct.c_int8), ct.POINTER(ct.c_int32), ct.POINTER(ct.c_uint32)
    native.argtypes = [p8, p8, pi, pu, p8, p8, p8, pi] + [ct.c_int] * 10
    native.restype = ct.c_int

    class NativeFCM:
        def __init__(self, params):
            self.params = params
            self.audit = False
            self.safe = True

        def call(self, row, x, skip):
            params = self.params[row['index']]
            of = (x.shape[1] + row['stride_f'] - 1) // row['stride_f']
            q = np.empty((row['cout'], of, x.shape[2]), np.int8)
            acc = np.empty(q.shape, np.int32)
            arrays = [np.ascontiguousarray(x), params['weights'], params['bias'], params['multiplier'],
                      params['post_lut'], np.ascontiguousarray(skip), q, acc]
            pointers = [v.ctypes.data_as(ty) for v, ty in zip(arrays, native.argtypes[:8])]
            scalars = [row['cin'], row['cout'], x.shape[1], x.shape[2], row['kernel'], row['stride_f'],
                       row['input_zp'], row['output_zp'], row['requant_shift'], row['flags']]
            if native(*pointers, *scalars):
                raise AssertionError('Native FCM failed')
            return q, acc, dict(chunks=1, pointer_rebinds=0)

    native_checks = []
    for mode in ('v4_off', 'v4_on'):
        with tests.execution(tests.optimized(mode), factory=factory):
            model = tests.make(mode, capacity, hardware=False)
            model.runner.context = NativeFCM(model.runner.params)
            try:
                for name, x in features.items():
                    raw, _ = model.run(x, audit=False)
                    if not np.array_equal(raw, vectors[mode][name]):
                        raise AssertionError('Native FCM complete model differs from independent integer model')
                    native_checks.append(dict(mode=mode, audio=name, exact=True))
                    print('[DESKTOP NATIVE FCM EXACT]', mode, name, flush=True)
            finally:
                tests.bench.close(model)

    # Confirm failure restores every patched runtime function without touching
    # hardware. This is essential for a persistent Jupyter kernel.
    old_integer, old_run = tests.core.integer_pointwise, tests.core.Hybrid.run
    try:
        with tests.execution(True, factory=factory):
            raise RuntimeError('intentional context restoration test')
    except RuntimeError:
        pass
    if tests.core.ort_session is not original_session_factory or tests.core.integer_pointwise is not old_integer or tests.core.Hybrid.run is not old_run:
        raise AssertionError('Failed execution context leaked patches')
    summary = tests.summarize_profile(profile_records)
    if len(summary) != 2 * (1 + 56 + 56 + 57 + 57):
        raise AssertionError('Profile aggregation lost sessions')
    tests.validate_files()
    archive = ROOT / 'updates/cpu_optimization_profile.zip'
    with zipfile.ZipFile(archive) as z:
        if z.testzip() or len(z.namelist()) != 4 or any(not n.startswith('optimization_profile/') for n in z.namelist()):
            raise AssertionError('Bad upload package')
    report = dict(pass_=True, actual_hardware=False, backend='Windows native ORT CAPI ' + api.version,
                  scope='Original full Fbank, OFF/ALL policies on every V3/V4 CPU session; profiler vectors exact; '
                        'real compiled FCM versus independent INT64 with live OFF/ALL inputs. No ARM/PL timing proof.',
                  quality_vs_original_cpu=quality, profile_checks=profile_checks, native_fcm_checks=native_checks,
                  session_factory_restoration=True, original_root_manifest_sha256=tests.core.digest(ROOT / 'upload_manifest.json'),
                  archive_sha256=tests.core.digest(archive), elapsed_seconds=time.perf_counter() - start)
    tests.save(WORK / 'diagnostics/desktop_validation.json', report)
    print('DESKTOP_OPT_VALIDATION_PASS:', WORK / 'diagnostics/desktop_validation.json', flush=True)


if __name__ == '__main__':
    main()
