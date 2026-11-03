"""Manual paired CPU/FPGA quality pilot using unchanged official recordings/trials.
Resumable per-audio receipts; diagnostic metrics only, no timing or auth claim.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import importlib.util
import json
import platform
import sys
import numpy as np
sys.dont_write_bytecode = True
WORK = Path(__file__).resolve().parent
ROOT = WORK.parent
assert (ROOT/'runtime_core.py').is_file(), 'evaluation must be inside full_model_test'
sys.path.insert(0, str(ROOT))
import runtime_core as core
import compatible_all55 as all55
from compatible_one_layer import route
from all55_fast_diagnostic import reference_and_progress, self_check, validate as validate_reference
from native_ort_bridge import backend_details

DATA = WORK / 'data/eval'


def validate():
    core.verify_manifest(); all55.validate(); validate_reference()
    path = WORK / 'manifest.json'
    manifest = json.loads(path.read_text(encoding='utf-8'))
    for name, expected in manifest['files'].items():
        item = (WORK / name).resolve()
        if not item.is_relative_to(WORK):
            raise ValueError('Pilot path escapes root')
        if item.suffix == '.ipynb':
            if core.notebook_sources(item) != manifest['notebook_cells'][name]:
                raise ValueError('Pilot notebook code changed')
        elif core.digest(item) != expected:
            raise ValueError('Pilot input changed: ' + name)
    return core.digest(path)


def require55(backend):
    matches = []
    for path in (core.HERE / 'test_results').glob('compatible_all55_fast_*/fpga/correctness.json'):
        row = json.loads(path.read_text(encoding='utf-8'))
        if (row.get('diagnostic_completed') and row.get('hardware_consistency_gate') is True
                and row.get('diagnostic_manifest') == core.digest(all55.ASSETS / 'manifest.json')
                and row.get('exact_reference_manifest') == core.digest(core.HERE / 'all55_fast_manifest.json')
                and row.get('native_backend') == backend):
            matches.append(path)
    if not matches:
        raise ValueError('Matching actual 03b all55 hardware consistency report required')
    path = sorted(matches, key=lambda p: p.stat().st_mtime)[-1]
    return {'file': str(path), 'sha256': core.digest(path)}


def protocol_module():
    spec = importlib.util.spec_from_file_location('pilot_official_protocol', core.BUNDLE / 'protocol_reference.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def record_signature(identity, name, path):
    return {'run_identity': identity, 'audio': name, 'audio_sha256': core.digest(path)}


def cached_vector(directory, key, signature, is_fpga):
    receipt_path = directory / (key + '.json')
    try:
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        raw_path = directory / (key + '.raw.npy')
        vector_path = directory / (key + '.npy')
        if (receipt['signature'] != signature or receipt['FPGA_generated'] != is_fpga
                or core.digest(raw_path) != receipt['raw_sha256']
                or core.digest(vector_path) != receipt['vector_sha256']):
            return None
        raw = np.load(raw_path, allow_pickle=False)
        vector = np.load(vector_path, allow_pickle=False)
        if raw.shape != (1, 192) or not np.isfinite(raw).all() or not np.array_equal(core.normalize(raw), vector):
            return None
        return receipt
    except (OSError, ValueError, KeyError):
        return None


def run(stage, directory, cpu_directory=None, session_factory=None, backend=None):
    if stage not in ('cpu', 'fpga'):
        raise ValueError('Invalid stage')
    if stage == 'fpga' and (platform.system() != 'Linux' or platform.machine().lower() not in ('armv7l', 'armv8l')):
        raise ValueError('Actual FPGA pilot must run manually on ARM Linux')
    directory = Path(directory).resolve()
    if not directory.is_relative_to(WORK / 'results'):
        raise ValueError('Output must remain in evaluation/results')
    directory.mkdir(parents=True, exist_ok=True)
    package = validate(); backend = backend or backend_details()
    identity_data = {'package': package, 'backend': backend,
        'compatible_models': core.digest(all55.ASSETS / 'manifest.json'),
        'reference': core.digest(core.HERE / 'all55_fast_manifest.json'),
        'frontend': 'frozen original canonical Fbank for complete recordings', 'threads': 1, 'optimization': 'OFF',
        'numpy': np.__version__, 'platform': platform.platform()}
    identity = hashlib.sha256(json.dumps(identity_data, sort_keys=True).encode()).hexdigest()
    prerequisite = None
    if stage == 'fpga':
        prerequisite = require55(backend)
        if cpu_directory is None:
            raise ValueError('Run paired CPU pilot first')
        cpu_directory = Path(cpu_directory).resolve()
        if not cpu_directory.is_relative_to(WORK / 'results'):
            raise ValueError('CPU output must remain in evaluation/results')
        cpu = json.loads((cpu_directory / 'summary.json').read_text(encoding='utf-8'))
        if not (cpu.get('completed') and cpu.get('stage') == 'cpu' and cpu.get('run_identity') == identity):
            raise ValueError('Matching completed CPU pilot required')
    protocol = protocol_module()
    enrollment, tests = protocol.load_lists(DATA)
    names = list(dict.fromkeys([*enrollment.values(), *tests]))
    subset = json.loads((WORK / 'data/subset.json').read_text(encoding='utf-8'))
    feature_records = {r['protocol_name']: r for r in subset['recordings']}
    vectors = directory / 'embeddings'; vectors.mkdir(exist_ok=True)
    info = {'stage': stage, 'run_identity': identity, 'identity_data': identity_data,
            'subset_pilot_only': True, 'threshold': None, 'performance_claim': False,
            'prior_hardware_report': prerequisite, 'audio_count': len(names),
            'protocol': 'unchanged complete official enrollment and test audio; unchanged filtered official trial labels/order',
            'feature_scope': 'Canonical Fbank generated on desktop from full original recordings. Board runs full models/L2/scoring on identical frozen features; no board frontend or audio-capture claim.'}
    core.save(directory / 'run_info.json', info)
    runtime = None; records = []; computed = 0
    mapping = all55.validate()
    try:
        with route(mapping, session_factory), reference_and_progress() as original_reference:
            if stage == 'fpga':
                core.save(directory / 'reference_check.json', {'checks': self_check(original_reference)})
            for i, name in enumerate(names, 1):
                path = protocol.resolve_audio(DATA, name)
                signature = record_signature(identity, name, path)
                key = hashlib.sha256(name.encode()).hexdigest()
                receipt = cached_vector(vectors, key, signature, stage == 'fpga')
                if receipt is not None:
                    print('[PILOT]', stage, i, '/', len(names), name, 'CACHE_VALID', flush=True)
                else:
                    print('[PILOT]', stage, i, '/', len(names), name, 'START', flush=True)
                    feature_record = feature_records[name]
                    features = np.load(WORK / feature_record['features'], allow_pickle=False)
                    if (features.dtype != np.float32 or features.shape != (1, feature_record['feature_frames'], 80)
                            or not np.isfinite(features).all()):
                        raise ValueError('Invalid frozen canonical Fbank')
                    print('  canonical frames', features.shape[1], 'seconds', feature_record['audio_seconds'], flush=True)
                    if runtime is None:
                        runtime = core.FullCPU(1) if stage == 'cpu' else core.Hybrid('all55', 'fpga', 1, False)
                    if stage == 'fpga':
                        runtime.audit_sink = lambda row, key=key: core.save(
                            directory / 'layers' / key / ('layer%02d.json' % row['index']), row)
                    raw, network = runtime.run(features, audit=stage == 'fpga')
                    vector = core.normalize(raw)
                    raw_path = vectors / (key + '.raw.npy'); vector_path = vectors / (key + '.npy')
                    np.save(raw_path, raw); np.save(vector_path, vector)
                    receipt = {'signature': signature, 'FPGA_generated': stage == 'fpga',
                        'raw_sha256': core.digest(raw_path), 'vector_sha256': core.digest(vector_path),
                        'frames': int(features.shape[1]), 'audio_seconds': feature_record['audio_seconds'],
                        'features_sha256': feature_record['features_sha256'],
                        'layers': len(network['layers']),
                        'total_hardware_chunks': sum(v.get('chunks', 0) for v in network['layers']),
                        'local_hardware_checks_completed': stage == 'fpga'}
                    core.save(vectors / (key + '.json'), receipt)
                    computed += 1
                    print('[PILOT]', stage, i, '/', len(names), name, 'SAVED', flush=True)
                records.append({'audio': name, **receipt})
                core.save(directory / 'audio_receipts.json', records)
        scores, labels, total = protocol.score_trials(DATA, enrollment, tests, vectors, directory, False)
        metrics, thresholds, far, frr = protocol.detection_metrics(scores, labels, .01, 1., 1., None)
        metrics.update(subset_pilot_only=True, threshold_calibrated=False, performance_claim=False,
                       note='Small fixed subset; descriptive EER/minDCF only. Evaluation-derived threshold is not an authentication threshold.')
        core.save(directory / 'metrics.json', metrics)
        np.savez(directory / 'det_curve.npz', thresholds=thresholds, far=far, frr=frr)
        summary = {**info, 'completed': True, 'new_audio': computed, 'cache_hits': len(names)-computed,
            'FPGA_executed_this_run': stage == 'fpga' and computed > 0,
            'all_vectors_FPGA_generated': stage == 'fpga', 'metrics': metrics}
        core.save(directory / 'summary.json', summary)
        print('PILOT_METRICS:', json.dumps(metrics, ensure_ascii=False), flush=True)
        if stage == 'fpga':
            comparison = compare_runs(cpu_directory, directory)
            core.save(directory / 'paired_comparison.json', comparison)
            print('PAIRED_SCORE_CHANGE:', json.dumps(comparison['scores'], ensure_ascii=False), flush=True)
        print('PILOT_COMPLETED:', directory / 'summary.json', flush=True)
        return summary
    except Exception as error:
        core.save(directory / 'failure.json', {**info, 'completed': False, 'error': repr(error)})
        raise
    finally:
        if runtime is not None:
            runtime.close()


def compare_runs(cpu_directory, fpga_directory):
    cpu_directory = Path(cpu_directory); fpga_directory = Path(fpga_directory)
    a = json.loads((cpu_directory / 'summary.json').read_text(encoding='utf-8'))
    b = json.loads((fpga_directory / 'summary.json').read_text(encoding='utf-8'))
    if a['run_identity'] != b['run_identity'] or not a['completed'] or not b['completed']:
        raise ValueError('Paired run identity mismatch')
    with np.load(cpu_directory / 'trial_scores.npz') as aa, np.load(fpga_directory / 'trial_scores.npz') as bb:
        x = aa['scores']; y = bb['scores']; labels = aa['labels']
        if not np.array_equal(labels, bb['labels']) or x.shape != y.shape:
            raise ValueError('Paired trial lists differ')
    trials = [line.split() for line in (DATA / 'lists/trials.lst').read_text().splitlines() if line.strip()]
    if len(trials) != len(x):
        raise ValueError('Trial count mismatch')
    with (fpga_directory / 'paired_scores.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f); writer.writerow(['speaker', 'audio', 'label', 'cpu_score', 'fpga_score', 'delta'])
        for trial, cpu, fpga in zip(trials, x, y):
            writer.writerow([*trial, float(cpu), float(fpga), float(fpga-cpu)])
    delta = y.astype(np.float64)-x.astype(np.float64)
    rows = []
    for item in json.loads((cpu_directory / 'audio_receipts.json').read_text(encoding='utf-8')):
        name = item['audio']; key = hashlib.sha256(name.encode()).hexdigest()
        cpu = np.load(cpu_directory / 'embeddings' / (key+'.raw.npy'), allow_pickle=False)
        fpga = np.load(fpga_directory / 'embeddings' / (key+'.raw.npy'), allow_pickle=False)
        rows.append({'audio': name, **core.compare(cpu, fpga)})
    return {'subset_pilot_only': True, 'threshold': None, 'performance_claim': False,
            'scores': {'trials': len(x), 'mean_abs_delta': float(np.mean(np.abs(delta))),
                       'max_abs_delta': float(np.max(np.abs(delta))),
                       'above_existing_0_001_drift_limit': int(np.count_nonzero(np.abs(delta) > .001))},
            'embeddings': rows, 'cpu_metrics': a['metrics'], 'fpga_metrics': b['metrics'],
            'EER_percentage_point_change': b['metrics']['eer_percent']-a['metrics']['eer_percent'],
            'minDCF_change': b['metrics']['min_dcf_normalized']-a['metrics']['min_dcf_normalized'],
            'model_acceptance': 'not established by a small pilot; original failed smoke gate remains failed'}


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['cpu', 'fpga'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cpu-directory', type=Path)
    args = parser.parse_args()
    if platform.system() != 'Linux' or platform.machine().lower() not in ('armv7l', 'armv8l'):
        parser.error('Execute manually on ARM Linux')
    run(args.stage, args.output, args.cpu_directory)
