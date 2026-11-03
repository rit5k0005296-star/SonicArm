"""Reuse validated hardware drivers; replace only CPU graph extraction/interfaces."""
from contextlib import contextmanager
import json
import time
import numpy as np
from paths import WORK, LEGACY
import compare_runtime as old
import compare_benchmark as bench
import runtime_core as core
import compatible_all55 as compat
from all55_fast_diagnostic import reference_and_progress


def tensor_summary(names, values):
    return [dict(name=n, shape=list(v.shape), dtype=str(v.dtype), bytes=int(v.nbytes)) for n,v in zip(names,values)]


class ProfileSession:
    def __init__(self, session, path, collector):
        self.session, self.collector = session, collector
        path = path.resolve()
        self.name = ('test_1/' + path.relative_to(WORK).as_posix()) if path.is_relative_to(WORK) else ('legacy/' + path.relative_to(LEGACY).as_posix())
    def __getattr__(self, name):
        return getattr(self.session, name)
    def run(self, names, feed):
        before = time.perf_counter()
        out = self.session.run(names,feed)
        elapsed = (time.perf_counter()-before)*1000
        requested = [v.name for v in self.session.get_outputs()] if names is None else names
        self.collector.append(dict(component='CPU',name=self.name,cpu_session_ms=elapsed,
                                   inputs=tensor_summary(list(feed),list(feed.values())),outputs=tensor_summary(requested,out)))
        return out
    def close(self):
        self.session.close()


@contextmanager
def execution(optimize=True, collector=None, factory=None):
    mapping = compat.validate()
    original = core.ort_session
    base = factory or original
    def selected(path, threads=1, optimize=False):
        resolved = path.resolve()
        if resolved.is_relative_to(LEGACY):
            key = resolved.relative_to(LEGACY).as_posix()
            if key in mapping:
                resolved = LEGACY/mapping[key]['compatible_file']
        session = base(resolved, threads, requested)
        return session if collector is None else ProfileSession(session,resolved,collector)
    requested = bool(optimize)
    core.ort_session = selected
    try:
        with reference_and_progress() as original_integer:
            yield original_integer
    finally:
        core.ort_session = original


class StaticHybrid(core.Hybrid):
    def __init__(self, mode='integer', debug=False, first=None):
        if mode not in ('integer','bypass','fpga'):
            raise ValueError('Invalid mode')
        self.mode, self.debug, self.plan_name, self.threads = mode,debug,'all55',1
        self.trace_sink = self.audit_sink = None
        self.directory = WORK/'assets/v3'
        self.plan = json.loads((self.directory/'plan.json').read_text(encoding='utf8'))
        self.layers = {v['index']:v for v in json.loads((core.BUNDLE/'layers.json').read_text(encoding='utf8'))}
        self.params, self.sessions, self.islands, self.fpga = {},{},{},None
        try:
            for i,op in enumerate(self.plan['ops']):
                if op['kind']=='cpu':
                    self.sessions[i] = first if first is not None and i==0 else core.ort_session(self.directory/op['file'],1)
                else:
                    layer = self.layers[op['layer']]
                    with np.load(core.BUNDLE/layer['params'],allow_pickle=False) as p:
                        self.params[op['layer']] = {k:p[k].copy() for k in p.files}
                    if mode=='bypass':
                        self.islands[op['layer']] = core.ort_session(core.BUNDLE/layer['island'],1)
            if mode=='fpga':
                if old.UNSAFE:
                    raise RuntimeError('Previous hardware failure; power-cycle board')
                from fpga_context import FPGAContext
                self.fpga = FPGAContext([self.layers[k] for k in self.params], self.params, debug=debug)
        except BaseException:
            self.close()
            raise


class FirstCPU:
    def __init__(self, runner, bypass=False):
        self.runner, self.bypass = runner,bypass
        self.last_ms, self.last_rows = 0.,[]
        self.input = core.ort_session(WORK/'assets/v4'/('fcm_original.onnx' if bypass else 'fcm_input.onnx'),1)
        self.tail = core.ort_session(WORK/'assets/v4/cpu_after_fcm.onnx',1)
        self.yq = json.loads((WORK/'assets/build_report.json').read_text(encoding='utf8'))['yq']
    def run(self, names, feed):
        x = self.input.run(None,{'features':feed['features']})[0]
        self.last_ms,self.last_rows = 0.,[]
        if not self.bypass:
            before = time.perf_counter()
            x = self.runner.run(x)
            self.last_ms = (time.perf_counter()-before)*1000
            self.last_rows = self.runner.last
        return self.tail.run(names,{self.yq:x})
    def close(self):
        for session in (self.input,self.tail):
            session.close()


class StaticV4:
    def __init__(self, mode='integer', debug=False, capacity=529):
        self.base = self.fcm_context = self.runner = self.first = None
        self.mode = mode
        if old.UNSAFE:
            raise RuntimeError('Previous hardware failure; power-cycle board')
        rows,params = old.layers()
        if mode!='bypass':
            self.runner = old.FCMRunner(rows,params)
        try:
            self.first = FirstCPU(self.runner,bypass=mode=='bypass')
            self.base = StaticHybrid('bypass' if mode=='bypass' else 'integer',debug,first=self.first)
            if mode=='fpga':
                engine = old.fcm.Engine(timeout=30.)
                self.fcm_context = old.FCMContext(engine,rows,params,min(2048,capacity),debug)
                self.runner.context = self.fcm_context
                self.base.fpga = old.v4_pw_context(engine,self.base,debug)
                self.base.mode = 'fpga'
        except BaseException:
            self.close()
            raise
    def run(self, features, audit=False):
        if self.runner:
            self.runner.audit = audit
        raw,detail = self.base.run(features,audit)
        detail['cpu_remaining_ms'] -= self.first.last_ms
        detail['layer_callback_ms'] += self.first.last_ms
        detail['layers'] = self.first.last_rows + [{**r,'component':'pointwise'} for r in detail['layers']]
        if self.mode=='fpga' and len(detail['layers'])!=67:
            raise AssertionError('Expected 12 FCM and 55 pointwise layers')
        return raw,detail
    def close(self):
        if self.base and self.base.fpga and not self.base.fpga.safe:
            old.UNSAFE = True
        if self.fcm_context and not self.fcm_context.safe:
            old.UNSAFE = True
        if self.base:
            self.base.close()
        elif self.first:
            self.first.close()
        if self.fcm_context:
            self.fcm_context.close()
        self.base = self.fcm_context = self.first = None


def make(mode, capacity, hardware=True, debug=False, bypass=False):
    if mode=='cpu_fp32':
        return old.FP32CPU()
    if mode=='cpu_int8':
        return core.FullCPU(1,True)
    if mode=='cpu_reference':
        return core.FullCPU(1,False)
    kind = 'bypass' if bypass else ('fpga' if hardware else 'integer')
    if mode=='v3_static':
        return StaticHybrid(kind,debug)
    if mode=='v4_static':
        return StaticV4(kind,debug,capacity)
    if mode=='v3_before':
        return core.Hybrid('all55',kind,1,debug)
    if mode=='v4_before':
        return old.V4Runtime(kind,debug,capacity)
    raise ValueError('Unknown model mode: '+mode)
