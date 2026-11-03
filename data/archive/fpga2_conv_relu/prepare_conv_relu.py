"""Extract V2-A parameters and ONNX references using V1's verified real internal inputs.

Run with E:/condaData/envs_dirs/python3.11/python.exe -B.
Only writes inside this desktop conv_relu directory; never writes to Samba.
"""
from pathlib import Path
import copy
import hashlib
import json
import shutil
import sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
MODELS = HERE.parents[1]
V1 = MODELS / 'FPGA-1/conv1x1'
sys.path.insert(0, str(MODELS / 'consistency-test/codex'))
from common import import_runtime, sha256
import numpy as np
import onnx
from onnx import helper as h, numpy_helper as nh


def require(condition, message):
    if not condition:
        raise ValueError(message)


def q40_quantize(acc, q40, zp):
    product = acc.astype(np.int64) * q40.astype(np.int64)[:, None]
    magnitude = np.abs(product)
    whole = magnitude >> 40
    fraction = magnitude & ((1 << 40) - 1)
    whole += (fraction > (1 << 39)) | ((fraction == (1 << 39)) & ((whole & 1) != 0))
    return np.clip(np.where(product < 0, -whole, whole) + zp, -128, 127).astype(np.int8)


def main():
    model_path = MODELS / 'consistency-test/codex/artifacts/quantization/camplus_int8_qdq.onnx'
    model_hash = sha256(model_path)
    metadata = json.loads(model_path.with_suffix('.export.json').read_text(encoding='utf-8'))
    require(metadata['onnx_sha256'] == model_hash and metadata.get('quantization'), 'Model provenance mismatch')
    original_files = [V1 / name for name in ('conv1x1.cpp', 'conv1x1.h', 'tb_conv1x1.cpp', 'layer_params.h')]
    original_hashes = {str(p): sha256(p) for p in original_files}
    m = onnx.load(model_path)
    onnx.checker.check_model(m)
    a = {v.name: nh.to_array(v) for v in m.graph.initializer}
    prod = {o: n for n in m.graph.node for o in n.output}
    consumers = {}
    for n in m.graph.node:
        for x in n.input:
            consumers.setdefault(x, []).append(n)
    conv = next(n for n in m.graph.node if n.name == '/xvector/block1/tdnnd1/linear1/Conv')
    attrs = {v.name: h.get_attribute_value(v) for v in conv.attribute}
    require(attrs['kernel_shape'] == [1] and attrs['strides'] == [1] and attrs['pads'] == [0, 0]
            and attrs['dilations'] == [1] and attrs['group'] == 1, 'Unsupported Conv')
    chain = []
    tensor = conv.output[0]
    for op in ('QuantizeLinear', 'DequantizeLinear', 'Relu', 'QuantizeLinear', 'DequantizeLinear'):
        nodes = consumers[tensor]
        require(len(nodes) == 1 and nodes[0].op_type == op, 'Unexpected post-Conv graph boundary')
        chain.append(nodes[0])
        tensor = nodes[0].output[0]
    q1, dq1, relu, q2, dq2 = chain
    xd, wd, bd = (prod[x] for x in conv.input)
    require(all(n.op_type == 'DequantizeLinear' for n in (xd, wd, bd)), 'QDQ Conv required')
    require({v.name: h.get_attribute_value(v) for v in wd.attribute}.get('axis', 1) == 0, 'Weight axis must be 0')
    weights = a[wd.input[0]]
    bias = a[bd.input[0]]
    xs, xz, ws = a[xd.input[1]], a[xd.input[2]], a[wd.input[1]]
    ys, yz = a[q1.input[1]], a[q1.input[2]]
    require(weights.shape == (128, 128, 1) and weights.dtype == np.int8, 'Weight shape/type')
    require(np.all(a[wd.input[2]] == 0), 'V2-A requires weight ZP 0')
    require(bias.shape == (128,) and bias.dtype == np.int32 and np.all(a[bd.input[2]] == 0), 'Bias shape/type')
    require(xs.size == ys.size == xz.size == yz.size == 1 and xz.dtype == yz.dtype == np.int8, 'Activation quantization')
    require(np.array_equal(a[bd.input[1]], np.asarray(xs * ws, dtype=np.float32)), 'Bias scale mismatch')
    require(np.all(np.isfinite(ws)) and np.all(ws > 0) and float(xs) > 0 and float(ys) > 0, 'Invalid scales')
    require(np.array_equal(a[dq1.input[1]], ys) and np.array_equal(a[dq1.input[2]], yz), 'Q1/DQ1 mismatch')
    multipliers = float(xs) * ws.astype(np.float64) / float(ys)
    q40_float = np.floor(multipliers * (1 << 40) + .5)
    require(np.all(q40_float >= 1) and np.all(q40_float <= 0xffffffff), 'Q40 uint32 overflow')
    q40 = q40_float.astype('<u4')
    centered_w = weights[:, :, 0].astype(np.int64)
    bound = np.abs(bias.astype(np.int64)) + np.abs(centered_w).sum(1) * max(abs(-128-int(xz)), abs(127-int(xz)))
    require(int(bound.max()) <= 2147483647, 'Partial INT32 sums not proven safe')
    ort = import_runtime('cpu')
    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1

    def session(nodes, inputs, outputs, name):
        used = {x for n in nodes for x in n.input}
        graph = h.make_graph(copy.deepcopy(nodes), name, inputs, outputs,
                             [copy.deepcopy(v) for v in m.graph.initializer if v.name in used])
        model = h.make_model(graph, opset_imports=m.opset_import, ir_version=m.ir_version)
        onnx.checker.check_model(model)
        return ort.InferenceSession(model.SerializeToString(), options, providers=['CPUExecutionProvider'])

    lut_session = session([dq1, relu, q2],
        [h.make_tensor_value_info(q1.output[0], onnx.TensorProto.INT8, [256])],
        [h.make_tensor_value_info(q2.output[0], onnx.TensorProto.INT8, [256])], 'post_lut')
    codes = np.arange(-128, 128, dtype=np.int16).astype(np.int8)
    lut = lut_session.run(None, {q1.output[0]: codes})[0]
    rs, rz = float(a[q2.input[1]]), int(a[q2.input[2]])
    formula = np.clip(np.rint(np.maximum(0, (codes.astype(np.float64)-int(yz))*float(ys))/rs)+rz, -128, 127).astype(np.int8)
    np.testing.assert_array_equal(lut, formula)
    shape = [1, 128, 150]
    fused = session([xd, wd, bd, conv]+chain[:4],
        [h.make_tensor_value_info(xd.input[0], onnx.TensorProto.INT8, shape)],
        [h.make_tensor_value_info(q1.output[0], onnx.TensorProto.INT8, shape),
         h.make_tensor_value_info(q2.output[0], onnx.TensorProto.INT8, shape)], 'conv_relu')
    manifest = json.loads((V1/'deploy/cases/cases.json').read_text(encoding='utf-8'))
    rows = []
    for item in manifest['cases']:
        source = V1/'deploy/cases'/item['directory']
        require(source.resolve().parent == (V1/'deploy/cases').resolve(), 'Unsafe case path')
        np.testing.assert_array_equal(np.fromfile(source/'weights_int8.bin', dtype='i1').reshape(weights.shape), weights)
        np.testing.assert_array_equal(np.fromfile(source/'bias_int32.bin', dtype='<i4'), bias)
        x = np.fromfile(source/'input_int8.bin', dtype='i1').reshape(128,150)
        acc = centered_w @ (x.astype(np.int64)-int(xz)) + bias.astype(np.int64)[:,None]
        np.testing.assert_array_equal(acc, np.fromfile(source/'reference_accum_int32.bin',dtype='<i4').reshape(128,150))
        golden_q1 = q40_quantize(acc, q40, int(yz))
        fp64_q1 = np.clip(np.rint(acc*multipliers[:,None])+int(yz),-128,127).astype(np.int8)
        oq1, oq2 = fused.run(None,{xd.input[0]:x[None]})
        np.testing.assert_array_equal(golden_q1,fp64_q1)
        np.testing.assert_array_equal(golden_q1,oq1[0])
        final = lut[golden_q1.astype(np.int16)+128]
        np.testing.assert_array_equal(final,oq2[0])
        dest = HERE/'deploy/cases'/item['directory']
        dest.mkdir(parents=True,exist_ok=True)
        arrays = {'input_int8.bin':x, 'weights_int8.bin':weights, 'bias_int32.bin':bias.astype('<i4'),
                  'requant_q40_uint32.bin':q40, 'post_lut_int8.bin':lut,
                  'reference_accum_int32.bin':acc.astype('<i4'),
                  'reference_conv_output_int8.bin':golden_q1, 'onnx_conv_output_int8.bin':oq1[0],
                  'reference_output_int8.bin':final, 'onnx_output_int8.bin':oq2[0]}
        for name,value in arrays.items():
            np.ascontiguousarray(value).tofile(dest/name)
        row = {**item,'model_sha256':model_hash,'input_source':'V1 verified internal INT8 input; no new audio preprocessing',
               'exact_int32_q40_fp64_onnx_match':True,'files':{name:sha256(dest/name) for name in arrays}}
        (dest/'metadata.json').write_text(json.dumps(row,indent=2,ensure_ascii=False),encoding='utf-8')
        rows.append(row)
        print('[PASS]',item['directory'],'INT32 / Q40 / FP64 / ONNX Q1 / ONNX Q2: zero mismatches',flush=True)
    # Default HLS vectors preserve V1's root test case (singing).
    default = HERE/'deploy/cases/case_004'
    for p in default.glob('*.bin'):
        shutil.copyfile(p,HERE/p.name)
    header = ['#ifndef CAMPLUS_CONV_RELU_PARAMS_H','#define CAMPLUS_CONV_RELU_PARAMS_H','#include <stdint.h>',
              '#define CONV_BATCH 1','#define CONV_CIN 128','#define CONV_COUT 128','#define CONV_T 150',
              f'#define CONV_INPUT_ZERO_POINT ({int(xz)})',f'#define CONV_OUTPUT_ZERO_POINT ({int(yz)})',
              f'#define POST_OUTPUT_ZERO_POINT ({rz})',f'static const double POST_INPUT_SCALE = {float(ys):.17g};',
              f'static const double POST_OUTPUT_SCALE = {rs:.17g};',
              'static const double CONV_REQUANT_MULTIPLIER[128] = {',
              ',\n'.join(format(float(x),'.17g') for x in multipliers),'};','#endif']
    (HERE/'layer_params.h').write_text('\n'.join(header)+'\n',encoding='utf-8')
    report = {'scope':'V2-A fixed Conv + original Q1/DQ1 + ReLU + Q2; not full CAM++',
              'model_sha256':model_hash,'conv_node':conv.name,'post_nodes':[n.name for n in chain[:4]],
              'input_tensor':xd.input[0],'output_tensor':q2.output[0],'output_scale':rs,'output_zero_point':rz,
              'lut_256_values_match':True,'conservative_int32_bound':int(bound.max()),
              'cases':rows,'v1_original_hashes':original_hashes,'onnxruntime':ort.__version__}
    (HERE/'reference_report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    (HERE/'deploy/cases/cases.json').write_text(json.dumps({'cases':rows},indent=2,ensure_ascii=False),encoding='utf-8')
    for path,digest in original_hashes.items():
        require(sha256(path)==digest,'V1 changed: '+path)
    print('[PASS] Full 256-entry LUT; five real inputs; original V1 files unchanged')


if __name__ == '__main__':
    main()
