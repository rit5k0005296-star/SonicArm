"""Manual ARM tests: CPU subgraph optimization and separate layer profiling.

Read-only dependencies: benchmark_compare and the original V3 runtime/models.
No hardware runs on import; never starts or kills a hardware subprocess.
"""
from pathlib import Path
from contextlib import contextmanager
import ast
import csv
import gc
import hashlib
import json
import platform
import sys
import time
import numpy as np

WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[1]
COMPARE = WORK.parent / 'benchmark_compare'
sys.path.insert(0, str(COMPARE))
import compare_benchmark as bench
import compare_runtime as runtime
import runtime_core as core

MODES = ('cpu_int8', 'v3_off', 'v3_on', 'v4_off', 'v4_on')
LIMITS = dict(cosine_min=.99999, relative_l2_max=.01, score_abs_delta_max=.001)


def notebook_program(sources):
    """Compare executable structure, ignoring comments and whitespace only.

    The three documented integer settings are configurable in the first code
    cell. Do not evaluate notebook code or normalize arbitrary expressions.
    """
    programs = []
    for source in sources:
        tree = ast.parse(source)
        if not tree.body:  # Jupyter may append empty code cells.
            continue
        if not programs:
            for node in tree.body:
                if not (isinstance(node, ast.Assign) and len(node.targets) == 1 and
                        isinstance(node.targets[0], ast.Name)):
                    continue
                name = node.targets[0].id
                if name not in ('PROFILE_REPEATS', 'REPEATS', 'WARMUP'):
                    continue
                if not isinstance(node.value, ast.Constant) or type(node.value.value) is not int:
                    raise ValueError(name + ' must be a positive integer literal')
                value = node.value.value
                if value < 1 or (name == 'REPEATS' and (value < 2 or value % 2)):
                    raise ValueError('Invalid notebook setting: ' + name)
                node.value = ast.Constant(value='CONFIGURABLE_' + name)
        programs.append(ast.dump(tree, include_attributes=False))
    return programs


def save(path, value):
    path = Path(path).resolve()
    if not path.is_relative_to(WORK):
        raise ValueError('Output must stay in optimization_profile')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf8')
    temporary.replace(path)


def validate_files():
    bench.validate_files()
    m = json.loads((WORK / 'manifest.json').read_text(encoding='utf8'))
    if core.digest(COMPARE / 'manifest.json') != m['comparison_manifest_sha256']:
        raise ValueError('Requires the matching 06 comparison package')
    for name, expected in m['files'].items():
        p = (WORK / name).resolve()
        if not p.is_relative_to(WORK):
            raise ValueError('Unsafe manifest path')
        observed = core.notebook_source_digest(p) if p.suffix == '.ipynb' else core.digest(p)
        if observed != expected:
            reference = m.get('notebook_cells', {}).get(name)
            if p.suffix == '.ipynb' and reference is not None:
                if notebook_program(core.notebook_sources(p)) == notebook_program(reference):
                    continue
                raise ValueError('Notebook executable statements changed: ' + name +
                                 '; restore the packaged cells. Blank lines/comments and documented numeric settings are allowed.')
            raise ValueError('New test file changed: ' + name)
    return m


def identity():
    return dict(test_manifest_sha256=core.digest(WORK / 'manifest.json'), comparison=bench.identity())


def directory(path):
    path = Path(path).resolve()
    if not path.is_relative_to(WORK / 'results'):
        raise ValueError('Use optimization_profile/results')
    path.mkdir(parents=True, exist_ok=True)
    return path


