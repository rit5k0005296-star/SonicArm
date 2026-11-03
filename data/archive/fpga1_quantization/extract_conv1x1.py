"""Extract a real CAM++ QDQ pointwise layer and verified binary HLS test vectors.

Run with the existing Python3.11. Default model: the fully evaluated INT8 model.
Output: header + raw C-order little-endian binaries, no intermediate ONNX files.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import sys
sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
PYNQ = HERE.parents[2]
sys.path.insert(0,str(PYNQ/'CAM-pretrained_models/consistency-test/codex'))
from common import audio_features, import_runtime, sha256
import numpy as np
import onnx
from onnx import helper, numpy_helper

DEFAULT_MODEL=PYNQ/'CAM-pretrained_models/consistency-test/codex/artifacts/quantization/camplus_int8_qdq.onnx'
DEFAULT_NODE='/xvector/block1/tdnnd1/linear1/Conv'


def initial_value(initializers,name):
    if name not in initializers: raise ValueError('Expected initializer: '+name)
    return initializers[name]


def read_qparams(node,initializers):
    if node.op_type not in {'QuantizeLinear','DequantizeLinear'} or len(node.input)!=3:
        raise ValueError('Explicit Q/DQ scales and zero points required')
    return initial_value(initializers,node.input[1]), initial_value(initializers,node.input[2])


def prefix_model(model,names,types,shapes):
    producers={o:n for n in model.graph.node for o in n.output}
    initializer_names={i.name for i in model.graph.initializer}
    needed_nodes=set(); needed_init=set(); pending=list(names)
    inputs={i.name for i in model.graph.input}
    visited=set()
    while pending:
        name=pending.pop()
        if not name or name in visited: continue
        visited.add(name)
        if name in initializer_names: needed_init.add(name); continue
        if name in inputs: continue
        if name not in producers: raise ValueError('No producer: '+name)
        node=producers[name]
        needed_nodes.add(node.name)
        pending.extend(node.input)
    result=copy.deepcopy(model)
    result.graph.ClearField('node'); result.graph.ClearField('initializer')
    result.graph.ClearField('output'); result.graph.ClearField('value_info')
    result.graph.node.extend(copy.deepcopy(n) for n in model.graph.node if n.name in needed_nodes)
    result.graph.initializer.extend(copy.deepcopy(i) for i in model.graph.initializer if i.name in needed_init)
    result.graph.output.extend(helper.make_tensor_value_info(n,t,s) for n,t,s in zip(names,types,shapes))
    onnx.checker.check_model(result)
    return result


def append_array(lines,ctype,name,array):
    flat=np.asarray(array).reshape(-1)
    def literal(v):
        if np.issubdtype(flat.dtype,np.floating):
            s=format(float(v),'.17g')
            return s if '.' in s or 'e' in s else s+'.0'
        return str(int(v))
    lines.append(f'static const {ctype} {name}[{len(flat)}] = {{')
    for i in range(0,len(flat),8): lines.append('    '+', '.join(literal(v) for v in flat[i:i+8])+',')
    lines.append('};')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',type=Path,default=DEFAULT_MODEL)
    parser.add_argument('--node',default=DEFAULT_NODE)
    parser.add_argument('--audio',type=Path)
    parser.add_argument('--frames',type=int,default=300,help='Use first N normalized feature frames; 0 means complete recording')
    parser.add_argument('--pad-frames',action='store_true',help='Zero-pad normalized features to --frames for fixed-size hardware tests')
    parser.add_argument('--output',type=Path,default=HERE)
    args=parser.parse_args()
    if args.frames<0: parser.error('frames must be nonnegative')
    output=args.output.resolve()
    if not output.is_relative_to(PYNQ.parent.resolve()): parser.error('Output must remain inside SonicArm')
    metadata=json.loads(args.model.with_suffix('.export.json').read_text(encoding='utf-8'))
    if metadata['onnx_sha256']!=sha256(args.model) or not metadata.get('quantization'):
        raise ValueError('Quantized model provenance invalid')
    model=onnx.load(str(args.model)); onnx.checker.check_model(model)
    producers={o:n for n in model.graph.node for o in n.output}
    initializers={i.name:numpy_helper.to_array(i) for i in model.graph.initializer}
    conv=next((n for n in model.graph.node if n.name==args.node),None)
    if conv is None or conv.op_type!='Conv': raise ValueError('Conv node not found')
    attrs={a.name:helper.get_attribute_value(a) for a in conv.attribute}
    if attrs.get('kernel_shape')!=[1] or attrs.get('strides',[1])!=[1] or attrs.get('pads',[0,0])!=[0,0] or attrs.get('dilations',[1])!=[1] or attrs.get('group',1)!=1:
        raise ValueError('This extractor supports pointwise Conv1D stride1/dilation1/group1 only')
    xdq=producers[conv.input[0]]; wdq=producers[conv.input[1]]
    if xdq.op_type!='DequantizeLinear' or wdq.op_type!='DequantizeLinear': raise ValueError('QDQ Conv required')
    ws,wz=read_qparams(wdq,initializers); xs,xz=read_qparams(xdq,initializers)
    w=initial_value(initializers,wdq.input[0])
    if w.dtype!=np.int8 or w.ndim!=3 or w.shape[2]!=1: raise ValueError('INT8 [Cout,Cin,1] weights required')
    cout,cin,_=w.shape
    if ws.shape!=(cout,) or wz.shape!=(cout,) or xs.size!=1 or xz.size!=1 or xz.dtype!=np.int8:
        raise ValueError('Expected per-output-channel weights and scalar signed INT8 activations')
    if dict((a.name,helper.get_attribute_value(a)) for a in wdq.attribute).get('axis',1)!=0:
        raise ValueError('Weight quantization axis must be output-channel axis0')
    yqs=[n for n in model.graph.node if n.op_type=='QuantizeLinear' and n.input[0]==conv.output[0]]
    if len(yqs)!=1: raise ValueError('Expected one output quantization boundary')
    yq=yqs[0]; ys,yz=read_qparams(yq,initializers)
    if ys.size!=1 or yz.size!=1 or yz.dtype!=np.int8: raise ValueError('Scalar signed INT8 output required')
    bias=np.zeros(cout,dtype=np.int32)
    if len(conv.input)>2:
        bdq=producers.get(conv.input[2])
        if bdq is None or bdq.op_type!='DequantizeLinear': raise ValueError('INT32 QDQ bias required')
        bs,bz=read_qparams(bdq,initializers)
        bias=initial_value(initializers,bdq.input[0])
        if bias.dtype!=np.int32 or bias.shape!=(cout,) or np.any(bz!=0): raise ValueError('INT32 per-channel zero-point0 bias required')
        if not np.array_equal(bs, np.asarray(xs*ws,dtype=np.float32)):
            raise ValueError('Bias scale must equal float32 input_scale * weight_scale')
    if np.any(ws<=0) or float(xs)<=0 or float(ys)<=0: raise ValueError('Invalid scales')
    audio=args.audio
    if audio is None:
        directory=PYNQ/'data/cn-celeb_v2/CN-Celeb_flac/data/id00000'
        paths=sorted([*directory.glob('*.flac'),*directory.glob('*.wav')])
        if not paths: raise FileNotFoundError('No default development audio; pass --audio')
        audio=paths[0]
    features=audio_features(audio)
    if features.shape[1]<20: raise ValueError('Audio too short')
    original_frames=features.shape[1]
    if args.frames: features=features[:,:args.frames,:].copy()
    if args.pad_frames and args.frames and features.shape[1]<args.frames:
        features=np.pad(features,((0,0),(0,args.frames-features.shape[1]),(0,0)),mode='constant')
    print(f'Feature frames: original={original_frames}, used={features.shape[1]}, padded={max(0,features.shape[1]-original_frames)}')
    # Expose real internal quantized input/output, stopping immediately after the chosen layer.
    # Disable graph optimization so references follow explicit DQ -> float Conv -> Q semantics.
    prefix=prefix_model(model,[xdq.input[0],yq.output[0],conv.output[0]],
                        [onnx.TensorProto.INT8,onnx.TensorProto.INT8,onnx.TensorProto.FLOAT],
                        [[1,cin,'T'],[1,cout,'T'],[1,cout,'T']])
    ort=import_runtime('cpu'); options=ort.SessionOptions()
    options.intra_op_num_threads=4; options.inter_op_num_threads=1
    options.graph_optimization_level=ort.GraphOptimizationLevel.ORT_DISABLE_ALL
    runtime=ort.InferenceSession(prefix.SerializeToString(),sess_options=options,providers=['CPUExecutionProvider'])
    x,onnx_q,onnx_float=runtime.run(None,{'features':features})
    if x.dtype!=np.int8 or x.shape[:2]!=(1,cin): raise ValueError('Unexpected internal activation layout')
    centered_x=x.astype(np.int64)-int(xz)
    centered_w=w[:,:,0].astype(np.int64)-wz.astype(np.int64)[:,None]
    accumulator64=np.matmul(centered_w,centered_x[0])+bias.astype(np.int64)[:,None]
    if accumulator64.min()<np.iinfo(np.int32).min or accumulator64.max()>np.iinfo(np.int32).max:
        raise OverflowError('INT32 accumulator overflow')
    accumulator=accumulator64.astype(np.int32)[None,:,:]
    # Hardware golden rule: exact integer accumulation including bias; FP64 per-channel
    # scaling; ties-to-even round BEFORE adding the integer output zero point; saturate.
    multipliers=np.float64(xs)*ws.astype(np.float64)/np.float64(ys)
    reference=np.clip(np.rint(accumulator.astype(np.float64)*multipliers[None,:,None])+int(yz),-128,127).astype(np.int8)
    expected_float=accumulator.astype(np.float64)*(np.float64(xs)*ws.astype(np.float64))[None,:,None]
    float_error=float(np.max(np.abs(expected_float-onnx_float.astype(np.float64))))
    lsb=np.abs(reference.astype(np.int16)-onnx_q.astype(np.int16))
    if not np.isfinite(onnx_float).all() or int(lsb.max())>1:
        raise ValueError(f'Integer reference differs from ONNX by >1 LSB: {lsb.max()}')
    output.mkdir(parents=True,exist_ok=True)
    # Binary layout is channel-major C contiguous: X[n,c,t], W[o,c,k], Y[n,o,t].
    arrays={'weights_int8.bin':w.astype('i1'),'bias_int32.bin':bias.astype('<i4'),
            'input_int8.bin':x.astype('i1'),'reference_accum_int32.bin':accumulator.astype('<i4'),
            'reference_output_int8.bin':reference,'onnx_output_int8.bin':onnx_q.astype('i1')}
    for name,array in arrays.items(): np.ascontiguousarray(array).tofile(output/name)
    lines=['#ifndef CAMPLUS_CONV1X1_PARAMS_H','#define CAMPLUS_CONV1X1_PARAMS_H','#include <stdint.h>',
           '// Binary tensors use C-order little-endian; X/Y=[N,C,T], W=[Cout,Cin,1].',
           '// Acc = bias[o] + sum_c ((X[n,c,t]-X_ZP)*(W[o,c,0]-W_ZP[o])).',
           '// Y = sat_int8(round_ties_even(Acc * REQUANT_MULTIPLIER[o]) + Y_ZP).',
           '// REF output uses exact INT32 Acc and FP64 scaling. ONNX output is separate.',
           '// This layer includes no separate ReLU, residual Add, or following BatchNorm.',
           f'#define CONV_BATCH 1',f'#define CONV_CIN {cin}',f'#define CONV_COUT {cout}',
           f'#define CONV_T {x.shape[2]}','#define CONV_KERNEL 1','#define CONV_STRIDE 1',
           '#define CONV_PADDING 0','#define CONV_DILATION 1','#define CONV_GROUPS 1',
           f'#define CONV_INPUT_ZERO_POINT ({int(xz)})',f'#define CONV_OUTPUT_ZERO_POINT ({int(yz)})',
           f'#define CONV_REFERENCE_ONNX_MAX_LSB {int(lsb.max())}',
           f'#define CONV_REFERENCE_ONNX_MISMATCHES {int(np.count_nonzero(lsb))}',
           f'static const char CONV_NODE[] = {json.dumps(conv.name)};',
           f'static const char CONV_MODEL_SHA256[] = "{sha256(args.model)}";',
           f'static const char CONV_AUDIO_SHA256[] = "{sha256(audio)}";',
           f'#define CONV_INPUT_FEATURE_FRAMES {features.shape[1]}',
           f'static const double CONV_INPUT_SCALE = {float(xs):.17g};',
           f'static const double CONV_OUTPUT_SCALE = {float(ys):.17g};']
    append_array(lines,'double','CONV_WEIGHT_SCALE',ws)
    append_array(lines,'int32_t','CONV_WEIGHT_ZERO_POINT',wz)
    append_array(lines,'double','CONV_REQUANT_MULTIPLIER',multipliers)
    lines.append('#endif')
    (output/'layer_params.h').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(f'Layer: {conv.name}\nX={x.shape}, W={w.shape}, Y={reference.shape}')
    print(f'Input scale/ZP: {float(xs):.9g}/{int(xz)}; output scale/ZP: {float(ys):.9g}/{int(yz)}')
    print(f'INT32 range: [{accumulator.min()}, {accumulator.max()}]; reference/ONNX max LSB={lsb.max()}, mismatches={np.count_nonzero(lsb)}')
    print(f'Float Conv max abs difference={float_error:.6g}; output={output}')


if __name__=='__main__': main()
