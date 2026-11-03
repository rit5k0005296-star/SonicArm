"""Portable full-model execution. No overlay or hardware action on import.
CPU chunks are original ONNX nodes; a callback replaces only Conv -> Q1.
"""
from pathlib import Path
import hashlib
import json
import platform
import sys
import time
HERE = Path(__file__).resolve().parent
if (HERE/'_board_deps').is_dir():
    sys.path.insert(0,str(HERE/'_board_deps'))
import numpy as np
sys.dont_write_bytecode = True
BUNDLE = HERE/'bundle'


def digest(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            value.update(block)
    return value.hexdigest()


def save(path,value):
    path=Path(path).resolve()
    if not path.is_relative_to(HERE):
        raise ValueError('Results must remain within full_model_test')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def ort_session(path,threads=1,optimize=False):
    # Native C API is an explicit ARM backend; it never impersonates the Python ORT package.
    native_manifest=HERE/'_native_ort/manifest.json'
    if native_manifest.is_file() and platform.system()=='Linux' and platform.machine().lower() in ('armv7l','armv8l'):
        from native_ort_bridge import Session
        return Session(path,threads,optimize)
    import onnxruntime as ort
    options=ort.SessionOptions()
    options.intra_op_num_threads=threads
    options.inter_op_num_threads=1
    options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
    options.graph_optimization_level=ort.GraphOptimizationLevel.ORT_ENABLE_ALL if optimize else ort.GraphOptimizationLevel.ORT_DISABLE_ALL
    # Multiple graph sessions must not reserve independent large CPU arenas on 512 MiB boards.
    options.enable_cpu_mem_arena=False
    options.enable_mem_pattern=False
    options.log_severity_level=3
    result=ort.InferenceSession(str(path),sess_options=options,providers=['CPUExecutionProvider'])
    if result.get_providers()!=['CPUExecutionProvider']:
        raise RuntimeError('Unexpected execution provider')
    return result


def stats(values):
    a=np.asarray(values,dtype=np.float64)
    if not a.size:
        return None
    return {'n':a.size,'median_ms':float(np.median(a)),'p95_ms':float(np.percentile(a,95)),
            'min_ms':float(a.min()),'max_ms':float(a.max())}


def compare(a,b):
    a=np.asarray(a,dtype=np.float64);b=np.asarray(b,dtype=np.float64)
    if a.shape!=b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError('Invalid comparison arrays')
    d=np.abs(a-b);den=np.maximum(np.abs(a),1e-12)
    na=np.linalg.norm(a);nb=np.linalg.norm(b)
    if min(na,nb)<1e-12:
        raise ValueError('Zero comparison vector')
    return {'max_abs':float(d.max()),'mean_abs':float(d.mean()),
            'max_relative_element':float((d/den).max()),'relative_l2':float(np.linalg.norm(a-b)/na),
            'cosine':float(np.sum(a*b)/(na*nb))}


def normalize(embedding):
    a=np.asarray(embedding,dtype=np.float32).reshape(-1)
    if a.shape!=(192,) or not np.isfinite(a).all():
        raise ValueError('Embedding must be finite float32[192]')
    norm=np.linalg.norm(a)
    if norm<1e-12:
        raise ValueError('Zero embedding')
    return a/norm


def frontend(path,kind='canonical'):
    """File read, channel mean, original Fbank, temporal mean. No cropping/VAD."""
    import soundfile as sf
    started=time.perf_counter()
    pcm,rate=sf.read(str(path),dtype='float32',always_2d=True)
    if not pcm.size or not np.isfinite(pcm).all() or len(pcm)/rate<0.45:
        raise ValueError('Invalid/short audio; full protocol forbids silent removal')
    waveform=pcm.mean(axis=1).copy()
    read_ms=(time.perf_counter()-started)*1000
    t=time.perf_counter()
    if kind=='canonical':
        import torch
        import torchaudio.functional as af
        import torchaudio.compliance.kaldi as kaldi
        w=torch.from_numpy(waveform).unsqueeze(0)
        if rate!=16000:
            w=af.resample(w,rate,16000)
        cfg=json.loads((BUNDLE/'frontend_config.json').read_text())['fbank_kwargs']
        features=kaldi.fbank(w,**cfg)
        features-=features.mean(0,keepdim=True)
        f=features.unsqueeze(0).contiguous().numpy()
    elif kind=='numpy16k':
        if rate!=16000:
            raise ValueError('numpy16k supports only original 16 kHz audio; use canonical for resampling')
        with np.load(BUNDLE/'frontend_constants.npz',allow_pickle=False) as constants:
            mel=constants['mel'];window=constants['window']
        count=1+(len(waveform)-400)//160
        frames=np.lib.stride_tricks.as_strided(waveform,shape=(count,400),
            strides=(160*waveform.strides[0],waveform.strides[0])).copy()
        frames-=frames.mean(axis=1,keepdims=True)
        previous=np.concatenate((frames[:,:1],frames[:,:-1]),axis=1)
        frames=(frames-np.float32(0.97)*previous)*window
        spectrum=np.abs(np.fft.rfft(frames,n=512,axis=1).astype(np.complex64)).astype(np.float32)**2
        f=np.log(np.maximum(spectrum@mel.T,np.finfo(np.float32).eps)).astype(np.float32)
        f-=f.mean(axis=0,keepdims=True)
        f=f[None]
    else:
        raise ValueError('Unknown frontend')
    return np.ascontiguousarray(f,dtype=np.float32), {'audio_read_decode_mono_ms':read_ms,
        'fbank_resample_normalize_ms':(time.perf_counter()-t)*1000,'audio_seconds':len(pcm)/rate,
        'original_sample_rate':rate,'frontend':kind}


def integer_pointwise(layer,params,x,debug=False):
    if x.dtype!=np.int8 or x.ndim!=3 or x.shape[:2]!=(1,layer['cin']):
        raise ValueError('Boundary must be original INT8 [1,C,T]')
    # Bounds were proved during extraction. INT64 here is a numerical oracle, not a CPU speed baseline.
    acc=params['weights'].astype(np.int64)@(x[0].astype(np.int64)-layer['input_zp'])+params['bias'].astype(np.int64)[:,None]
    if np.any(acc>2147483647) or np.any(acc<-2147483648):
        raise OverflowError('INT32 accumulator')
    product=acc*params['multiplier'].astype(np.int64)[:,None]
    mag=np.abs(product);shift=layer['requant_shift'];whole=mag>>shift
    fraction=mag&((1<<shift)-1);half=1<<(shift-1)
    whole+=(fraction>half)|((fraction==half)&((whole&1)!=0))
    q=np.clip(np.where(product<0,-whole,whole)+layer['output_zp'],-128,127).astype(np.int8)[None]
    return q,acc.astype(np.int32)[None] if debug else None


class FullCPU:
    def __init__(self,threads=1,optimize=False):
        self.optimize=optimize
        self.session=ort_session(BUNDLE/'camplus_int8_qdq.onnx',threads,optimize)
    def run(self,features,audit=False):
        start=time.perf_counter()
        value=self.session.run(['embedding'],{'features':features})[0]
        return value,{'cpu_remaining_ms':(time.perf_counter()-start)*1000,'layers':[],
                     'ort_optimization':'ORT_ENABLE_ALL' if self.optimize else 'ORT_DISABLE_ALL',
                     'runtime_backend':'native C API '+self.session.api.version if hasattr(self.session,'api') else 'Python ONNX Runtime'}
    def close(self):
        if hasattr(self.session,'close'):
            self.session.close()
        self.session=None


class Hybrid:
    def __init__(self,plan='one',mode='integer',threads=1,debug=False):
        if mode not in ('bypass','integer','fpga') or plan not in ('one','all55'):
            raise ValueError('Invalid hybrid mode/plan')
        self.mode=mode;self.debug=debug;self.plan_name=plan;self.threads=threads;self.trace_sink=None;self.audit_sink=None
        self.directory=BUNDLE/'plans'/plan
        self.plan=json.loads((self.directory/'plan.json').read_text())
        self.layers={x['index']:x for x in json.loads((BUNDLE/'layers.json').read_text())}
        self.params={};self.sessions={};self.islands={};self.fpga=None
        for i,op in enumerate(self.plan['ops']):
            if op['kind']=='cpu':
                self.sessions[i]=ort_session(self.directory/op['file'],threads)
            else:
                layer=self.layers[op['layer']]
                with np.load(BUNDLE/layer['params'],allow_pickle=False) as p:
                    self.params[op['layer']]={k:p[k].copy() for k in p.files}
                if mode=='bypass':
                    self.islands[op['layer']]=ort_session(BUNDLE/layer['island'],threads)
        if mode=='fpga':
            from fpga_context import FPGAContext
            self.fpga=FPGAContext([self.layers[k] for k in self.params],self.params,debug=debug)

    def run(self,features,audit=False):
        if features.dtype!=np.float32 or features.ndim!=3 or features.shape[0]!=1 or features.shape[2]!=80:
            raise ValueError('Expected Fbank float32 [1,T,80]')
        values={'features':features};report={'cpu_remaining_ms':0.,'layer_callback_ms':0.,'layers':[]}
        if self.fpga:
            self.fpga.audit=audit
        for i,op in enumerate(self.plan['ops']):
            start=time.perf_counter()
            if op['kind']=='cpu':
                feed={n:values[n] for n in op['inputs']}
                out=self.sessions[i].run(op['outputs'],feed)
                values.update(zip(op['outputs'],out))
                report['cpu_remaining_ms']+=(time.perf_counter()-start)*1000
            else:
                layer=self.layers[op['layer']];x=values[layer['input_tensor']]
                convert=time.perf_counter();x=np.ascontiguousarray(x)
                layout_ms=(time.perf_counter()-convert)*1000
                if self.mode=='bypass':
                    q=self.islands[layer['index']].run([layer['output_tensor']],{layer['input_tensor']:x})[0]
                    acc=None;details={}
                elif self.mode=='integer':
                    q,acc=integer_pointwise(layer,self.params[layer['index']],x,self.debug)
                    details={'scope':'software integer simulation'}
                else:
                    q,acc,details=self.fpga.call(layer,x)
                elapsed=(time.perf_counter()-start)*1000
                values[layer['output_tensor']]=q
                row={'index':layer['index'],'name':layer['name'],'frames':x.shape[2],
                     'input_tensor':layer['input_tensor'],'output_tensor':layer['output_tensor'],
                     'input_dtype':str(x.dtype),'output_dtype':str(q.dtype),
                     'callback_ms':elapsed,'layout_ms':layout_ms,**details}
                report['layer_callback_ms']+=elapsed
                if audit:
                    # Recompute on CURRENT intermediate tensors; never case inputs or stale output.
                    gold,gold_acc=integer_pointwise(layer,self.params[layer['index']],x,True)
                    if self.mode!='bypass' and not np.array_equal(q,gold):
                        raise AssertionError('Current integer boundary mismatch '+layer['name'])
                    if acc is not None and not np.array_equal(acc,gold_acc):
                        raise AssertionError('Current accumulator mismatch '+layer['name'])
                    island=ort_session(BUNDLE/layer['island'],self.threads)
                    original=island.run([layer['output_tensor']],{layer['input_tensor']:x})[0]
                    diff=np.abs(gold.astype(np.int16)-original.astype(np.int16))
                    row.update(integer_exact=self.mode!='bypass',onnx_changed_elements=int(np.count_nonzero(diff)),
                               onnx_max_lsb=int(diff.max()),input_sha256=hashlib.sha256(x.tobytes()).hexdigest(),
                               output_sha256=hashlib.sha256(q.tobytes()).hexdigest())
                    if int(diff.max())>1:
                        raise AssertionError('Original QDQ island >1 LSB: '+layer['name'])
                    if self.trace_sink is not None:
                        self.trace_sink(layer,x,q,gold,original)
                    del island
                report['layers'].append(row)
                if audit and self.audit_sink is not None:
                    self.audit_sink(row)
            keep=set(op['keep_after'])
            values={k:v for k,v in values.items() if k in keep}
        return values['embedding'],report

    def close(self):
        if self.fpga:
            self.fpga.close()
        for session in [*self.sessions.values(),*self.islands.values()]:
            if hasattr(session,'close'):
                session.close()
        self.sessions.clear();self.islands.clear();self.params.clear()


def notebook_source_digest(path):
    document=json.loads(Path(path).read_text(encoding='utf-8'))
    sources=[''.join(cell.get('source',[])) for cell in document['cells'] if cell['cell_type']=='code']
    return hashlib.sha256(json.dumps(sources,ensure_ascii=False).encode('utf-8')).hexdigest()


def notebook_sources(path):
    document=json.loads(Path(path).read_text(encoding='utf-8'))
    return [''.join(cell.get('source',[])) for cell in document['cells'] if cell['cell_type']=='code']


def verify_manifest():
    manifest=json.loads((HERE/'upload_manifest.json').read_text(encoding='utf-8'))
    for name,sha in manifest['files'].items():
        path=(HERE/name).resolve()
        if not path.is_relative_to(HERE):
            raise ValueError('Upload path escapes package: '+name)
        if digest(path)!=sha:
            expected=manifest.get('notebook_sources',{}).get(name)
            if path.suffix=='.ipynb' and expected and notebook_source_digest(path)==expected:
                continue
            original_cells=manifest.get('notebook_cells',{}).get(name)
            if path.suffix=='.ipynb' and original_cells:
                observed=notebook_sources(path)
                # The user was instructed to append an extraction cell to 00. Preserve that
                # valid operation history while still requiring original cells unmodified.
                if observed[:len(original_cells)]==original_cells:
                    continue
            raise ValueError('Upload hash mismatch: '+name)
    return manifest['version_id']
