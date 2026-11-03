"""Desktop only: audit the existing QDQ graph and build portable full-model plans.
All writes are confined to this new full_model_test directory. Old projects are read-only.
Run with the verified desktop Python, -B. No board connection is used.
"""
from pathlib import Path
import copy
import hashlib
import inspect
import json
import shutil
import sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
MODELS = HERE.parents[1]
OLD = MODELS / 'consistency-test/codex'
V3 = HERE.parent / 'pointwise_engine'
sys.path.insert(0, str(OLD))
from common import audio_features, import_runtime, sha256
import numpy as np
import onnx
from onnx import helper as h, numpy_helper as nh


def save(path, value):
    path = Path(path).resolve()
    if not path.is_relative_to(HERE):
        raise ValueError('Output outside new directory')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def model_for(nodes, outputs, model, types, label):
    """Backward prune within this chunk; external inputs become explicit graph inputs."""
    needed = set(outputs)
    kept = []
    for node in reversed(nodes):
        if needed.intersection(node.output):
            kept.append(node)
            needed.difference_update(node.output)
            needed.update(x for x in node.input if x)
    kept.reverse()
    initializers = [x for x in model.graph.initializer if x.name in needed]
    needed.difference_update(x.name for x in initializers)
    inputs = sorted(needed)
    require(all(x in types for x in inputs+list(outputs)), 'Missing inferred type '+label)
    graph = h.make_graph(kept, label, [copy.deepcopy(types[x]) for x in inputs],
                         [copy.deepcopy(types[x]) for x in outputs], initializers)
    result = h.make_model(graph, opset_imports=model.opset_import, ir_version=model.ir_version)
    onnx.checker.check_model(result)
    return result, inputs


def build_plan(model, types, layers, count):
    selected = layers[:count]
    conv_names = {x['name'] for x in selected}
    by_q = {x['q_name']:x for x in selected}
    groups, pending = [], []
    for node in model.graph.node:
        if node.name in conv_names:
            continue
        if node.name in by_q:
            if pending:
                groups.append({'kind':'cpu', 'nodes':pending})
                pending = []
            layer = by_q[node.name]
            groups.append({'kind':'pointwise', 'layer':layer['index'],
                           'inputs':[layer['input_tensor']], 'outputs':[layer['output_tensor']]})
        else:
            pending.append(node)
    if pending:
        groups.append({'kind':'cpu','nodes':pending})
    # Global backward liveness includes every residual/concat/attention/shape dependency.
    live = {'embedding'}
    for group in reversed(groups):
        if group['kind'] == 'pointwise':
            require(group['outputs'][0] in live, 'Disconnected replacement')
            live.difference_update(group['outputs'])
            live.update(group['inputs'])
            group['live_after'] = None
        else:
            produced = {x for n in group['nodes'] for x in n.output}
            outputs = sorted(live & produced)
            if not outputs:
                group['discard'] = True
                continue
            chunk, inputs = model_for(group['nodes'], outputs, model, types, 'cpu_chunk')
            group.update(model=chunk, inputs=inputs, outputs=outputs)
            live.difference_update(outputs)
            live.update(inputs)
    require(live == {'features'}, 'Unresolved full graph inputs: '+str(live))
    groups = [x for x in groups if not x.get('discard')]
    plan_dir = HERE/'bundle/plans'/('one' if count==1 else 'all55')
    plan_dir.mkdir(parents=True, exist_ok=True)
    ops = []
    for i, group in enumerate(groups):
        op = {k:v for k,v in group.items() if k not in ('nodes','model','live_after')}
        if group['kind'] == 'cpu':
            filename = 'cpu_{:03d}.onnx'.format(i)
            onnx.save(group['model'], plan_dir/filename)
            op['file'] = filename
            op['original_nodes'] = [n.name for n in group['model'].graph.node]
        ops.append(op)
    # Release tensor values only after their final consumer. Never discard a bypass prematurely.
    for i, op in enumerate(ops):
        op['keep_after'] = sorted({'embedding'} | {x for later in ops[i+1:] for x in later['inputs']})
    save(plan_dir/'plan.json', {'count':count, 'input':'features','output':'embedding','ops':ops,
        'boundary':'original input QuantizeLinear INT8 -> original Conv output QuantizeLinear INT8',
        'all_nonreplaced_dependencies_preserved':True})


