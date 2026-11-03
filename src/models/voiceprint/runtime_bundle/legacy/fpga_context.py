"""One IP, resident per-layer DDR parameters and one shared scratch pool.
Every call rebinds all seven 64-bit pointer pairs and all seven scalars.
Long recordings are split ONLY along pointwise time; CPU context/attention stay full.
"""
import platform
import sys
import time
import numpy as np
from runtime_core import BUNDLE
sys.path.insert(0,str(BUNDLE/'support'))
from pointwise_board import Engine, POINTERS, SCALARS, GUARD, DEBUG_SENTINEL, RETAINED_BUFFERS


class FPGAContext:
    def __init__(self,layers,params,debug=False,capacity=2048):
        if platform.system()!='Linux' or platform.machine().lower() not in ('armv7l','armv8l'):
            raise RuntimeError('Real FPGA mode requires PYNQ-Z2 ARM Linux')
        from pynq import allocate
        self.engine=Engine(timeout=30.);self.debug=debug;self.audit=False
        self.capacity=capacity;self.safe=True;self.resident={};self.scratch={};self.allocated=[]
        self.allocation_ms=0.;start=time.perf_counter()
        def alloc(value):
            value=np.ascontiguousarray(value)
            buf=allocate(shape=(value.size+GUARD,),dtype=value.dtype)
            self.allocated.append(buf)
            addr=int(buf.physical_address)
            if addr<0 or addr+buf.nbytes>0x20000000:
                raise ValueError('Buffer outside PYNQ-Z2 mapped DDR')
            buf[:value.size]=value.ravel();buf[value.size:]=85;buf.flush()
            return buf
        try:
            for layer in layers:
                self.resident[layer['index']]={k:alloc(v) for k,v in params[layer['index']].items()}
            self.scratch['input_r']=alloc(np.zeros(max(x['cin'] for x in layers)*capacity,dtype=np.int8))
            self.scratch['output_r']=alloc(np.zeros(max(x['cout'] for x in layers)*capacity,dtype=np.int8))
            size=max(x['cout'] for x in layers)*capacity if debug else 1
            self.scratch['accumulator_out']=alloc(np.full(size,DEBUG_SENTINEL,dtype=np.int32))
            self.allocation_ms=(time.perf_counter()-start)*1000
        except Exception:
            self.close()
            raise

    def call(self,layer,x):
        if not self.safe:
            raise RuntimeError('IP timed out; reboot before any further call')
        if x.dtype!=np.int8 or x.ndim!=3 or x.shape[:2]!=(1,layer['cin']) or x.shape[2]<1:
            raise ValueError('Invalid live pointwise tensor')
        ip=self.engine.ip;offsets=self.engine.offsets
        outputs=[];accumulators=[]
        detail={k:0. for k in ('parameter_address_size_switch_ms','input_ddr_copy_flush_ms',
                              'fpga_start_done_ms','output_invalidate_copy_ms','guard_check_ms','output_concat_ms')}
        detail['chunks']=0;detail['pointer_rebinds']=0
        for begin in range(0,x.shape[2],self.capacity):
            current=np.ascontiguousarray(x[0,:,begin:begin+self.capacity])
            frames=current.shape[1];ci=layer['cin'];co=layer['cout']
            buffers={**self.resident[layer['index']],**self.scratch}
            start=time.perf_counter()
            if not (ip.read(offsets['CTRL'])&4):
                raise RuntimeError('IP busy before context switch')
            for name in POINTERS:
                address=int(buffers[name].physical_address)
                ip.write(offsets[name+'_1'],address&0xffffffff)
                ip.write(offsets[name+'_2'],address>>32)
                if self.audit:
                    if ip.read(offsets[name+'_1'])!=(address&0xffffffff) or ip.read(offsets[name+'_2'])!=(address>>32):
                        raise AssertionError('Pointer readback failed '+name)
            cfg={**layer,'frames':frames,'flags':2 if self.debug else 0}
            for name in SCALARS:
                ip.write(offsets[name],int(cfg[name])&0xffffffff)
                if self.audit and ip.read(offsets[name])!=(int(cfg[name])&0xffffffff):
                    raise AssertionError('Scalar readback failed '+name)
            detail['parameter_address_size_switch_ms']+=(time.perf_counter()-start)*1000
            start=time.perf_counter()
            inp=buffers['input_r'];inp[:ci*frames]=current.ravel()
            if self.audit:
                inp[ci*frames:ci*frames+GUARD]=85
                buffers['output_r'].fill(85);buffers['output_r'].flush()
                buffers['accumulator_out'].fill(DEBUG_SENTINEL);buffers['accumulator_out'].flush()
            inp.flush()
            detail['input_ddr_copy_flush_ms']+=(time.perf_counter()-start)*1000
            start=time.perf_counter();self.safe=False
            ip.write(offsets['CTRL'],1)
            while not (ip.read(offsets['CTRL'])&2):
                if time.perf_counter()-start>self.engine.timeout:
                    raise TimeoutError('FPGA timeout; buffers retained. Reboot before retry.')
            self.safe=True
            code=ip.read(offsets['ap_return'])
            if code:
                raise RuntimeError('Pointwise return code '+str(code))
            detail['fpga_start_done_ms']+=(time.perf_counter()-start)*1000
            start=time.perf_counter()
            out=buffers['output_r'];out.invalidate()
            outputs.append(np.array(out[:co*frames],copy=True).reshape(1,co,frames))
            if self.debug:
                buffers['accumulator_out'].invalidate()
                accumulators.append(np.array(buffers['accumulator_out'][:co*frames],copy=True).reshape(1,co,frames))
            detail['output_invalidate_copy_ms']+=(time.perf_counter()-start)*1000
            if self.audit:
                start=time.perf_counter()
                for name in POINTERS:
                    b=buffers[name];b.invalidate()
                    end=ci*frames if name=='input_r' else co*frames if name=='output_r' else co*frames if name=='accumulator_out' and self.debug else len(b)-GUARD
                    sentinel=DEBUG_SENTINEL if name=='accumulator_out' else 85
                    if np.any(b[end:end+GUARD]!=sentinel):
                        raise AssertionError('Guard overwritten '+name)
                    if name=='accumulator_out' and not self.debug and np.any(b!=DEBUG_SENTINEL):
                        raise AssertionError('Debug-disabled output modified')
                detail['guard_check_ms']+=(time.perf_counter()-start)*1000
            detail['chunks']+=1;detail['pointer_rebinds']+=len(POINTERS)
        start=time.perf_counter()
        q=np.concatenate(outputs,axis=2)
        acc=np.concatenate(accumulators,axis=2) if self.debug else None
        detail['output_concat_ms']+=(time.perf_counter()-start)*1000
        return q,acc,detail

    def close(self):
        if self.safe:
            for buf in self.allocated:
                buf.freebuffer()
        else:
            RETAINED_BUFFERS.extend(self.allocated)
        self.allocated=[];self.resident.clear();self.scratch.clear()
