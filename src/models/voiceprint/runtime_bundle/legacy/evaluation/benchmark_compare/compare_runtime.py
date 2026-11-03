"""V4 full CAM++ integration. Old V3 files/models are read-only dependencies."""
from pathlib import Path
from types import SimpleNamespace
import json
import sys
import time
import xml.etree.ElementTree as ET
import numpy as np
WORK=Path(__file__).resolve().parent
ROOT=WORK.parents[1]
HW=WORK/'hardware_v4'
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(HW))
import runtime_core as core
import fcm_board as fcm
if Path(fcm.__file__).resolve().parent!=HW.resolve():
    raise RuntimeError('A different fcm_board is cached. Restart this Notebook kernel before starting.')
UNSAFE=False


def layers():
    rows=[];params={}
    for index in range(1,13):
        cfg,values,_=fcm.load_case('audio01_isolated%02d'%index)
        rows.append(cfg)
        params[index]={k:v for k,v in values.items() if k not in ('input_r','residual')}
    return rows,params


def windows(total,k,capacity):
    halo=k//2
    payload=total if total<=capacity else capacity-2*halo
    if payload<1:raise ValueError('FCM capacity must include halo')
    for start in range(0,total,payload):
        stop=min(total,start+payload)
        lo,hi=max(0,start-halo),min(total,stop+halo)
        yield lo,hi,start-lo,stop-start,start