def main():
    source = OLD/'artifacts/quantization/camplus_int8_qdq.onnx'
    metadata = json.loads(source.with_suffix('.export.json').read_text(encoding='utf-8'))
    require(sha256(source)==metadata['onnx_sha256'], 'QDQ model provenance')
    require(metadata['dynamic_frames'], 'Requires dynamic full-recording model')
    model = onnx.shape_inference.infer_shapes(onnx.load(source))
    onnx.checker.check_model(model)
    arrays = {t.name:nh.to_array(t) for t in model.graph.initializer}
    prod = {out:n for n in model.graph.node for out in n.output}
    consumers = {}
    for n in model.graph.node:
        for x in n.input:
            consumers.setdefault(x, []).append(n)
    types = {x.name:x for x in [*model.graph.input,*model.graph.output,*model.graph.value_info]}
    for name,a in arrays.items():
        types[name] = h.make_tensor_value_info(name, h.np_dtype_to_tensor_dtype(a.dtype), list(a.shape))
    targets = [n for n in model.graph.node if n.op_type=='Conv' and
        (('/block' in n.name and n.name.endswith('/linear1/Conv') and '/cam_layer/' not in n.name)
         or ('/transit' in n.name and n.name.endswith('/linear/Conv')))]
    require(len(targets)==55, 'Expected 55 V3 layers')
    layers=[]
    root=HERE/'bundle'
    (root/'params').mkdir(parents=True,exist_ok=True)
    (root/'islands').mkdir(exist_ok=True)
    for index,n in enumerate(targets,1):
        attrs={x.name:h.get_attribute_value(x) for x in n.attribute}
        require(attrs['kernel_shape']==[1] and attrs['strides']==[1] and attrs['pads']==[0,0]
                and attrs['group']==1 and attrs['dilations']==[1], 'Unsupported Conv')
        xd,wd=prod[n.input[0]],prod[n.input[1]]
        require(xd.op_type==wd.op_type=='DequantizeLinear', 'Missing QDQ')
        qnodes=consumers[n.output[0]]
        require(len(qnodes)==1 and qnodes[0].op_type=='QuantizeLinear', 'Additional FP32 Conv consumers')
        q=qnodes[0]
        w=arrays[wd.input[0]][:,:,0]
        cout,cin=w.shape
        xs,xz,ws,ys,yz=arrays[xd.input[1]],arrays[xd.input[2]],arrays[wd.input[1]],arrays[q.input[1]],arrays[q.input[2]]
        require(cin<=1024 and cout<=512 and w.dtype==np.int8 and np.all(arrays[wd.input[2]]==0), 'W shape/ZP')
        require(xs.size==ys.size==xz.size==yz.size==1 and xz.dtype==yz.dtype==np.int8, 'Activation scalar INT8')
        require({x.name:h.get_attribute_value(x) for x in wd.attribute}.get('axis',1)==0, 'Per-channel W axis')
        bias=np.zeros(cout,dtype=np.int32)
        island_nodes=[xd,wd]
        if len(n.input)==3:
            bd=prod[n.input[2]]
            require(bd.op_type=='DequantizeLinear', 'Bias DQ')
            bias=arrays[bd.input[0]]
            require(bias.dtype==np.int32 and np.all(arrays[bd.input[2]]==0), 'Bias INT32/ZP')
            require(np.array_equal(arrays[bd.input[1]],np.asarray(xs*ws,dtype=np.float32)), 'Bias scales')
            island_nodes.append(bd)
        multiplier=float(xs)*ws.astype(np.float64)/float(ys)
        shift=40
        while np.any(np.floor(multiplier*2**shift+.5)>0xffffffff):
            shift-=1
        require(shift>=8 and np.all(multiplier>0), 'Multiplier bounds')
        coeff=np.floor(multiplier*2**shift+.5).astype('<u4')
        require(np.all(coeff>0), 'Multiplier underflow')
        bound=np.abs(w.astype(np.int64)).sum(1)*max(abs(-128-int(xz)),abs(127-int(xz)))+np.abs(bias.astype(np.int64))
        require(bound.max()<=np.iinfo(np.int32).max, 'INT32 safety')
        layer={'index':index,'name':n.name,'cin':cin,'cout':cout,'input_zp':int(xz),
               'output_zp':int(yz),'requant_shift':shift,'flags':0,'input_tensor':xd.input[0],
               'output_tensor':q.output[0],'q_name':q.name,'input_scale':float(xs),
               'output_scale':float(ys),'weight_scales':ws.tolist(),'bound':int(bound.max()),
               'params':'params/layer{:02d}.npz'.format(index),'island':'islands/layer{:02d}.onnx'.format(index)}
        # Recheck generated parameters against the verified V3 files. Do NOT load case input tensors.
        cfg=json.loads((V3/'deploy/cases'/('audio01_layer{:02d}'.format(index))/'config.json').read_text())
        require(all(layer[k]==cfg[k] for k in ('name','cin','cout','input_zp','output_zp','requant_shift','input_tensor','output_tensor')), 'V3 config changed')
        for filename,array in [('weights_int8.bin',w),('bias_int32.bin',bias.astype('<i4')),
                                ('multiplier_uint32.bin',coeff)]:
            require(hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()==cfg['files_sha256'][filename], 'V3 params '+filename)
        np.savez(root/layer['params'],weights=w,bias=bias.astype('<i4'),multiplier=coeff,
                 post_lut=np.arange(-128,128,dtype=np.int16).astype(np.int8))
        island,inputs=model_for(island_nodes+[n,q], [q.output[0]], model, types, 'original_QDQ_island')
        require(inputs==[xd.input[0]], 'Island has additional dependencies')
        onnx.save(island,root/layer['island'])
        layers.append(layer)
    save(root/'layers.json',layers)
    diagnostic=copy.deepcopy(model)
    wanted=list(dict.fromkeys(['embedding']+[x[k] for x in layers for k in ('input_tensor','output_tensor')]))
    del diagnostic.graph.output[:]
    diagnostic.graph.output.extend(copy.deepcopy(types[x]) for x in wanted)
    onnx.checker.check_model(diagnostic)
    onnx.save(diagnostic,root/'diagnostic_boundaries.onnx')
    for count in (1,55):
        build_plan(model, types, layers, count)
    shutil.copy2(source,root/'camplus_int8_qdq.onnx')
    shutil.copy2(source.with_suffix('.export.json'),root/'model_provenance.json')
    support=root/'support'
    support.mkdir(exist_ok=True)
    for name in ('pointwise.bit','pointwise.hwh','pointwise_board.py'):
        shutil.copy2(V3/'deploy'/name,support/name)
    # Snapshot protocol function, untouched; no original extractor/cache-writing entry points used.
    shutil.copy2(MODELS.parent/'evaluate_cnceleb.py',root/'protocol_reference.py')
    import torch
    import torchaudio.compliance.kaldi as kaldi
    defaults={k:p.default for k,p in inspect.signature(kaldi.fbank).parameters.items()
              if p.default is not inspect.Parameter.empty}
    defaults.update(num_mel_bins=80,sample_frequency=16000,dither=0)
    save(root/'frontend_config.json', {'fbank_kwargs':defaults,'mono':'float32 channel mean',
        'normalization':'subtract time mean independently per mel bin', 'resample':'torchaudio.functional.resample defaults',
        'minimum_audio_seconds':0.45, 'embedding_dim':192, 'score':'L2 normalize then dot',
        'threshold':None, 'threshold_note':'No calibrated threshold provided; decisions pending',
        'canonical_source_sha256':sha256(OLD/'common.py'), 'kaldi_source_sha256':sha256(inspect.getfile(kaldi)),
        'torch_version':torch.__version__})
    # NumPy option uses exact desktop float32 filter/window constants, not guessed parameters.
    banks,_=kaldi.get_mel_banks(80,512,16000,20.,0.,100.,-500.,1.)
    window=kaldi._feature_window_function('povey',400,0.42,torch.device('cpu'),torch.float32)
    np.savez(root/'frontend_constants.npz',mel=np.pad(banks.numpy(),((0,0),(0,1))),window=window.numpy())
    audio=root/'audio'
    audio.mkdir(exist_ok=True)
    samples=[]
    for name in ('speaker1_a_cn_16k.wav','speaker1_b_cn_16k.wav','speaker2_a_cn_16k.wav'):
        source_audio=MODELS/'campplus_cn_common/examples'/name
        shutil.copy2(source_audio,audio/name)
        feat=audio_features(source_audio)
        np.save(audio/(name+'.fbank.npy'),feat)
        samples.append({'id':name,'path':'audio/'+name,'features':'audio/'+name+'.fbank.npy',
                        'sha256':sha256(source_audio),'frames':feat.shape[1]})
    save(root/'smoke_protocol.json', {'label_source':'campplus_cn_common/README.md ModelScope examples',
        'scope':'2 illustrative labeled trials; not accuracy or EER evidence', 'audio':samples,
        'enroll':{'speaker1':'speaker1_a_cn_16k.wav'},
        'trials':[{'speaker':'speaker1','audio':'speaker1_b_cn_16k.wav','label':1},
                  {'speaker':'speaker1','audio':'speaker2_a_cn_16k.wav','label':0}]})
    save(HERE/'source_audit.json', {'model_sha256':sha256(source),'layers':55,'case_inputs_read':False,
        'sources':{str(p.relative_to(MODELS.parent)):sha256(p) for p in
                   [OLD/'common.py',OLD/'export_camplus_onnx.py',OLD/'evaluate_camplus_onnx_cnceleb.py',
                    OLD/'quantize_camplus_int8.py',V3/'prepare_pointwise.py',V3/'deploy/pointwise_board.py',
                    V3/'analysis/run_db2b6b2792c9/RESULT_ANALYSIS.md',MODELS.parent/'evaluate_cnceleb.py']},
        'CPU_backend_board':'unconfirmed; manual probe required','hardware_regenerated':False})
    print('BUILT: full graph + one-layer and 55-layer plans; all V3 parameters rechecked',flush=True)


if __name__=='__main__':
    main()