def setup(run, previous_run):
    if platform.system() != 'Linux' or platform.machine().lower() not in ('armv7l', 'armv8l'):
        raise RuntimeError('Run manually on the PYNQ board')
    if runtime.UNSAFE:
        raise RuntimeError('Previous active hardware failure: power-cycle and restart kernel')
    validate_files()
    run = directory(run)
    previous_run = Path(previous_run).resolve()
    if not previous_run.is_relative_to(COMPARE / 'results'):
        raise ValueError('Previous run must be under benchmark_compare/results')
    p = previous_run / 'integration.json'
    prior = json.loads(p.read_text(encoding='utf8'))
    performance = json.loads((previous_run / 'performance.json').read_text(encoding='utf8'))
    wanted = bench.identity()
    if not (prior.get('identity') == wanted and prior.get('actual_hardware') and
            prior.get('integration_ready') and prior.get('hardware_integer_consistency_pass') and
            performance.get('identity') == wanted and performance.get('completed') and
            performance.get('actual_hardware')):
        raise ValueError('Matching completed actual-board 06 run required')
    _, items, features = bench.data()
    feature_hashes = {n: core.digest(core.BUNDLE / items[n]['features']) for n in features}
    if prior.get('feature_sha256') != feature_hashes:
        raise ValueError('Previous features differ')
    prior_vectors = {}
    for mode in ('cpu_int8', 'v3', 'v4'):
        for name in features:
            file = mode + '.' + name + '.npy'
            valid_vector(np.load(previous_run / file, allow_pickle=False))
            prior_vectors[file] = core.digest(previous_run / file)
    receipt = dict(identity=identity(), previous_run=str(previous_run),
                   prior_integration_sha256=core.digest(p),
                   prior_performance_sha256=core.digest(previous_run / 'performance.json'),
                   feature_sha256=feature_hashes, prior_vector_sha256=prior_vectors, modes=list(MODES), threads=1,
                   scope='frozen canonical Fbank -> full model -> L2 -> cosine',
                   optimization='OFF versus ORT_ENABLE_ALL for hybrid CPU sessions only; same bitstreams',
                   authentication_threshold=None, accuracy_matched_speedup_claim=False,
                   note='Strict optimization drift and original QDQ drift are reported independently. '
                        'Engineering timing requires matching current hardware/software integer outputs; '
                        'it does not imply either numerical drift gate passed.')
    save(run / 'setup.json', receipt)
    print('OPT_SETUP_PASS:', run, flush=True)
    return receipt


def check_setup(run):
    validate_files()
    run = directory(run)
    receipt = json.loads((run / 'setup.json').read_text(encoding='utf8'))
    if receipt['identity'] != identity():
        raise ValueError('Wrong test identity')
    previous = Path(receipt['previous_run'])
    for name, key in [('integration.json', 'prior_integration_sha256'),
                      ('performance.json', 'prior_performance_sha256')]:
        if core.digest(previous / name) != receipt[key]:
            raise ValueError('Previous evidence changed')
    for name, wanted in receipt['prior_vector_sha256'].items():
        p = (previous / name).resolve()
        if not p.is_relative_to(previous) or core.digest(p) != wanted:
            raise ValueError('Previous embedding changed: ' + name)
    _, items, features = bench.data()
    if receipt['feature_sha256'] != {n: core.digest(core.BUNDLE / items[n]['features']) for n in features}:
        raise ValueError('Feature identity changed')
    if runtime.UNSAFE:
        raise RuntimeError('Hardware may be active; power-cycle board before retry')
    return run, receipt


def tensor_summary(names, values):
    rows = [dict(name=n, shape=list(v.shape), dtype=str(v.dtype), bytes=int(v.nbytes))
            for n, v in zip(names, values)]
    return dict(count=len(rows), bytes=sum(r['bytes'] for r in rows),
                tensors=rows, largest=sorted(rows, key=lambda r: r['bytes'], reverse=True)[:8])


class ProfileSession:
    """Record complete native bridge calls, including tensor marshalling/copies."""
    def __init__(self, session, path, optimize, collector):
        self.session = session
        self.path = str(Path(path).resolve().relative_to(ROOT))
        self.optimize = optimize
        self.collector = collector

    def __getattr__(self, name):
        return getattr(self.session, name)

    def run(self, names, feed):
        before = time.perf_counter()
        out = self.session.run(names, feed)
        elapsed = (time.perf_counter() - before) * 1000
        # Metadata gathering deliberately outside this subgraph timer, but inside
        # profiled full-model wall time. Never use profiled wall time as benchmark.
        requested = [v.name for v in self.session.get_outputs()] if names is None else names
        self.collector.append(dict(component='CPU', name=self.path, cpu_session_ms=elapsed,
                                   optimize=self.optimize,
                                   inputs=tensor_summary(list(feed), list(feed.values())),
                                   outputs=tensor_summary(requested, out)))
        return out

    def close(self):
        self.session.close()


@contextmanager
def execution(optimize, collector=None, factory=None):
    # route() performs the existing AveragePool-compatible path mapping first.
    # The V4 first-session factory delegates its two inner native sessions here.
    original = factory or core.ort_session

    def selected(path, threads=1, optimize=False):
        session = original(path, threads, requested)
        return session if collector is None else ProfileSession(session, path, requested, collector)

    requested = bool(optimize)
    with bench.execution(selected) as reference:
        yield reference


