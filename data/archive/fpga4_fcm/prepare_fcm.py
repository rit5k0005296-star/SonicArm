"""Extract original FCM boundaries and reproduce its complete integer schedule.
Desktop only, writes exclusively in FPGA-4. Does not touch board or V1/2/3.
"""
from pathlib import Path
import copy
import hashlib
import importlib.util
import json
import sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
MODELS = HERE.parents[1]
sys.path.insert(0, str(MODELS/'consistency-test/codex'))
from common import import_runtime, sha256
ort = import_runtime('cpu')
import numpy as np
import onnx
from onnx import helper as h, numpy_helper as nh
spec = importlib.util.spec_from_file_location('v1_readonly', MODELS/'FPGA-1/conv1x1/extract_conv1x1.py')
v1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v1)
MODEL = MODELS/'consistency-test/codex/artifacts/quantization/camplus_int8_qdq.onnx'
MODEL_SHA = 'c0c4103c23301e26aa58e106933bbeaefbfdc7d0708052729b3155f7f824560f'
LUT_AUDIT = []
NATIVE_API = None


def require(ok, message):
    if not ok:
        raise ValueError(message)


def session(model):
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 1
    opts.inter_op_num_threads = 1
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
    return ort.InferenceSession(model.SerializeToString(), opts, providers=['CPUExecutionProvider'])


def quantize(acc, coeff, shift, zp):
    p = acc.astype(np.int64)*coeff.astype(np.int64)[:, None, None]
    mag = np.abs(p)
    whole = mag >> shift
    rem = mag & ((1 << shift)-1)
    whole += (rem > (1 << (shift-1))) | ((rem == (1 << (shift-1))) & ((whole & 1) != 0))
    return np.clip(np.where(p < 0, -whole, whole)+zp, -128, 127).astype(np.int8)


