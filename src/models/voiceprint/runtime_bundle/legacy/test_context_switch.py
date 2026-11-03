"""Desktop MMIO/buffer mock: tests actual manager rebinding, guards, chunks, timeout retention.
This is SOFTWARE validation of host control only, never FPGA correctness evidence.
"""
import json
import sys
import types
from unittest.mock import patch
import numpy as np
from runtime_core import HERE,BUNDLE,integer_pointwise,save
import fpga_context as context


class Buffer(np.ndarray):
    address=0x100000
    registry={}
    def __new__(cls,shape,dtype):
        value=np.zeros(shape,dtype=dtype).view(cls)
        value.physical_address=cls.address
        cls.address+=((value.nbytes+4095)//4096)*4096
        cls.registry[value.physical_address]=value
        value.freed=False
        return value
    def flush(self):
        pass
    def invalidate(self):
        pass
    def freebuffer(self):
        self.freed=True


class FakeIP:
    def __init__(self):
        names=['CTRL','ap_return']+list(context.SCALARS)+[x+'_'+str(i) for x in context.POINTERS for i in (1,2)]
        self.offsets={x:i*4 for i,x in enumerate(names)};self.reg={};self.launches=0
        self.fail_timeout=False
    def read(self,offset):
        return self.reg.get(offset,4 if offset==self.offsets['CTRL'] else 0)
    def write(self,offset,value):
        self.reg[offset]=value
        if offset==self.offsets['CTRL'] and value==1:
            self.launches+=1
            if self.fail_timeout:
                self.reg[offset]=0
                return
            def scalar(name):
                v=self.reg[self.offsets[name]]
                return v-(1<<32) if name.endswith('_zp') and v>=1<<31 else v
            cfg={k:scalar(k) for k in context.SCALARS}
            def buf(name):
                addr=self.reg[self.offsets[name+'_1']]+(self.reg[self.offsets[name+'_2']]<<32)
                return Buffer.registry[addr]
            ci,co,t=cfg['cin'],cfg['cout'],cfg['frames']
            params={'weights':np.asarray(buf('weights')[:ci*co]).reshape(co,ci),
                    'bias':np.asarray(buf('bias')[:co]),'multiplier':np.asarray(buf('multiplier')[:co])}
            x=np.asarray(buf('input_r')[:ci*t]).reshape(1,ci,t)
            q,acc=integer_pointwise(cfg,params,x,True)
            buf('output_r')[:co*t]=q.ravel()
            if cfg['flags']&2:
                buf('accumulator_out')[:co*t]=acc.ravel()
            self.reg[self.offsets['ap_return']]=0
            self.reg[offset]=6


class FakeEngine:
    def __init__(self,timeout=30.):
        self.ip=FakeIP();self.offsets=self.ip.offsets;self.timeout=timeout


def main():
    layers=json.loads((BUNDLE/'layers.json').read_text());params={}
    for layer in layers:
        with np.load(BUNDLE/layer['params']) as data:
            params[layer['index']]={k:data[k].copy() for k in data.files}
    pynq=types.SimpleNamespace(allocate=lambda shape,dtype:Buffer(shape,dtype))
    rng=np.random.default_rng(20261015);count=0;launches=0
    with patch.dict(sys.modules,{'pynq':pynq}),patch.object(context,'Engine',FakeEngine),patch.object(context.platform,'system',return_value='Linux'),patch.object(context.platform,'machine',return_value='armv7l'):
        for debug in (False,True):
            manager=context.FPGAContext(layers,params,debug,capacity=64);manager.audit=True
            try:
                # All layers twice in reversed order: catches last-session pointer reuse.
                sequence=layers+list(reversed(layers))
                for i,layer in enumerate(sequence):
                    t=65 if i%2 else 129
                    x=rng.integers(-128,128,size=(1,layer['cin'],t),dtype=np.int8)
                    actual,acc,details=manager.call(layer,x)
                    gold,gold_acc=integer_pointwise(layer,params[layer['index']],x,True)
                    assert np.array_equal(actual,gold)
                    assert acc is None if not debug else np.array_equal(acc,gold_acc)
                    assert details['pointer_rebinds']==details['chunks']*7
                    count+=1
                layer=layers[0];x=rng.integers(-128,128,size=(1,layer['cin'],2049),dtype=np.int8)
                actual,acc,details=manager.call(layer,x)
                gold,_=integer_pointwise(layer,params[layer['index']],x,True)
                assert np.array_equal(actual,gold) and details['chunks']==33
                launches+=manager.engine.ip.launches;count+=1
            finally:
                manager.close()
        # A timed-out bus master must retain both scratch and all parameter allocations.
        manager=context.FPGAContext(layers[:1],params,False,64)
        allocated=list(manager.allocated);manager.engine.timeout=0.;manager.engine.ip.fail_timeout=True
        try:
            manager.call(layers[0],np.zeros((1,layers[0]['cin'],1),dtype=np.int8))
            raise AssertionError('Timeout was not detected')
        except TimeoutError:
            manager.close()
            assert all(not x.freed for x in allocated)
            assert all(any(x is b for b in context.RETAINED_BUFFERS) for x in allocated)
        # Fake buffers can be safely disposed; real timed-out DMA buffers cannot.
        context.RETAINED_BUFFERS.clear()
    result={'pass':True,'scope':'SOFTWARE MMIO and buffer simulation only; no FPGA used',
            'calls':count,'launches':launches,'55_layers_both_orders':True,'debug_on_off':True,
            '2049_frame_chunking':True,'timeout_buffers_retained':True}
    save(HERE/'desktop_validation/context_switch.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
