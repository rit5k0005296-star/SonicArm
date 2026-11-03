"""V3 shared references and PYNQ driver. Importing never loads an overlay.
Data are isolated real-model layer inputs, not an offloaded CAM++ runtime.
"""
from pathlib import Path
import hashlib
import json
import platform
import time
import xml.etree.ElementTree as ET
import numpy as np

HERE=Path(__file__).resolve().parent
POINTERS=('input_r','weights','bias','multiplier','post_lut','output_r','accumulator_out')
SCALARS=('cin','cout','frames','input_zp','output_zp','requant_shift','flags')
RETAINED_BUFFERS=[]
GUARD=16
DEBUG_SENTINEL=0x5a5a5a5a

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def exact(actual,expected,label):
    a=np.asarray(actual);b=np.asarray(expected)
    if a.shape!=b.shape:raise AssertionError(label+' shape mismatch')
    indices=np.flatnonzero(a.ravel()!=b.ravel())
    if indices.size:
        k=int(indices[0]);raise AssertionError('{}: {} mismatches; first flat index {} actual={} expected={}'.format(label,indices.size,k,int(a.ravel()[k]),int(b.ravel()[k])))

def checked_config(cfg):
    for key in SCALARS:
        if not isinstance(cfg.get(key),int):raise ValueError('Invalid integer config: '+key)
    if not (1<=cfg['cin']<=1024 and 1<=cfg['cout']<=512 and 1<=cfg['frames']<=2048):raise ValueError('Dimension limits')
    if not (-128<=cfg['input_zp']<=127 and -128<=cfg['output_zp']<=127 and 8<=cfg['requant_shift']<=40 and 0<=cfg['flags']<=3):raise ValueError('Quantization/flags limits')

def quantize(acc,multiplier,cfg):
    p=np.asarray(acc,dtype=np.int64)*multiplier.astype(np.int64)[:,None]
    mag=np.abs(p);shift=cfg['requant_shift'];whole=mag>>shift
    fraction=mag&((1<<shift)-1);half=1<<(shift-1)
    whole+=(fraction>half)|((fraction==half)&((whole&1)!=0))
    return np.clip(np.where(p<0,-whole,whole)+cfg['output_zp'],-128,127).astype(np.int8)

def bounds(inputs,cfg):
    delta=max(abs(-128-cfg['input_zp']),abs(127-cfg['input_zp']))
    bound=np.abs(inputs['weights'].astype(np.int64)).sum(axis=1)*delta+np.abs(inputs['bias'].astype(np.int64))
    if np.any(bound>np.iinfo(np.int32).max):raise ValueError('INT32 partial sums not proved safe')
    return bound

def software_reference(inputs,cfg):
    bounds(inputs,cfg)
    acc=inputs['weights'].astype(np.int64)@(inputs['input_r'].astype(np.int64)-cfg['input_zp'])+inputs['bias'].astype(np.int64)[:,None]
    q=quantize(acc,inputs['multiplier'],cfg)
    if cfg['flags']&1:q=inputs['post_lut'][q.astype(np.int16)+128]
    return {'output_r':q,'accumulator_out':acc.astype(np.int32)}

def case_items(selection='all'):
    items=json.loads((HERE/'cases/cases.json').read_text(encoding='utf-8'))['cases']
    if len(items)!=110 or len({x['case'] for x in items})!=110:raise ValueError('Expected 110 distinct cases')
    if selection=='all':return items
    names=(HERE/'cases/representative_cases.txt').read_text().splitlines() if selection=='representative' else selection.split(',')
    lookup={x['case']:x for x in items}
    if not names or len(names)!=len(set(names)) or any(n not in lookup for n in names):raise ValueError('Invalid case selection')
    return [lookup[n] for n in names]

