"""User-run CPU-only AveragePool diagnosis; original production model is retained."""
from pathlib import Path
import argparse
import json
import platform
import sys
import numpy as np
from runtime_core import HERE, BUNDLE, digest, save, verify_manifest, frontend, compare, normalize
from native_ort_bridge import Session, backend_details


def parity(a, b):
    metric = compare(a, b)
    metric['pass'] = bool(np.allclose(a, b, atol=1e-4, rtol=1e-3)
                          and metric['cosine'] >= 0.99999)
    return metric


def probe(directory, factory=Session, backend=None):
    directory = Path(directory).resolve()
    if not directory.is_relative_to(HERE):
        raise ValueError('Output must remain within full_model_test')
    directory.mkdir(parents=True, exist_ok=True)
    assets = HERE / 'pool_diagnostics'
    manifest = json.loads((assets / 'manifest.json').read_text(encoding='utf-8'))
    for name, expected in manifest['files'].items():
        path = (HERE / name).resolve()
        if not path.is_relative_to(HERE) or digest(path) != expected:
            raise ValueError('Pool diagnosis package hash mismatch: ' + name)
    version = verify_manifest()
    if digest(BUNDLE / 'camplus_int8_qdq.onnx') != manifest['original_model_sha256']:
        raise ValueError('Original model changed')
    result = {'scope': 'CPU AveragePool and QDQ numerical diagnosis; no FPGA or accuracy claim',
              'fpga_executed': False, 'threshold': None, 'bundle_version': version,
              'diagnostic_manifest': manifest, 'backend': backend or backend_details(),
              'numpy_version': np.__version__, 'pool_checks': [], 'audio': []}
    try:
        # Dynamic lengths include full windows, partial windows, and inputs shorter than K.
        for kind in ('original', 'compat'):
            session = factory(assets / ('pool_' + kind + '.onnx'))
            try:
                for length in (45, 99, 100, 101, 185, 200, 245, 265, 300):
                    x = (np.arange(length, dtype=np.float32) / 100 - 0.75).reshape(1, 1, -1)
                    expected = np.asarray([x[..., start:start+100].mean(dtype=np.float32)
                                           for start in range(0, length, 100)], dtype=np.float32).reshape(1, 1, -1)
                    actual = session.run(None, {'x': x})[0]
                    error = float(np.max(np.abs(actual - expected)))
                    row = {'kind': kind, 'length': length, 'expected': expected.reshape(-1).tolist(),
                           'actual': actual.reshape(-1).tolist(), 'max_abs': error,
                           'pass': bool(np.allclose(actual, expected, atol=1e-6, rtol=1e-6))}
                    result['pool_checks'].append(row)
            finally:
                session.close()
        result['original_pool_gate'] = all(r['pass'] for r in result['pool_checks'] if r['kind'] == 'original')
        result['compatible_pool_gate'] = all(r['pass'] for r in result['pool_checks'] if r['kind'] == 'compat')
        print('ORIGINAL_POOL_GATE:', result['original_pool_gate'], flush=True)
        print('COMPATIBLE_POOL_GATE:', result['compatible_pool_gate'], flush=True)
        save(directory / 'pool_gate.json', result)
        protocol = json.loads((BUNDLE / 'smoke_protocol.json').read_text(encoding='utf-8'))
        samples = []
        for item in protocol['audio']:
            features, _ = frontend(BUNDLE / item['path'], 'numpy16k')
            golden = np.load(BUNDLE / item['features'], allow_pickle=False)
            diff = np.abs(features - golden)
            if features.shape != golden.shape or diff.max() > 1e-4 or diff.mean() > 1e-5:
                raise AssertionError('Frontend gate failed')
            samples.append((item, features, golden))
        embeddings = {}
        for kind, model in [('original', BUNDLE / 'camplus_int8_qdq.onnx'),
                            ('compat', assets / 'camplus_pool_compat.onnx')]:
            session = factory(model)
            try:
                embeddings[kind] = []
                for item, features, golden in samples:
                    raw = session.run(None, {'features': golden})[0]
                    if raw.shape != (1, 192) or not np.isfinite(raw).all():
                        raise ValueError('Invalid full-model embedding')
                    embeddings[kind].append(raw)
                    np.save(directory / (item['id'] + '.' + kind + '.raw_embedding.npy'), raw)
                    print('[FULL CPU]', kind, item['id'], 'norm', float(np.linalg.norm(raw)), flush=True)
            finally:
                session.close()
        # Test real decoded audio features as well, after retaining same-Fbank comparisons.
        session = factory(assets / 'camplus_pool_compat.onnx')
        try:
            for i, (item, features, golden) in enumerate(samples):
                actual = session.run(None, {'features': features})[0]
                ref = np.load(BUNDLE / 'audio' / (item['id'] + '.desktop_qdq_embedding.npy'), allow_pickle=False)
                old_ref = np.load(assets / (item['id'] + '.windows117_compat.npy'), allow_pickle=False)
                a = embeddings['original'][i]; b = embeddings['compat'][i]
                row = {'audio': item['id'], 'features_sha256': digest(BUNDLE / item['features']),
                       'before_vs_desktop131': parity(ref, a), 'after_vs_desktop131': parity(ref, b),
                       'after_vs_windows117_same_compat_model': parity(old_ref, b),
                       'before_vs_after': compare(a, b),
                       'real_audio_vs_stored_fbank': parity(b, actual)}
                result['audio'].append(row)
                print('  AFTER_DESKTOP_COSINE', item['id'], row['after_vs_desktop131']['cosine'],
                      'strict_pass', row['after_vs_desktop131']['pass'], flush=True)
                save(directory / 'pool_gate.json', result)
        finally:
            session.close()
        scores = {}
        for kind, values in embeddings.items():
            vectors = [normalize(e) for e in values]
            scores[kind] = {'speaker1_a_vs_speaker1_b': float(np.dot(vectors[0], vectors[1])),
                            'speaker1_a_vs_speaker2_a': float(np.dot(vectors[0], vectors[2]))}
        result['similarity_scores'] = scores
        result['desktop_gate_before'] = all(r['before_vs_desktop131']['pass'] for r in result['audio'])
        result['desktop_gate_after'] = all(r['after_vs_desktop131']['pass'] for r in result['audio'])
        result['real_audio_gate'] = all(r['real_audio_vs_stored_fbank']['pass'] for r in result['audio'])
        result['diagnostic_completed'] = True
        result['next'] = 'Return this report before FPGA. Strict desktop gate unchanged; compatible model is diagnostic only.'
        save(directory / 'pool_gate.json', result)
        print('DESKTOP_GATE_BEFORE:', result['desktop_gate_before'], flush=True)
        print('DESKTOP_GATE_AFTER:', result['desktop_gate_after'], flush=True)
        print('REAL_AUDIO_GATE:', result['real_audio_gate'], flush=True)
        print('DIAGNOSTIC_COMPLETED; return output before FPGA:', directory / 'pool_gate.json', flush=True)
    except Exception as error:
        result['diagnostic_completed'] = False
        result['error'] = repr(error)
        save(directory / 'pool_gate.json', result)
        raise
    return result


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if platform.system() != 'Linux' or platform.machine().lower() not in ('armv7l', 'armv8l'):
        parser.error('Execute manually on the ARM Linux board')
    probe(args.output)