def make(mode, capacity, hardware=True, debug=False):
    if mode == 'cpu_int8':
        return core.FullCPU(1, True)
    version, _ = mode.split('_')
    return bench.make_runtime(version if hardware else version + '_software', capacity, debug)


def optimized(mode):
    return mode == 'cpu_int8' or mode.endswith('_on')


def valid_vector(value):
    if value.shape != (1, 192) or value.dtype != np.float32 or not np.isfinite(value).all():
        raise AssertionError('Invalid complete embedding')


def strict(reference, observed):
    metric = core.compare(reference, observed)
    metric['pass_'] = metric['cosine'] >= LIMITS['cosine_min'] and metric['relative_l2'] <= LIMITS['relative_l2_max']
    return metric


def write_csv(path, rows):
    if not rows:
        return
    with Path(path).open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def correctness(run):
    run, receipt = check_setup(run)
    protocol, _, features = bench.data()
    capacity = max(x.shape[1] for x in features.values())
    vectors = {}
    audit_rows = []
    try:
        with execution(False) as original:
            save(run / 'reference_self_check.json', bench.self_check(original))
        for mode in ('cpu_reference', *MODES):
            print('[OPT GATE]', mode, flush=True)
            vectors[mode] = {}
            for hardware in ((False,) if mode in ('cpu_reference', 'cpu_int8') else (False, True)):
                with execution(optimized(mode)):
                    model = core.FullCPU(1, False) if mode == 'cpu_reference' else make(mode, capacity, hardware, debug=hardware)
                    try:
                        for name, x in features.items():
                            raw, detail = model.run(x, audit=hardware)
                            valid_vector(raw)
                            if not hardware:
                                vectors[mode][name] = raw.copy()
                                np.save(run / (mode + '.' + name + '.npy'), raw, allow_pickle=False)
                            else:
                                layers = detail['layers']
                                fcm = [r for r in layers if r.get('component') == 'FCM']
                                pw = [r for r in layers if r.get('component') != 'FCM']
                                if len(pw) != 55 or len(fcm) != (12 if mode.startswith('v4') else 0):
                                    raise AssertionError('Missing actual hardware layers')
                                if not all(r.get('integer_exact') for r in layers):
                                    raise AssertionError('Missing current-input hardware INT8/INT32 audit')
                                if not np.array_equal(vectors[mode][name], raw):
                                    raise AssertionError('Hardware embedding differs from matching optimized software integer model')
                                audit_rows.append(dict(mode=mode, audio=name, integer_embedding_exact=True, layers=layers))
                            print('[OPT GATE PASS]', mode, 'hardware' if hardware else 'software', name, flush=True)
                    finally:
                        bench.close(model)
        quality = []
        parity = []
        for mode in MODES:
            for name in features:
                quality.append(dict(mode=mode, audio=name, **strict(vectors['cpu_reference'][name], vectors[mode][name])))
        for version in ('v3', 'v4'):
            for name in features:
                parity.append(dict(version=version, audio=name,
                                   **strict(vectors[version + '_off'][name], vectors[version + '_on'][name])))
        enroll = protocol['enroll']['speaker1']
        scores = []
        for trial in protocol['trials']:
            name = trial['audio']
            values = {m: float(core.normalize(v[enroll]) @ core.normalize(v[name])) for m, v in vectors.items()}
            scores.append(dict(audio=name, label=trial['label'], scores=values,
                               v3_on_off_abs_delta=abs(values['v3_on'] - values['v3_off']),
                               v4_on_off_abs_delta=abs(values['v4_on'] - values['v4_off'])))
        gates = {v: all(r['pass_'] for r in parity if r['version'] == v) and
                    all(r[v + '_on_off_abs_delta'] <= LIMITS['score_abs_delta_max'] for r in scores)
                 for v in ('v3', 'v4')}
        original_gates = {m: all(r['pass_'] for r in quality if r['mode'] == m) and
                            all(abs(s['scores'][m] - s['scores']['cpu_reference']) <= LIMITS['score_abs_delta_max'] for s in scores)
                          for m in MODES}
        vector_hashes = {m + '.' + n + '.npy': core.digest(run / (m + '.' + n + '.npy'))
                         for m in vectors for n in features}
        report = dict(identity=identity(), engineering_ready=True, actual_hardware=True,
                      hardware_integer_consistency_pass=True, optimization_drift_gate=gates,
                      original_QDQ_drift_gate=original_gates, thresholds=LIMITS,
                      optimization_embedding_comparison=parity, original_embedding_comparison=quality,
                      scores=scores, hardware_audits=audit_rows, vector_sha256=vector_hashes,
                      accuracy_matched_speedup_claim=False, authentication_threshold=None,
                      setup_sha256=core.digest(run / 'setup.json'))
        save(run / 'correctness.json', report)
        print('OPTIMIZATION_DRIFT_GATE:', json.dumps(gates), flush=True)
        print('ORIGINAL_QDQ_DRIFT_GATE:', json.dumps(original_gates), flush=True)
        print('OPT_ENGINEERING_READY:', run / 'correctness.json', flush=True)
        return report
    except BaseException as error:
        save(run / 'correctness_failed.json', dict(error=repr(error), hardware_may_be_active=runtime.UNSAFE))
        raise


