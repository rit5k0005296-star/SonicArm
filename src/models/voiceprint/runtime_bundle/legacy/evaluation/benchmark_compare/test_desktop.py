"""Actual Windows ORT1.17.1 + native C++ kernel checks. Never board proof."""
from pathlib import Path
import ast
import ctypes as ct
import json
import sys
import time
sys.dont_write_bytecode=True
WORK=Path(__file__).resolve().parent;ROOT=WORK.parents[1];MODELS=ROOT.parents[1]
sys.path.insert(0,str(MODELS/'consistency-test/codex'))
from common import import_runtime
import_runtime('cpu')
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(WORK))
import numpy as np
import compare_runtime as runtimes
import compare_benchmark as bench
import runtime_core as core
from native_ort_bridge import API,Session


def main():
    d=WORK/'diagnostics';d.mkdir(exist_ok=True)
    bench.validate_files()
    lib=ROOT/'desktop_validation/ort_audit/windows1171/onnxruntime-win-x64-1.17.1/lib/onnxruntime.dll'
    api=API(lib,verify=False)
    if api.version!='1.17.1':raise AssertionError('Wrong native runtime')
    factory=lambda path,threads=1,optimize=False:Session(path,threads,optimize,api=api)
    protocol,items,features=bench.data();names=list(features)
    captured={};reports={};start=time.perf_counter()
    with bench.execution(factory):
        for mode in ('cpu_int8_reference','cpu_int8','cpu_fp32','v4_rebuild','v3_software','v4_software'):
            print('[DESKTOP ACTUAL ORT]',mode,'INITIALIZE',flush=True)
            model=bench.make_runtime(mode,max(x.shape[1] for x in features.values()),False)
            try:
                captured[mode]={}
                for name,x in features.items():
                    raw,detail=model.run(x,audit=False)
                    if raw.shape!=(1,192) or raw.dtype!=np.float32 or not np.isfinite(raw).all():raise AssertionError('Bad embedding')
                    captured[mode][name]=raw.copy()
                    print('[DESKTOP VECTOR]',mode,name,'norm',float(np.linalg.norm(raw)),flush=True)
                reports[mode]={n:core.compare(captured['cpu_int8_reference'][n],r) for n,r in captured[mode].items()}
            finally:bench.close(model)
        for n in names:
            if not np.array_equal(captured['cpu_int8_reference'][n],captured['v4_rebuild'][n]):
                raise AssertionError('Full original FCM boundary cut/reconstruction not exact')
        # Complete V4 with REAL compiled C++ FCM callback on live tensors; PW remains
        # independently checked exact blocked integer reference. No MMIO here.
        cpp=MODELS/'FPGA-4/fcm_engine/diagnostics/fcm_native.dll'
        native=ct.CDLL(str(cpp)).fcm
        p8=ct.POINTER(ct.c_int8);pi=ct.POINTER(ct.c_int32);pu=ct.POINTER(ct.c_uint32)
        native.argtypes=[p8,p8,pi,pu,p8,p8,p8,pi]+[ct.c_int]*10;native.restype=ct.c_int
        class NativeFCM:
            def __init__(self,params):self.params=params;self.audit=False;self.safe=True
            def call(self,row,x,skip):
                p=self.params[row['index']];of=(x.shape[1]+row['stride_f']-1)//row['stride_f'];t=x.shape[2]
                q=np.empty((row['cout'],of,t),np.int8);a=np.empty(q.shape,np.int32)
                values=[np.ascontiguousarray(x),p['weights'],p['bias'],p['multiplier'],p['post_lut'],np.ascontiguousarray(skip),q,a]
                pointers=[v.ctypes.data_as(ty) for v,ty in zip(values,native.argtypes[:8])]
                scalar=[row['cin'],row['cout'],row['freq'],t,row['kernel'],row['stride_f'],row['input_zp'],row['output_zp'],row['requant_shift'],row['flags']]
                if native(*pointers,*scalar)!=0:raise AssertionError('Native FCM status')
                return q,a,dict(chunks=1,pointer_rebinds=0)
        model=runtimes.V4Runtime('integer',False,max(x.shape[1] for x in features.values()))
        model.runner.context=NativeFCM(model.runner.params)
        try:
            for name,x in features.items():
                raw,_=model.run(x,audit=False)
                if not np.array_equal(raw,captured['v4_software'][name]):raise AssertionError('Full-model native FCM differs from independent INT64 model')
                print('[NATIVE FCM FULL MODEL EXACT]',name,flush=True)
        finally:bench.close(model)
    # Window seam mechanics are tested separately in the V4 native driver tests.
    for n in ('compare_runtime.py','compare_benchmark.py','prepare_compare.py'):
        ast.parse((WORK/n).read_text(encoding='utf8'))
    bench.validate_files()
    import zipfile
    archive=ROOT/'updates/cpu_v3_v4_compare.zip'
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:raise AssertionError('Archive corruption')
        if any(not n.startswith('benchmark_compare/') or '..' in Path(n).parts for n in z.namelist()):raise AssertionError('Archive path')
    report=dict(pass_=True,actual_hardware=False,native_runtime='Windows ORT CAPI '+api.version,
        scope='Three full canonical recordings; original CPU vs cut/rebuilt model exact; compiled C++ FCM vs independent INT64 full integer model exact. Not ARM, PL or throughput proof.',
        reconstruction_exact_recordings=3,native_fcm_integer_exact_recordings=3,quality=reports,
        original_v3_manifest=core.verify_manifest(),elapsed_seconds=time.perf_counter()-start,
        package_sha256=core.digest(archive))
    bench.save(d/'desktop_validation.json',report)
    print('DESKTOP_COMPARE_VALIDATION_PASS:',d/'desktop_validation.json',flush=True)


if __name__=='__main__':main()
