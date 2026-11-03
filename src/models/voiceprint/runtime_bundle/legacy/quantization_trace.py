"""CPU diagnostic: find the first INT8 divergence, then inspect its actual float input.

The small protobuf reader only removes graph-output declarations. It neither edits
operators nor interprets the network. Real inference always uses ONNX Runtime.
"""
from pathlib import Path
import argparse
import json
import platform
import sys
import numpy as np
from runtime_core import HERE, BUNDLE, digest, save, compare, verify_manifest
from native_ort_bridge import Session, backend_details


def varint(data, offset):
    value = 0
    for shift in range(0, 70, 7):
        if offset >= len(data):
            raise ValueError('Truncated protobuf varint')
        byte = data[offset]; offset += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, offset
    raise ValueError('Invalid protobuf varint')


def encode_varint(value):
    result = bytearray()
    while value > 127:
        result.append((value & 127) | 128); value >>= 7
    result.append(value)
    return bytes(result)


def fields(data):
    offset = 0
    while offset < len(data):
        start = offset
        tag, offset = varint(data, offset)
        wire = tag & 7; number = tag >> 3
        if wire == 2:
            size, offset = varint(data, offset)
            body = data[offset:offset+size]; offset += size
        elif wire == 0:
            _, offset = varint(data, offset); body = None
        elif wire in (1, 5):
            offset += 8 if wire == 1 else 4; body = None
        else:
            raise ValueError('Unsupported protobuf wire type')
        if not number or offset > len(data):
            raise ValueError('Truncated protobuf field')
        yield number, wire, body, data[start:offset]


def select_outputs(model_bytes, requested):
    requested = set(requested); found = set(); result = []; graphs = 0
    for number, wire, body, raw in fields(model_bytes):
        if number != 7:
            result.append(raw); continue
        if wire != 2:
            raise ValueError('Invalid ModelProto.graph')
        graphs += 1; graph = []
        for field, kind, value, item in fields(body):
            if field == 12:
                names = [v.decode('utf-8') for n, w, v, _ in fields(value) if n == 1 and w == 2]
                if len(names) != 1:
                    raise ValueError('Invalid graph output name')
                if names[0] not in requested:
                    continue
                found.add(names[0])
            graph.append(item)
        graph_bytes = b''.join(graph)
        result.append(encode_varint((7 << 3) | 2) + encode_varint(len(graph_bytes)) + graph_bytes)
    if graphs != 1 or found != requested:
        raise ValueError('Missing or duplicated graph outputs')
    return b''.join(result)


def integer_difference(reference, actual):
    if reference.shape != actual.shape or reference.dtype != actual.dtype:
        raise ValueError('Quantized tensor metadata mismatch')
    d = np.abs(reference.astype(np.int32) - actual.astype(np.int32))
    return {'changed': int(np.count_nonzero(d)), 'elements': int(d.size),
            'max_lsb': int(d.max()), 'mean_lsb': float(d.mean())}


def numpy_quantize(x, spec):
    scale = np.asarray(spec['scale'], dtype=np.float32)
    zero = np.asarray(spec['zero_point'], dtype=np.int32)
    if scale.size > 1:
        shape = [1] * x.ndim; shape[spec['axis']] = scale.size
        scale = scale.reshape(shape); zero = zero.reshape(shape)
    qtype = np.dtype(spec['dtype']); info = np.iinfo(qtype)
    return np.clip(np.rint(x / scale).astype(np.int64) + zero,
                   info.min, info.max).astype(qtype)