def load_case(item,recompute=False):
    directory=(HERE/'cases'/item['case']).resolve()
    if directory.parent!=(HERE/'cases').resolve():raise ValueError('Unsafe case directory')
    cfg=json.loads((directory/'config.json').read_text(encoding='utf-8'));checked_config(cfg)
    if cfg!=item:raise ValueError('Case index/config mismatch')
    report=json.loads((HERE/'reference_report.json').read_text(encoding='utf-8'))
    if cfg['model_sha256']!=report['model_sha256']:raise ValueError('Model hash mismatch')
    for name,sha in cfg['files_sha256'].items():
        file=(directory/name).resolve()
        if file.parent!=directory or digest(file)!=sha:raise ValueError('Case hash mismatch: '+name)
    ci,co,t=cfg['cin'],cfg['cout'],cfg['frames']
    def binary(name,dtype,shape):
        file=directory/name;dtype=np.dtype(dtype)
        if file.stat().st_size!=int(np.prod(shape))*dtype.itemsize:raise ValueError('Binary size mismatch: '+name)
        return np.fromfile(file,dtype=dtype).reshape(shape)
    inputs={'input_r':binary('input_int8.bin','i1',(ci,t)), 'weights':binary('weights_int8.bin','i1',(co,ci)),
            'bias':binary('bias_int32.bin','<i4',(co,)), 'multiplier':binary('multiplier_uint32.bin','<u4',(co,)),
            'post_lut':binary('post_lut_int8.bin','i1',(256,))}
    refs={'output_r':binary('reference_output_int8.bin','i1',(co,t)), 'accumulator_out':binary('reference_accum_int32.bin','<i4',(co,t)),
          'onnx':binary('onnx_output_int8.bin','i1',(co,t))}
    bounds(inputs,cfg)
    q=quantize(refs['accumulator_out'],inputs['multiplier'],cfg)
    if cfg['flags']&1:q=inputs['post_lut'][q.astype(np.int16)+128]
    exact(q,refs['output_r'],'integer reference')
    difference=np.abs(refs['output_r'].astype(np.int16)-refs['onnx'].astype(np.int16))
    if int(np.count_nonzero(difference))!=cfg['onnx_mismatches'] or int(difference.max())!=cfg['onnx_max_lsb'] or int(difference.max())>1:raise ValueError('ONNX mismatch audit changed')
    if recompute:
        gold=software_reference(inputs,cfg)
        for name in gold:exact(gold[name],refs[name],'recomputed '+name)
    return cfg,inputs,refs

def offsets_from_hwh():
    tree=ET.parse(HERE/'pointwise.hwh').getroot()
    module=next((m for m in tree.iter('MODULE') if m.get('INSTANCE')=='pointwise_0'),None)
    if module is None or module.get('VLNV')!='xilinx.com:hls:pointwise:1.0':raise ValueError('Wrong V3 HWH IP')
    offsets={}
    for reg in module.findall('.//REGISTERS/REGISTER'):
        prop=reg.find("./PROPERTY[@NAME='ADDRESS_OFFSET']")
        if prop is not None:offsets[reg.get('NAME')]=int(prop.get('VALUE'),0)
    required=['CTRL','GIER','IP_IER','ap_return']+list(SCALARS)
    for name in POINTERS:required.extend([name+'_1',name+'_2'])
    if any(name not in offsets for name in required):raise ValueError('Incomplete V3 HWH register map')
    ps=next(m for m in tree.iter('MODULE') if m.get('INSTANCE')=='processing_system7_0')
    params={p.get('NAME'):p.get('VALUE') for p in ps.iter('PARAMETER')}
    if abs(float(params['PCW_FPGA0_PERIPHERAL_FREQMHZ'])-100)>0.01 or params['PCW_USE_M_AXI_GP0']!='1' or params['PCW_USE_S_AXI_HP0']!='1':raise ValueError('Wrong PS7 clock or AXI configuration')
    return offsets

class Engine:
    def __init__(self,timeout=10.):
        if platform.system()!='Linux' or platform.machine().lower() not in ('armv7l','armv8l'):raise RuntimeError('Hardware cells must run on PYNQ-Z2 ARM Linux')
        from pynq import Overlay,Clocks
        self.offsets=offsets_from_hwh();self.timeout=timeout
        self.overlay=Overlay(str(HERE/'pointwise.bit'));self.ip=self.overlay.pointwise_0
        self.clock=float(Clocks.fclk0_mhz)
        if abs(self.clock-100)>0.5:raise RuntimeError('Expected 100 MHz after Overlay load')
        self.ip.write(self.offsets['GIER'],0);self.ip.write(self.offsets['IP_IER'],0)

    def session(self,cfg,inputs):return Session(self,cfg,inputs)