def check_gate(run):
    run, receipt = check_setup(run)
    gate = json.loads((run / 'correctness.json').read_text(encoding='utf8'))
    if not (gate.get('identity') == identity() and gate.get('engineering_ready') and gate.get('actual_hardware') and
            gate.get('hardware_integer_consistency_pass') and gate.get('setup_sha256') == core.digest(run / 'setup.json')):
        raise ValueError('Complete matching current optimization correctness gate first')
    for name, wanted in gate['vector_sha256'].items():
        p = (run / name).resolve()
        if not p.is_relative_to(run) or core.digest(p) != wanted:
            raise ValueError('Reference embedding changed: ' + name)
    return run, gate


def expected(run, mode, name, raw):
    valid_vector(raw)
    if not np.array_equal(np.load(run / (mode + '.' + name + '.npy'), allow_pickle=False), raw):
        raise AssertionError('Debug-off/profile output differs from this mode correctness reference: ' + mode + ' ' + name)


def expected_previous(receipt, mode, name, raw):
    valid_vector(raw)
    old_mode = mode.split('_')[0] if mode.startswith(('v3_', 'v4_')) else mode
    file = Path(receipt['previous_run']) / (old_mode + '.' + name + '.npy')
    if not np.array_equal(np.load(file, allow_pickle=False), raw):
        raise AssertionError('Baseline profiler differs from previous actual-board reference: ' + mode + ' ' + name)


def statistics(values):
    values = np.asarray(values, dtype=np.float64)
    return dict(n=len(values), median_ms=float(np.median(values)), p95_ms=float(np.percentile(values, 95)),
                min_ms=float(values.min()), max_ms=float(values.max()))


