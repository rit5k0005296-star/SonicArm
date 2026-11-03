"""Desktop only: compiled REAL C++ kernels behind simulated resident MMIO/DDR.
No board receipts are created. Original hardware guards are not monkeypatched on board.
"""
from pathlib import Path
from types import SimpleNamespace
import ctypes as ct
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
sys.dont_write_bytecode=True
WORK=Path(__file__).resolve().parents[1];ROOT=WORK.parents[1];MODELS=ROOT.parents[1]
sys.path.insert(0,str(MODELS/'consistency-test/codex'))
from common import import_runtime
import_runtime('cpu')
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(WORK))
import numpy as np
import compare_runtime as rt
import compare_benchmark as bench
import fpga_context as pc
from native_ort_bridge import API,Session


def main():
    output=WORK/'diagnostics';output.mkdir(exist_ok=True)
    pw=output/'pointwise_native.dll'
    subprocess.run(['D:/msys64/ucrt64/bin/g++.exe','-shared','-O2','-Wno-unknown-pragmas','-static-libgcc','-static-libstdc++',
                    str(MODELS/'FPGA-3/pointwise_engine/pointwise.cpp'),'-o',str(pw)],check=True)
    p8,pi,pu=ct.POINTER(ct.c_int8),ct.POINTER(ct.c_int32),ct.POINTER(ct.c_uint32)
    cnn=ct.CDLL(str(MODELS/'FPGA-4/fcm_engine/diagnostics/fcm_native.dll')).fcm
    cnn.argtypes=[p8,p8,pi,pu,p8,p8,p8,pi]+[ct.c_int]*10;cnn.restype=ct.c_int
    pointwise=ct.CDLL(str(pw)).pointwise
    pointwise.argtypes=[p8,p8,pi,pu,p8,p8,pi]+[ct.c_int]*7;pointwise.restype=ct.c_int
    tree=ET.parse(rt.HW/'fcm_v4.hwh').getroot()
    def offsets(instance):
        module=next(m for m in tree.iter('MODULE') if m.get('INSTANCE')==instance)
        result={}
        for r in module.findall('.//REGISTERS/REGISTER'):
            p=r.find("./PROPERTY[@NAME='ADDRESS_OFFSET']")
            if p is not None:result[r.get('NAME')]=int(p.get('VALUE'),0)
        return result
    allocated={};next_address=[0x10000000];total_calls={'fcm':0,'pointwise':0}
    class Buffer(np.ndarray):
        def __new__(cls,shape,dtype):
            v=np.zeros(shape,dtype).view(cls);v.physical_address=next_address[0]
            next_address[0]+=((v.nbytes+4095)//4096+1)*4096
            if next_address[0]>0x20000000:raise AssertionError('Simulated DDR exceeded')
            allocated[v.physical_address]=v;return v
        def __array_finalize__(self,o):self.physical_address=getattr(o,'physical_address',None)
        def flush(self):pass
        def invalidate(self):pass
        def freebuffer(self):allocated.pop(self.physical_address,None)
    class MMIO:
        def __init__(self,name,fn,pointers,scalars,off):
            self.name,self.fn,self.pointers,self.scalars,self.off=name,fn,pointers,scalars,off
            self.reg={};self.done=False
        def read(self,offset):
            if offset==self.off['CTRL']:return 6 if self.done else 4
            return self.reg.get(offset,0)
        def write(self,offset,value):
            self.reg[offset]=value
            if offset!=self.off['CTRL'] or value!=1:return
            arrays=[]
            for name in self.pointers:
                address=self.reg[self.off[name+'_1']]|(self.reg[self.off[name+'_2']]<<32)
                arrays.append(allocated[address])
            ptrs=[v.ctypes.data_as(ty) for v,ty in zip(arrays,self.fn.argtypes[:len(arrays)])]
            scalars=[self.reg[self.off[n]]-(1<<32) if self.reg[self.off[n]]>=(1<<31) else self.reg[self.off[n]] for n in self.scalars]
            code=self.fn(*ptrs,*scalars)
            if code:raise AssertionError('Native hardware status '+str(code))
            self.reg[self.off['ap_return']]=code;self.done=True;total_calls[self.name]+=1
    original_pynq=sys.modules.get('pynq');original_engine=rt.fcm.Engine;original_platform=pc.platform
    sys.modules['pynq']=SimpleNamespace(allocate=lambda shape,dtype:Buffer(shape,dtype))
    pc.platform=SimpleNamespace(system=lambda:'Linux',machine=lambda:'armv7l')
    def simulated_engine(timeout=30.):
        fcm_ip=MMIO('fcm',cnn,rt.fcm.POINTERS,rt.fcm.SCALARS,offsets('fcm_0'))
        pw_ip=MMIO('pointwise',pointwise,pc.POINTERS,pc.SCALARS,offsets('pointwise_0'))
        return SimpleNamespace(ip=fcm_ip,offsets=offsets('fcm_0'),timeout=timeout,poisoned=False,
                               overlay=SimpleNamespace(pointwise_0=pw_ip),clock=100.)
    rt.fcm.Engine=simulated_engine
    api=API(ROOT/'desktop_validation/ort_audit/windows1171/onnxruntime-win-x64-1.17.1/lib/onnxruntime.dll',verify=False)
    factory=lambda path,threads=1,optimize=False:Session(path,threads,optimize,api=api)
    _,_,features=bench.data();names=[list(features)[-1],list(features)[0]]
    references={};checked=[]
    try:
        with bench.execution(factory):
            model=rt.V4Runtime('integer',False,529)
            try:
                for n in names:references[n]=model.run(features[n])[0]
            finally:bench.close(model)
            for debug in (True,False):
                model=rt.V4Runtime('fpga',debug,529)
                try:
                    for name in names:
                        raw,detail=model.run(features[name],audit=debug)
                        if not np.array_equal(raw,references[name]):raise AssertionError('Resident combined hardware simulation differs from full integer model')
                        if len(detail['layers'])!=67:raise AssertionError('Callback count')
                        if debug and not all(r['integer_exact'] for r in detail['layers']):raise AssertionError('Missing audited INT8/INT32')
                        checked.append(dict(audio=name,debug=debug,layers=67,embedding_exact=True))
                        print('[RESIDENT DUAL C++ MMIO EXACT]',name,'debug',debug,flush=True)
                    raw,row=bench.invoke(model,features[names[0]],bench.core.normalize(references[names[1]]))
                    if row['fcm_chunks']!=12 or row['pointwise_chunks']!=55:raise AssertionError('Timed callback receipt count')
                finally:bench.close(model)
                if allocated:raise AssertionError('Simulated resident memory leak')
    finally:
        rt.fcm.Engine=original_engine;pc.platform=original_platform
        if original_pynq is None:sys.modules.pop('pynq',None)
        else:sys.modules['pynq']=original_pynq
    report=dict(pass_=True,actual_hardware=False,scope='Real C++ FCM and PW kernels behind simulated DDR/MMIO; Windows ORT1.17.1; not ARM or PL timing proof',
        checks=checked,native_callback_calls=total_calls,memory_leak=False,actual_hwh_register_map=True)
    bench.save(output/'resident_mmio_validation.json',report)
    print('RESIDENT_MMIO_VALIDATION_PASS',report,flush=True)


if __name__=='__main__':main()