class Session:
    def __init__(self,engine,cfg,inputs):
        from pynq import allocate
        self.engine=engine;self.cfg=dict(cfg);self.buffers={};self.safe=True;self.shapes={}
        values=dict(inputs)
        values['output_r']=np.zeros((cfg['cout'],cfg['frames']),dtype=np.int8)
        values['accumulator_out']=np.zeros((cfg['cout'],cfg['frames']),dtype=np.int32)
        try:
            for name,value in values.items():
                self.shapes[name]=value.shape
                buf=allocate(shape=(value.size+GUARD,),dtype=value.dtype);self.buffers[name]=buf
                self.view(name)[:]=value;buf[value.size:]=self.sentinel(name)
                address=int(buf.physical_address)
                if address<0 or address+buf.nbytes>0x20000000:raise ValueError('Buffer outside mapped 512 MiB DDR')
                buf.flush();engine.ip.write(engine.offsets[name+'_1'],address&0xffffffff);engine.ip.write(engine.offsets[name+'_2'],address>>32)
            self.configure(cfg['flags'])
        except Exception:
            self.close();raise

    def sentinel(self,name):return DEBUG_SENTINEL if name=='accumulator_out' else 85
    def view(self,name):return self.buffers[name][:int(np.prod(self.shapes[name]))].reshape(self.shapes[name])
    def configure(self,flags,cin=None):
        for name in SCALARS:
            value=flags if name=='flags' else cin if name=='cin' and cin is not None else self.cfg[name]
            self.engine.ip.write(self.engine.offsets[name],int(value)&0xffffffff)
        self.flags=flags
    def prepare_outputs(self):
        for name in ('output_r','accumulator_out'):
            self.buffers[name].fill(self.sentinel(name));self.buffers[name].flush()
    def launch(self,expected_return=0):
        ip=self.engine.ip;off=self.engine.offsets
        if not (ip.read(off['CTRL'])&4):raise RuntimeError('IP is not idle before launch')
        start=time.perf_counter();self.safe=False;ip.write(off['CTRL'],1)
        while not (ip.read(off['CTRL'])&2):
            if time.perf_counter()-start>self.engine.timeout:raise TimeoutError('IP timeout. Reboot board before retrying; buffers retained while hardware may be active.')
        end=time.perf_counter();self.safe=True
        code=ip.read(off['ap_return']);code=code-(1<<32) if code>=(1<<31) else code
        if code!=expected_return:raise RuntimeError('Unexpected IP return code: '+str(code))
        return (end-start)*1000
    def validate(self,refs):
        for name in ('output_r','accumulator_out'):
            self.buffers[name].invalidate()
            if name=='output_r' or self.flags&2:exact(self.view(name),refs[name],name)
            else:
                if np.any(self.view(name)!=DEBUG_SENTINEL):raise AssertionError('Debug-disabled output was modified')
            if np.any(self.buffers[name][int(np.prod(self.shapes[name])):]!=self.sentinel(name)):raise AssertionError('Guard overwritten: '+name)
    def call(self,inputs,refs,flags):
        self.configure(flags);self.prepare_outputs()
        self.view('input_r')[:]=inputs['input_r'];self.buffers['input_r'].flush()
        self.launch();self.validate(refs)
    def close(self):
        if self.safe:
            for buf in self.buffers.values():buf.freebuffer()
        else:RETAINED_BUFFERS.extend(self.buffers.values())
        self.buffers={}
    def __enter__(self):return self
    def __exit__(self,*args):self.close()

def feature_cases():
    for ci,co,t,lut_on in ((17,9,65,True),(1,1,2048,False)):
        cfg=dict(cin=ci,cout=co,frames=t,input_zp=13,output_zp=-7,requant_shift=38,flags=3 if lut_on else 2)
        inputs={'input_r':np.where(np.indices((ci,t)).sum(0)%2,127,-128).astype(np.int8),
                'weights':np.where(np.indices((co,ci)).sum(0)%2,-128,127).astype(np.int8),
                'bias':np.arange(co,dtype=np.int32)*17-1000,'multiplier':np.full(co,1<<30,dtype=np.uint32),
                'post_lut':np.maximum(-7,np.arange(-128,128)).astype(np.int8)}
        yield cfg,inputs,software_reference(inputs,cfg)