class FCMContext:
    """Resident DDR parameters/shared scratch. No allocations in timed calls."""
    def __init__(self,engine,rows,params,capacity,debug):
        from pynq import allocate
        self.engine=engine;self.rows=rows;self.params=params;self.capacity=capacity
        self.debug=debug;self.audit=False;self.safe=True;self.allocated=[];self.resident={};self.scratch={}
        def alloc(value,sentinel=85):
            a=np.ascontiguousarray(value);b=allocate(shape=(a.size+fcm.GUARD,),dtype=a.dtype)
            self.allocated.append(b)
            addr=int(b.physical_address)
            if addr<0 or addr+b.nbytes>0x20000000:raise ValueError('FCM buffer outside mapped DDR')
            b[:a.size]=a.ravel();b[a.size:]=sentinel;b.flush()
            return b
        try:
            for row in rows:
                fcm.bounds(params[row['index']],row)
                self.resident[row['index']]={k:alloc(v) for k,v in params[row['index']].items()}
            ni=max(r['cin']*r['freq'] for r in rows)*capacity
            no=max(r['cout']*((r['freq']+r['stride_f']-1)//r['stride_f']) for r in rows)*capacity
            ns=max(r['cout']*((r['freq']+r['stride_f']-1)//r['stride_f']) for r in rows if r['flags']&4)*capacity
            self.scratch['input_r']=alloc(np.zeros(ni,np.int8))
            self.scratch['residual']=alloc(np.zeros(ns,np.int8))
            self.scratch['output_r']=alloc(np.zeros(no,np.int8))
            self.scratch['accumulator_out']=alloc(np.full(no if debug else 1,fcm.DEBUG_SENTINEL,np.int32),fcm.DEBUG_SENTINEL)
        except BaseException:
            self.close();raise

    def call(self,row,x,skip):
        if not self.safe or UNSAFE:raise RuntimeError('Previous hardware failure; power-cycle board before retrying')
        if x.dtype!=np.int8 or x.shape[:2]!=(row['cin'],row['freq']):raise ValueError('FCM live input layout')
        total=x.shape[2];of=(row['freq']+row['stride_f']-1)//row['stride_f']
        if skip.shape!=(row['cout'],of,total) or skip.dtype!=np.int8:raise ValueError('FCM live residual layout')
        detail={k:0. for k in ('parameter_address_size_switch_ms','input_ddr_copy_flush_ms','fpga_start_done_ms',
            'output_invalidate_copy_ms','output_concat_ms','guard_check_ms')}
        detail.update(chunks=0,pointer_rebinds=0)
        qparts=[];aparts=[]
        for lo,hi,crop,count,start_at in windows(total,row['kernel'],self.capacity):
            t=hi-lo;n=row['cout']*of*t
            current=np.ascontiguousarray(x[...,lo:hi]);res=np.ascontiguousarray(skip[...,lo:hi])
            bufs={**self.resident[row['index']],**self.scratch}
            off=self.engine.offsets;ip=self.engine.ip
            before=time.perf_counter()
            if not ip.read(off['CTRL'])&4:raise RuntimeError('FCM IP busy before launch')
            for name in fcm.POINTERS:
                address=int(bufs[name].physical_address)
                ip.write(off[name+'_1'],address&0xffffffff);ip.write(off[name+'_2'],address>>32)
                if self.audit and (ip.read(off[name+'_1'])!=(address&0xffffffff) or ip.read(off[name+'_2'])!=(address>>32)):
                    raise AssertionError('FCM pointer readback '+name)
            cfg={**row,'frames':t,'flags':(row['flags']&~2)|(2 if self.debug else 0)}
            for name in fcm.SCALARS:
                value=cfg[name]&0xffffffff;ip.write(off[name],value)
                if self.audit and ip.read(off[name])!=value:raise AssertionError('FCM scalar readback '+name)
            detail['parameter_address_size_switch_ms']+=(time.perf_counter()-before)*1000
            before=time.perf_counter()
            bufs['input_r'][:current.size]=current.ravel()
            if row['flags']&4:bufs['residual'][:res.size]=res.ravel()
            if self.audit:
                bufs['input_r'][current.size:current.size+fcm.GUARD]=85
                if row['flags']&4:bufs['residual'][res.size:res.size+fcm.GUARD]=85
                bufs['output_r'].fill(85);bufs['output_r'].flush()
                bufs['accumulator_out'].fill(fcm.DEBUG_SENTINEL);bufs['accumulator_out'].flush()
            bufs['input_r'].flush()
            if row['flags']&4:bufs['residual'].flush()
            detail['input_ddr_copy_flush_ms']+=(time.perf_counter()-before)*1000
            before=time.perf_counter();self.safe=False
            try:
                ip.write(off['CTRL'],1)
                while not ip.read(off['CTRL'])&2:
                    if time.perf_counter()-before>self.engine.timeout:raise TimeoutError('FCM timeout; retain kernel and power-cycle board')
            except BaseException:
                self.engine.poisoned=True;raise
            self.safe=True
            if ip.read(off['ap_return'])!=0:raise RuntimeError('FCM returned nonzero')
            detail['fpga_start_done_ms']+=(time.perf_counter()-before)*1000
            before=time.perf_counter();bufs['output_r'].invalidate()
            q=np.array(bufs['output_r'][:n],copy=True).reshape(row['cout'],of,t)
            qparts.append(q[...,crop:crop+count].copy())
            if self.debug:
                bufs['accumulator_out'].invalidate()
                a=np.array(bufs['accumulator_out'][:n],copy=True).reshape(row['cout'],of,t)
                aparts.append(a[...,crop:crop+count].copy())
            detail['output_invalidate_copy_ms']+=(time.perf_counter()-before)*1000
            if self.audit:
                before=time.perf_counter()
                sizes={'input_r':current.size,'output_r':n,'accumulator_out':n if self.debug else 1}
                if row['flags']&4:sizes['residual']=res.size
                for name,b in bufs.items():
                    b.invalidate();end=sizes.get(name,len(b)-fcm.GUARD)
                    sentinel=fcm.DEBUG_SENTINEL if name=='accumulator_out' else 85
                    if np.any(b[end:end+fcm.GUARD]!=sentinel):raise AssertionError('FCM guard '+name)
                if not self.debug and np.any(bufs['accumulator_out']!=fcm.DEBUG_SENTINEL):raise AssertionError('FCM debug-disabled store')
                detail['guard_check_ms']+=(time.perf_counter()-before)*1000
            detail['chunks']+=1;detail['pointer_rebinds']+=8
        before=time.perf_counter()
        q=np.concatenate(qparts,axis=2);a=np.concatenate(aparts,axis=2) if self.debug else None
        detail['output_concat_ms']+=(time.perf_counter()-before)*1000
        return q,a,detail

    def close(self):
        if self.safe:
            for b in self.allocated:b.freebuffer()
        else:fcm.RETAINED_BUFFERS.extend(self.allocated)
        self.allocated=[];self.resident.clear();self.scratch.clear()


class FCMRunner:
    def __init__(self,rows,params,context=None):
        self.rows=rows;self.params=params;self.context=context;self.audit=False;self.last=[]
    def run(self,xq):
        values={self.rows[0]['input_tensor']:np.ascontiguousarray(xq[0])};self.last=[]
        for i,row in enumerate(self.rows):
            x=values[row['input_tensor']];of=(x.shape[1]+row['stride_f']-1)//row['stride_f']
            skip=values[row['skip_tensor']] if row['skip_tensor'] else np.zeros((row['cout'],of,x.shape[2]),np.int8)
            cfg={**row,'freq':x.shape[1],'frames':x.shape[2]};before=time.perf_counter()
            inputs={**self.params[row['index']],'input_r':x,'residual':skip}
            if self.context:
                self.context.audit=self.audit
                q,a,detail=self.context.call(row,x,skip)
                if self.audit:
                    gold=fcm.software_reference(inputs,cfg)
                    fcm.exact(q,gold['output_r'],'FCM current INT8 '+row['name'])
                    if a is None:raise AssertionError('FCM audit requires debug INT32')
                    fcm.exact(a,gold['accumulator_out'],'FCM current INT32 '+row['name'])
            else:
                gold=fcm.software_reference(inputs,cfg);q=gold['output_r'];detail={}
            record=dict(index=row['index'],name=row['name'],component='FCM',frames=x.shape[2],
                callback_ms=(time.perf_counter()-before)*1000,integer_exact=bool(self.context and self.audit),**detail)
            self.last.append(record)
            values[row['post_output_tensor']]=q
            pending={k for r in self.rows[i+1:] for k in (r['input_tensor'],r['skip_tensor']) if k}
            pending.add(self.rows[-1]['post_output_tensor'])
            values={k:v for k,v in values.items() if k in pending}
        result=values[self.rows[-1]['post_output_tensor']]
        return np.ascontiguousarray(result.reshape(1,320,result.shape[-1]))


class FirstCPU:
    def __init__(self,runner=None,bypass=False):
        self.runner=runner;self.bypass=bypass;self.last_ms=0.;self.last_rows=[]
        self.input=core.ort_session(WORK/'assets'/('fcm_original.onnx' if bypass else 'fcm_input.onnx'))
        self.tail=core.ort_session(WORK/'assets/cpu000_after_fcm.onnx')
        self.provenance=json.loads((WORK/'assets/provenance.json').read_text())
    def run(self,names,feeds):
        x=self.input.run(None,{'features':feeds['features']})[0]
        self.last_ms=0.;self.last_rows=[]
        if not self.bypass:
            before=time.perf_counter();x=self.runner.run(x)
            self.last_ms=(time.perf_counter()-before)*1000;self.last_rows=self.runner.last
        return self.tail.run(names,{'features':feeds['features'],self.provenance['yq']:x})
    def close(self):
        for s in (self.input,self.tail):
            if hasattr(s,'close'):s.close()


def v4_pw_context(engine,base,debug):
    import fpga_context as pc
    tree=ET.parse(HW/'fcm_v4.hwh').getroot()
    module=next(m for m in tree.iter('MODULE') if m.get('INSTANCE')=='pointwise_0')
    if module.get('VLNV')!='xilinx.com:hls:pointwise:1.0':raise ValueError('Unexpected V3 IP in V4')
    offsets={}
    for r in module.findall('.//REGISTERS/REGISTER'):
        p=r.find("./PROPERTY[@NAME='ADDRESS_OFFSET']")
        if p is not None:offsets[r.get('NAME')]=int(p.get('VALUE'),0)
    required=['CTRL','GIER','IP_IER','ap_return',*pc.SCALARS]
    for p in pc.POINTERS:required.extend([p+'_1',p+'_2'])
    if any(p not in offsets for p in required):raise ValueError('Incomplete V4 pointwise HWH')
    shared=SimpleNamespace(ip=engine.overlay.pointwise_0,offsets=offsets,timeout=30.)
    for key in ('GIER','IP_IER'):shared.ip.write(offsets[key],0)
    original=pc.Engine;pc.Engine=lambda timeout=30.:shared
    try:return pc.FPGAContext([base.layers[k] for k in base.params],base.params,debug=debug)
    finally:pc.Engine=original


class V4Runtime:
    def __init__(self,mode='fpga',debug=False,capacity=529):
        global UNSAFE
        if UNSAFE:raise RuntimeError('Previous active hardware failure. Power-cycle board and restart kernel.')
        if mode not in ('fpga','integer','bypass'):raise ValueError('V4 mode')
        self.base=None;self.fcm_context=None;self.runner=None;self.first=None
        rows,params=layers()
        if mode!='bypass':self.runner=FCMRunner(rows,params)
        original=core.ort_session
        target=(core.BUNDLE/'plans/all55/cpu_000.onnx').resolve()
        def factory(path,threads=1,optimize=False):
            if Path(path).resolve()==target:
                self.first=FirstCPU(self.runner,bypass=mode=='bypass');return self.first
            return original(path,threads,optimize)
        core.ort_session=factory
        try:self.base=core.Hybrid('all55','bypass' if mode=='bypass' else 'integer',1,debug)
        finally:core.ort_session=original
        try:
            if mode=='fpga':
                engine=fcm.Engine(timeout=30.)
                self.fcm_context=FCMContext(engine,rows,params,min(2048,capacity),debug)
                self.runner.context=self.fcm_context
                self.base.fpga=v4_pw_context(engine,self.base,debug)
                self.base.mode='fpga'
            self.mode=mode
        except BaseException:
            self.close();raise
    def run(self,features,audit=False):
        if self.runner:self.runner.audit=audit
        raw,report=self.base.run(features,audit)
        report['cpu_remaining_ms']-=self.first.last_ms
        report['layer_callback_ms']+=self.first.last_ms
        report['layers']=self.first.last_rows+[{**r,'component':'pointwise'} for r in report['layers']]
        if self.mode=='fpga' and len(report['layers'])!=67:raise AssertionError('Expected12 FCM +55 pointwise callbacks')
        return raw,report
    def close(self):
        global UNSAFE
        if self.base and self.base.fpga and not self.base.fpga.safe:UNSAFE=True
        if self.fcm_context and not self.fcm_context.safe:UNSAFE=True
        if self.base:self.base.close()
        if self.fcm_context:self.fcm_context.close()
        self.base=None;self.fcm_context=None


class FP32CPU:
    def __init__(self):self.session=core.ort_session(WORK/'assets/camplus_fp32_pool_compatible.onnx',1,True)
    def run(self,features,audit=False):
        t=time.perf_counter();raw=self.session.run(['embedding'],{'features':features})[0]
        return raw,dict(cpu_remaining_ms=(time.perf_counter()-t)*1000,layers=[],layer_callback_ms=0.)
    def close(self):
        if hasattr(self.session,'close'):self.session.close()