def conv_reference(x, w, bias, zp, stride):
    """Exact integer sums via FP64 GEMM. Every integer partial sum <2**53.
    C++ test bench independently uses signed INT64 nested convolution loops.
    """
    k = w.shape[-1]
    c, f, t = x.shape
    xc = np.pad(x.astype(np.int64)-zp, ((0, 0), (k//2, k//2), (k//2, k//2)))
    windows = np.lib.stride_tricks.sliding_window_view(xc, (k, k), axis=(1, 2))[:, ::stride]
    patches = np.ascontiguousarray(windows.transpose(0, 3, 4, 1, 2)).reshape(c*k*k, -1)
    bound = np.abs(bias.astype(np.int64))+np.abs(w.astype(np.int64)).sum((1, 2, 3))*max(abs(-128-zp), abs(127-zp))
    require(bound.max() <= 2147483647, 'INT32 overflow bound')
    raw = w.reshape(w.shape[0], -1).astype(np.float64) @ patches.astype(np.float64)
    raw += bias.astype(np.float64)[:, None]
    require(np.array_equal(raw, np.rint(raw)), 'FP64 integer reference lost exactness')
    return raw.astype(np.int64).reshape(w.shape[0], (f+stride-1)//stride, t)


def make_lut(model, a, xd, q, kind, skipd=None):
    """Exhaustive original FP32 DQ/(Add)/ReLU/Q, not approximate scale merging."""
    count = 65536 if kind == 'residual' else 256
    x = np.arange(-128, 128, dtype=np.int16).astype(np.int8)
    if kind == 'residual':
        x = np.repeat(x, 256)
    inputs = [h.make_tensor_value_info('x', onnx.TensorProto.INT8, [count])]
    nodes = [h.make_node('DequantizeLinear', ['x', xd.input[1], xd.input[2]], ['dx'])]
    init_names = {xd.input[1], xd.input[2], q.input[1], q.input[2]}
    y = None
    if kind == 'residual':
        y = np.tile(np.arange(-128, 128, dtype=np.int16).astype(np.int8), 256)
        inputs.append(h.make_tensor_value_info('y', onnx.TensorProto.INT8, [count]))
        nodes += [h.make_node('DequantizeLinear', ['y', skipd.input[1], skipd.input[2]], ['dy']),
                  h.make_node('Add', ['dx', 'dy'], ['sum'])]
        init_names.update(skipd.input[1:3])
    nodes += [h.make_node('Relu', ['sum' if kind == 'residual' else 'dx'], ['r']),
              h.make_node('QuantizeLinear', ['r', q.input[1], q.input[2]], ['z'])]
    graph = h.make_graph(nodes, 'exact_original_fcm_post', inputs,
                         [h.make_tensor_value_info('z', onnx.TensorProto.INT8, [count])],
                         [copy.deepcopy(i) for i in model.graph.initializer if i.name in init_names])
    lm = h.make_model(graph, opset_imports=copy.deepcopy(model.opset_import))
    lm.ir_version = model.ir_version
    onnx.checker.check_model(lm)
    dest = HERE/'analysis/lut_models'/((hashlib.sha256(q.name.encode('utf8')).hexdigest()[:16])+'.onnx')
    dest.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(lm, dest)
    feeds = {'x': x}
    dx = (x.astype(np.float32)-a[xd.input[2]].astype(np.float32))*a[xd.input[1]]
    if y is not None:
        feeds['y'] = y
        dx = dx+(y.astype(np.float32)-a[skipd.input[2]].astype(np.float32))*a[skipd.input[1]]
    out = session(lm).run(None, feeds)[0]
    # Independently test all 256/65536 pairs against explicit FP32 semantics.
    manual = np.clip(np.rint(np.maximum(dx, np.float32(0))/a[q.input[1]])+int(a[q.input[2]]), -128, 127).astype(np.int8)
    require(np.array_equal(out, manual), 'Original LUT FP32/ORT discrepancy')
    global NATIVE_API
    library = MODELS/'FPGA-3/full_model_test/desktop_validation/ort_audit/windows1171/onnxruntime-win-x64-1.17.1/lib/onnxruntime.dll'
    native_verified = False
    if library.is_file():
        sys.path.append(str(MODELS/'FPGA-3/full_model_test'))
        from native_ort_bridge import API, Session
        if NATIVE_API is None:
            NATIVE_API = API(library, verify=False)
            require(NATIVE_API.version == '1.17.1', 'Unexpected legacy ORT version')
        native = Session(dest, threads=1, optimize=False, api=NATIVE_API)
        try:
            require(np.array_equal(out, native.run(None, feeds)[0]), 'ORT 1.17.1 / 1.31 LUT mismatch')
        finally:
            native.close()
        native_verified = True
    LUT_AUDIT.append(dict(output_quantizer=q.name, kind=kind, entries=count, numpy_fp32_exact=True,
                          windows_ort_131_exact=True, windows_ort_1171_exact=native_verified,
                          arm_execution_claim=False, table_sha256=hashlib.sha256(out.tobytes()).hexdigest()))
    return out


def apply_post(q, skip, lut, flags):
    if not flags & 1:
        return q.copy()
    index = q.astype(np.int32)+128
    if flags & 4:
        index = index*256+skip.astype(np.int32)+128
    return lut[index]


def save_case(name, layer, x, skip, source, outputs, cases):
    acc = conv_reference(x, layer['w'], layer['bias'], layer['input_zp'], layer['stride_f'])
    q = quantize(acc, layer['coeff'], layer['requant_shift'], layer['output_zp'])
    y = apply_post(q, skip, layer['lut'], layer['flags'])
    fp64 = np.clip(np.rint(acc*layer['ratio'][:, None, None])+layer['output_zp'], -128, 127).astype(np.int8)
    cfg = {k: v for k, v in layer.items() if k not in ('w', 'bias', 'coeff', 'ratio', 'lut')}
    cfg.update(case=name, frames=x.shape[-1], freq=x.shape[-2], source=source,
               fp64_fixed_changed=int(np.count_nonzero(fp64 != q)),
               fp64_fixed_max_lsb=int(np.abs(fp64.astype(np.int16)-q).max()))
    require(cfg['fp64_fixed_max_lsb'] <= 1, 'Fixed-point approximation exceeds 1 LSB')
    dest = HERE/'deploy/cases'/name
    dest.mkdir(parents=True, exist_ok=True)
    arrays = {'input_int8.bin': x, 'weights_int8.bin': layer['w'], 'bias_int32.bin': layer['bias'].astype('<i4'),
              'multiplier_uint32.bin': layer['coeff'], 'post_lut_int8.bin': layer['lut'],
              'residual_int8.bin': skip, 'reference_accum_int32.bin': acc.astype('<i4'),
              'reference_output_int8.bin': y}
    if outputs is not None:
        original_q, original_y = outputs
        cfg.update(original_conv_changed=int(np.count_nonzero(q != original_q)),
                   original_conv_max_lsb=int(np.abs(q.astype(np.int16)-original_q).max()),
                   original_post_changed=int(np.count_nonzero(y != original_y)),
                   original_post_max_lsb=int(np.abs(y.astype(np.int16)-original_y).max()))
        arrays.update(original_conv_int8=original_q, original_post_int8=original_y)
    for key, value in arrays.items():
        np.ascontiguousarray(value).tofile(dest/key)
    cfg['files_sha256'] = {key: sha256(dest/key) for key in arrays}
    (dest/'config.json').write_text(json.dumps(cfg, indent=2), encoding='utf8')
    keys = ('cin', 'cout', 'freq', 'frames', 'kernel', 'stride_f', 'input_zp', 'output_zp', 'requant_shift', 'flags')
    (dest/'config.txt').write_text(' '.join(str(cfg[k]) for k in keys)+'\n', encoding='ascii')
    cases.append(cfg)
    return y


def main():
    require(sha256(MODEL) == MODEL_SHA, 'Original model SHA changed')
    model = onnx.load(MODEL)
    onnx.checker.check_model(model)
    a = {i.name: nh.to_array(i) for i in model.graph.initializer}
    prod = {o: n for n in model.graph.node for o in n.output}
    targets = [n for n in model.graph.node if n.name.startswith('/head/') and n.op_type == 'Conv']
    require(len(targets) == 12, 'FCM must contain 12 Conv2D')
    layers = []
    requested = {}
    for i, n in enumerate(targets, 1):
        attrs = {v.name: h.get_attribute_value(v) for v in n.attribute}
        xd, wd = prod[n.input[0]], prod[n.input[1]]
        bd = prod[n.input[2]]
        q = next(z for z in model.graph.node if z.op_type == 'QuantizeLinear' and z.input[0] == n.output[0])
        dq = prod[n.output[0]+'_DequantizeLinear_Output']
        require(xd.op_type == wd.op_type == bd.op_type == 'DequantizeLinear', 'Expected original QDQ')
        w, bias = a[wd.input[0]], a[bd.input[0]]
        cout, cin, k, kt = w.shape
        require(cin <= 32 and cout == 32 and k == kt and k in (1, 3), 'FCM dimensions')
        require(attrs['group'] == 1 and attrs['dilations'] == [1, 1] and attrs['strides'][1] == 1 and
                attrs['strides'][0] in (1, 2) and attrs['pads'] == [k//2]*4, 'FCM Conv attributes')
        require(w.dtype == np.int8 and np.all(a[wd.input[2]] == 0) and bias.dtype == np.int32 and
                np.all(a[bd.input[2]] == 0), 'Symmetric W / INT32 bias')
        require({v.name: h.get_attribute_value(v) for v in wd.attribute}.get('axis', 1) == 0, 'Weight axis')
        xs, ws, ys = a[xd.input[1]], a[wd.input[1]], a[q.input[1]]
        require(xs.size == ys.size == 1 and a[xd.input[2]].dtype == a[q.input[2]].dtype == np.int8, 'Activation Q params')
        require(np.array_equal(a[bd.input[1]], np.asarray(xs*ws, dtype=np.float32)), 'Original bias scale')
        ratio = float(xs)*ws.astype(np.float64)/float(ys)
        shift = 40
        while np.any(np.floor(ratio*2**shift+.5) > 0xffffffff):
            shift -= 1
        require(shift >= 8 and np.all(ratio > 0), 'Multiplier range')
        coeff = np.floor(ratio*2**shift+.5).astype('<u4')
        require(np.all(coeff > 0), 'Multiplier underflow')
        prefix = n.name.rsplit('/', 2)[0]
        skipd = None
        kind = 'relu'
        if '/shortcut/' in n.name:
            kind = 'identity'
            postq = q
        elif n.name == '/head/conv1/Conv':
            postq = prod['/head/Relu_output_0_QuantizeLinear_Output']
        elif n.name == '/head/conv2/Conv':
            postq = prod['/head/Reshape_output_0_QuantizeLinear_Output']
        elif n.name.endswith('/conv1/Conv'):
            postq = prod[prefix+'/Relu_output_0_QuantizeLinear_Output']
        else:
            kind = 'residual'
            add = next(z for z in model.graph.node if z.name == prefix+'/Add')
            other = next(s for s in add.input if s != dq.output[0])
            skipd = prod[other]
            postq = prod[prefix+'/Relu_1_output_0_QuantizeLinear_Output']
        flags = 2 if kind == 'identity' else (7 if kind == 'residual' else 3)
        lut = np.arange(-128, 128, dtype=np.int16).astype(np.int8) if kind == 'identity' else make_lut(model, a, dq, postq, kind, skipd)
        layer = dict(index=i, name=n.name, cin=cin, cout=cout, kernel=k, stride_f=attrs['strides'][0],
                     input_zp=int(a[xd.input[2]]), output_zp=int(a[q.input[2]]), requant_shift=shift,
                     input_tensor=xd.input[0], conv_output_tensor=q.output[0], post_output_tensor=postq.output[0],
                     skip_tensor=skipd.input[0] if skipd is not None else None, post_kind=kind,
                     w=w, bias=bias, ratio=ratio, coeff=coeff, lut=lut, flags=flags)
        layers.append(layer)
        requested[xd.input[0]] = [1, cin, 'F', 'T']
        requested[q.output[0]] = [1, cout, 'F', 'T']
        requested[postq.output[0]] = [1, 320, 'T'] if n.name == '/head/conv2/Conv' else [1, cout, 'F', 'T']
        if skipd is not None:
            requested[skipd.input[0]] = [1, cout, 'F', 'T']
    prefix_model = v1.prefix_model(model, list(requested), [onnx.TensorProto.INT8]*len(requested), list(requested.values()))
    (HERE/'analysis').mkdir(exist_ok=True)
    onnx.save(prefix_model, HERE/'analysis/original_fcm_probe.onnx')
    runtime = session(prefix_model)
    case_root = HERE/'deploy/cases'
    case_root.mkdir(parents=True, exist_ok=True)
    cases, reconstructions = [], []
    audio_root = MODELS/'FPGA-3/full_model_test/bundle/audio'
    for ai, (filename, frames) in enumerate((('speaker1_a_cn_16k.wav', 300), ('speaker2_a_cn_16k.wav', 67)), 1):
        feature_file = audio_root/(filename+'.fbank.npy')
        feature = np.load(feature_file)[:, :frames, :].copy()
        require(feature.shape == (1, frames, 80), 'Canonical Fbank shape')
        values = dict(zip(requested, runtime.run(None, {'features': feature})))
        computed = {layers[0]['input_tensor']: values[layers[0]['input_tensor']][0]}
        source = dict(audio=filename, audio_sha256=sha256(audio_root/filename), feature_sha256=sha256(feature_file), frames=frames,
                      note='Canonical full-record-normalized Fbank prefix for isolated design verification, not evaluation protocol')
        for layer in layers:
            original_x = values[layer['input_tensor']][0]
            shape = values[layer['conv_output_tensor']][0].shape
            skip = values[layer['skip_tensor']][0] if layer['skip_tensor'] else np.zeros(shape, np.int8)
            original_y = values[layer['post_output_tensor']][0].reshape(shape)
            outputs = (values[layer['conv_output_tensor']][0], original_y)
            save_case('audio%02d_isolated%02d' % (ai, layer['index']), layer, original_x, skip, source, outputs, cases)
            chain_skip = computed[layer['skip_tensor']] if layer['skip_tensor'] else np.zeros(shape, np.int8)
            y = save_case('audio%02d_chain%02d' % (ai, layer['index']), layer, computed[layer['input_tensor']], chain_skip, source, None, cases)
            computed[layer['post_output_tensor']] = y
        final = computed[layers[-1]['post_output_tensor']].reshape(1, 320, frames)
        baseline = values[layers[-1]['post_output_tensor']]
        diff = np.abs(final.astype(np.int16)-baseline.astype(np.int16))
        np.save(HERE/'analysis'/('audio%02d_integer_fcm.npy' % ai), final, allow_pickle=False)
        reconstructions.append(dict(audio=filename, frames=frames, changed=int(np.count_nonzero(diff)),
                                    elements=final.size, max_lsb=int(diff.max()), mean_abs_lsb=float(diff.mean()),
                                    integer_output_sha256=hashlib.sha256(final.tobytes()).hexdigest(),
                                    original_qdq_exact=bool(np.array_equal(final, baseline))))
        print('[EXTRACTED]', filename, frames, 'frames; 12 isolated + 12 chained cases; FCM drift', reconstructions[-1], flush=True)
    (case_root/'all_cases.txt').write_text('\n'.join(c['case'] for c in cases)+'\n', encoding='ascii')
    # RTL: real first Conv, projected shortcut, stride2 Conv, residual fusion, last Conv.
    # Full real channel dimensions; shorter temporal windows keep XSIM manageable.
    (case_root/'rtl_cases.txt').write_text('audio02_isolated01\naudio02_isolated02\naudio02_isolated03\naudio02_isolated04\naudio02_isolated12\n', encoding='ascii')
    report = dict(model_sha256=MODEL_SHA, scope='FCM only; independent original boundaries and true recursively updated integer FCM',
                  layers=12, real_cases=len(cases), scalar_lut_entries_exhaustively_verified=sum(l['lut'].size for l in layers if l['post_kind'] != 'identity'),
                  original_qdq_bit_exact_claim=False, board_tested=False,
                  reconstructions=reconstructions,
                  isolated_original_conv_changed=sum(c.get('original_conv_changed', 0) for c in cases),
                  isolated_original_post_max_lsb=max(c.get('original_post_max_lsb', 0) for c in cases),
                  fixed_vs_fp64_changed=sum(c['fp64_fixed_changed'] for c in cases),
                  lut_audit=LUT_AUDIT,
                  cases=cases)
    (HERE/'reference_report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print('[READY]', len(cases), 'real cases. Original model unchanged; numerical drift retained.', flush=True)


if __name__ == '__main__':
    main()