def benchmark(run, repeats=10, warmup=2):
    run, gate = check_gate(run)
    if repeats < 2 or repeats % 2 or warmup < 1:
        raise ValueError('Use an even repeats >=2 and warmup >=1')
    protocol, items, features = bench.data()
    capacity = max(x.shape[1] for x in features.values())
    enroll = protocol['enroll']['speaker1']
    names = list(dict.fromkeys(t['audio'] for t in protocol['trials']))
    rows, initializations = [], []
    try:
        for block, modes in enumerate((MODES, tuple(reversed(MODES)))):
            for mode in modes:
                print('[OPT BENCH]', block + 1, mode, 'INITIALIZE', flush=True)
                with execution(optimized(mode)):
                    before_snapshot = bench.snapshot()
                    before = time.perf_counter()
                    model = make(mode, capacity)
                    initializations.append(dict(block=block, mode=mode, initialization_ms=(time.perf_counter() - before) * 1000,
                                                before=before_snapshot, after=bench.snapshot()))
                    save(run / 'initialization.json', initializations)
                    try:
                        raw, _ = model.run(features[enroll], audit=False)
                        expected(run, mode, enroll, raw)
                        registry = core.normalize(raw)
                        for name in names:
                            for _ in range(warmup):
                                raw, _ = model.run(features[name], audit=False)
                                expected(run, mode, name, raw)
                            for repeat in range(repeats // 2):
                                raw, row = bench.invoke(model, features[name], registry)
                                expected(run, mode, name, raw)
                                check_counts(mode, row)
                                rows.append(dict(block=block, mode=mode, audio=name, repeat=repeat, **row))
                                # Persistence and printing outside invoke's timed interval.
                                save(run / 'raw_samples.json', rows)
                                print('[OPT TIMING]', mode, name, repeat + 1, '/', repeats // 2,
                                      round(row['model_l2_score_ms'], 3), flush=True)
                    finally:
                        bench.close(model)
        summaries = []
        for name in names:
            for mode in MODES:
                subset = [r for r in rows if r['mode'] == mode and r['audio'] == name]
                stat = statistics([r['model_l2_score_ms'] for r in subset])
                if stat['n'] != repeats:
                    raise AssertionError('Incomplete formal benchmark')
                summaries.append(dict(audio=name, mode=mode, **stat,
                                      real_time_factor=stat['median_ms'] / 1000 / items[name]['duration_seconds']))
        ratios = []
        for name in names:
            med = {r['mode']: r['median_ms'] for r in summaries if r['audio'] == name}
            ratios.append(dict(audio=name, V3_OFF_over_ON=med['v3_off'] / med['v3_on'],
                               V4_OFF_over_ON=med['v4_off'] / med['v4_on'],
                               CPU_INT8_over_V3_ON=med['cpu_int8'] / med['v3_on'],
                               CPU_INT8_over_V4_ON=med['cpu_int8'] / med['v4_on']))
        report = dict(identity=identity(), completed=True, actual_hardware=True, summary=summaries, ratios=ratios,
                      optimization_drift_gate=gate['optimization_drift_gate'],
                      original_QDQ_drift_gate=gate['original_QDQ_drift_gate'],
                      correctness_sha256=core.digest(run / 'correctness.json'),
                      profile_enabled=False, accuracy_matched_speedup_claim=False,
                      scope='frozen Fbank -> full model -> L2 -> cosine; one thread; reverse-order two blocks',
                      raw_samples=rows)
        save(run / 'performance.json', report)
        write_csv(run / 'summary.csv', summaries)
        for row in summaries:
            print('OPT_MODEL_LATENCY:', json.dumps(row), flush=True)
        for row in ratios:
            print('OPT_SPEEDUP_COMPARE:', json.dumps(row), flush=True)
        print('OPT_BENCHMARK_COMPLETED:', run / 'performance.json', flush=True)
        return report
    except BaseException as error:
        save(run / 'benchmark_failed.json', dict(error=repr(error), hardware_may_be_active=runtime.UNSAFE))
        raise


def check_counts(mode, row):
    if mode == 'cpu_int8':
        return
    if row['pointwise_chunks'] != 55 or row['fcm_chunks'] != (12 if mode.startswith('v4') else 0):
        raise AssertionError('Wrong actual hardware callback count for these <=529-frame inputs')


def profile(run, repeats=3, warmup=1, baseline_only=False):
    if baseline_only:
        run, receipt = check_setup(run)
        modes = ('cpu_int8', 'v3_off', 'v4_off')
        check = lambda mode, name, raw: expected_previous(receipt, mode, name, raw)
        prefix = 'baseline_'
        reference_sha256 = receipt['prior_integration_sha256']
    else:
        run, gate = check_gate(run)
        modes = MODES
        check = lambda mode, name, raw: expected(run, mode, name, raw)
        prefix = ''
        reference_sha256 = core.digest(run / 'correctness.json')
    if repeats < 1 or warmup < 1:
        raise ValueError('Positive profiling repeats/warmup required')
    protocol, _, features = bench.data()
    capacity = max(x.shape[1] for x in features.values())
    names = list(dict.fromkeys(t['audio'] for t in protocol['trials']))
    records = []
    try:
        for mode in modes:
            collector = []
            with execution(optimized(mode), collector):
                model = make(mode, capacity)
                try:
                    for name in names:
                        for _ in range(warmup):
                            raw, _ = model.run(features[name], audit=False)
                            check(mode, name, raw)
                            collector.clear()
                        for repeat in range(repeats):
                            collector.clear()
                            before = time.perf_counter()
                            raw, detail = model.run(features[name], audit=False)
                            wall = (time.perf_counter() - before) * 1000
                            check(mode, name, raw)
                            check_counts(mode, dict(pointwise_chunks=sum(r.get('chunks', 0) for r in detail['layers'] if r.get('component') != 'FCM'),
                                                    fcm_chunks=sum(r.get('chunks', 0) for r in detail['layers'] if r.get('component') == 'FCM')))
                            cpu_rows = [dict(r) for r in collector]
                            layer_rows = []
                            for r in detail['layers']:
                                component = r.get('component', 'pointwise')
                                layers = model.runner.rows if component == 'FCM' else (
                                    model.base.layers.values() if mode.startswith('v4') else model.layers.values())
                                cfg = next(v for v in layers if v['index'] == r['index'])
                                input_shape = ([cfg['cin'], cfg['freq'], r['frames']] if component == 'FCM'
                                               else [1, cfg['cin'], r['frames']])
                                output_shape = ([cfg['cout'], (cfg['freq'] + cfg['stride_f'] - 1) // cfg['stride_f'], r['frames']]
                                                if component == 'FCM' else [1, cfg['cout'], r['frames']])
                                layer_rows.append(dict(r, component=component, cin=cfg['cin'], cout=cfg['cout'],
                                                       input_frequency=cfg.get('freq'), kernel=cfg.get('kernel', 1),
                                                       input_shape=input_shape, output_shape=output_shape,
                                                       input_bytes=int(np.prod(input_shape)), output_bytes=int(np.prod(output_shape))))
                            records.append(dict(mode=mode, audio=name, repeat=repeat, profiled_wall_ms=wall,
                                                cpu_sessions=cpu_rows, fpga_layers=layer_rows,
                                                note='CPU call includes native tensor wrapping/copying. PL start/done includes DDR and polling. '
                                                     'Metadata collection adds wall overhead; do not compare this wall time with formal benchmark.'))
                            save(run / (prefix + 'profile_raw.json'), records)
                            print('[PROFILE]', mode, name, repeat + 1, 'CPU sessions', len(cpu_rows),
                                  'FPGA layers', len(layer_rows), flush=True)
                finally:
                    bench.close(model)
        summary = summarize_profile(records)
        save(run / (prefix + 'profile_summary.json'), dict(identity=identity(), completed=True, actual_hardware=True,
                                               profiling_only=True, summary=summary,
                                               baseline_only=baseline_only, reference_sha256=reference_sha256))
        write_csv(run / (prefix + 'profile_summary.csv'), summary)
        for mode in modes:
            for name in names:
                top = sorted([r for r in summary if r['mode'] == mode and r['audio'] == name],
                             key=lambda r: r['median_ms'], reverse=True)[:8]
                print('BASELINE_PROFILE_TOP:' if baseline_only else 'PROFILE_TOP:',
                      json.dumps(dict(mode=mode, audio=name, layers=top)), flush=True)
        print('BASELINE_PROFILE_COMPLETED:' if baseline_only else 'OPT_PROFILE_COMPLETED:',
              run / (prefix + 'profile_summary.json'), flush=True)
        return summary
    except BaseException as error:
        save(run / (prefix + 'profile_failed.json'), dict(error=repr(error), hardware_may_be_active=runtime.UNSAFE))
        raise


def summarize_profile(records):
    groups = {}
    for record in records:
        for row in record['cpu_sessions'] + record['fpga_layers']:
            key = (record['mode'], record['audio'], row['component'], row['name'])
            groups.setdefault(key, []).append(row)
    rows = []
    for (mode, audio, component, name), values in groups.items():
        cpu = component == 'CPU'
        row = dict(mode=mode, audio=audio, component=component, name=name,
                   **statistics([v['cpu_session_ms'] if cpu else v['callback_ms'] for v in values]),
                   input_count=values[0]['inputs']['count'] if cpu else 1,
                   output_count=values[0]['outputs']['count'] if cpu else 1,
                   input_bytes=values[0]['inputs']['bytes'] if cpu else values[0]['input_bytes'],
                   output_bytes=values[0]['outputs']['bytes'] if cpu else values[0]['output_bytes'],
                   input_shape='' if cpu else json.dumps(values[0]['input_shape']),
                   output_shape='' if cpu else json.dumps(values[0]['output_shape']),
                   cin=values[0].get('cin'), cout=values[0].get('cout'), frames=values[0].get('frames'),
                   input_frequency=values[0].get('input_frequency'), kernel=values[0].get('kernel'))
        for k in ('parameter_address_size_switch_ms', 'input_ddr_copy_flush_ms', 'fpga_start_done_ms',
                  'output_invalidate_copy_ms', 'output_concat_ms'):
            row[k] = None if cpu else float(np.median([v.get(k, 0.) for v in values]))
        rows.append(row)
    return sorted(rows, key=lambda r: (r['mode'], r['audio'], -r['median_ms']))