def probe(directory, factory=Session, backend=None):
    directory = Path(directory).resolve()
    if not directory.is_relative_to(HERE):
        raise ValueError('Output must stay within full_model_test')
    directory.mkdir(parents=True, exist_ok=True)
    assets = HERE / 'quant_trace_assets'
    manifest = json.loads((assets / 'manifest.json').read_text(encoding='utf-8'))
    for name, expected in manifest['files'].items():
        path = (HERE / name).resolve()
        if not path.is_relative_to(HERE):
            raise ValueError('Trace package path escapes root')
        if path.suffix == '.ipynb':
            doc = json.loads(path.read_text(encoding='utf-8'))
            sources = [''.join(c.get('source', [])) for c in doc['cells'] if c['cell_type'] == 'code']
            if sources != manifest['notebook_cells'][name]:
                raise ValueError('Trace notebook code changed: ' + name)
        elif digest(path) != expected:
            raise ValueError('Trace package hash mismatch: ' + name)
    metadata = json.loads((assets / 'metadata.json').read_text(encoding='utf-8'))
    report = {'scope': 'CPU quantization divergence diagnosis; no FPGA or acceptance relaxation',
              'fpga_executed': False, 'threshold': None, 'bundle_version': verify_manifest(),
              'backend': backend or backend_details(), 'numpy': np.__version__, 'nodes': []}
    session = None
    try:
        features_path = BUNDLE / metadata['features']
        if digest(features_path) != metadata['features_sha256']:
            raise ValueError('Features changed')
        features = np.load(features_path, allow_pickle=False)
        specs = metadata['quantizers']; template = (assets / 'template.onnx').read_bytes()
        wanted = ['embedding'] + [s['output'] for s in specs]
        path = directory / 'quantized_outputs.onnx'
        path.write_bytes(select_outputs(template, wanted))
        session = factory(path)
        outputs = session.run(None, {'features': features})
        tensors = dict(zip([v.name for v in session.get_outputs()], outputs))
        session.close(); session = None
        raw = tensors['embedding']
        board_reference = np.load(assets / 'board00d_embedding.npy', allow_pickle=False)
        report['trace_vs_board00d'] = compare(board_reference, raw)
        report['trace_exact_board00d'] = bool(np.array_equal(board_reference, raw))
        desktop = np.load(BUNDLE / 'audio' / (metadata['audio'] + '.desktop_qdq_embedding.npy'), allow_pickle=False)
        report['embedding_vs_desktop131'] = compare(desktop, raw)
        np.save(directory / 'trace_embedding.npy', raw)
        changed_specs = []
        with np.load(assets / 'desktop131_quantized.npz', allow_pickle=False) as new, \
             np.load(assets / 'desktop117_quantized.npz', allow_pickle=False) as old:
            for spec in specs:
                actual = tensors[spec['output']]
                row = {'node_index': spec['index'], 'name': spec['name'], 'tensor': spec['output'],
                       'vs_desktop131': integer_difference(new[spec['output']], actual),
                       'vs_windows117': integer_difference(old[spec['output']], actual)}
                report['nodes'].append(row)
                if row['vs_desktop131']['changed'] or row['vs_windows117']['changed']:
                    changed_specs.append(spec)
        for key in ('vs_desktop131', 'vs_windows117'):
            first = next((r for r in report['nodes'] if r[key]['changed']), None)
            report['first_' + key] = first
            print('FIRST_' + key.upper() + ':', json.dumps(first, ensure_ascii=False), flush=True)
        # Release all large tensors before the second complete-model pass.
        del tensors, outputs
        capture_specs = changed_specs[:3]
        report['same_input_quantizer_checks'] = []
        if capture_specs:
            names = ['embedding'] + list(dict.fromkeys(n for s in capture_specs for n in (s['input'], s['output'])))
            path = directory / 'first_difference_inputs.onnx'
            path.write_bytes(select_outputs(template, names))
            session = factory(path)
            values = session.run(None, {'features': features})
            captured = dict(zip([v.name for v in session.get_outputs()], values))
            session.close(); session = None
            report['second_pass_exact_first_pass'] = bool(np.array_equal(raw, captured['embedding']))
            np.savez_compressed(directory / 'first_difference_inputs.npz', **captured)
            for spec in capture_specs:
                x = captured[spec['input']]; actual = captured[spec['output']]
                reference = numpy_quantize(x, spec)
                row = {'name': spec['name'], 'input': spec['input'], 'output': spec['output'],
                       'same_input_numpy_vs_ORT': integer_difference(reference, actual),
                       'input_shape': list(x.shape), 'input_min': float(x.min()), 'input_max': float(x.max())}
                report['same_input_quantizer_checks'].append(row)
                print('SAME_INPUT_QUANTIZER:', json.dumps(row, ensure_ascii=False), flush=True)
        report['completed'] = True
        report['next'] = 'Return first divergence and captured arrays before deciding runtime/FPGA changes.'
        save(directory / 'quant_trace.json', report)
        print('TRACE_EXACT_BOARD00D:', report['trace_exact_board00d'], flush=True)
        print('TRACE_COMPLETED:', directory / 'quant_trace.json', flush=True)
    except Exception as error:
        report['completed'] = False; report['error'] = repr(error)
        save(directory / 'quant_trace.json', report)
        raise
    finally:
        if session:
            session.close()
    return report


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if platform.system() != 'Linux' or platform.machine().lower() not in ('armv7l', 'armv8l'):
        parser.error('Execute manually on ARM Linux')
    probe(args.output)
