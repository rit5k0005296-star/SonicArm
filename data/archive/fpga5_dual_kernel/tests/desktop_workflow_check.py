"""Real V5/V4 C++ kernels + native ORT behind simulated PYNQ MMIO/DDR.

Checks the shipped workflow and current-input oracles. No board, hardware
timing, FPGA cycle measurement or board acceptance is claimed by this test.
"""
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import ctypes as ct
import json
import os
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(WORKSPACE / 'test_1'))
from paths import LEGACY, COMPARE
sys.path.insert(0, str(LEGACY.parents[1] / 'consistency-test/codex'))
from common import import_runtime
import_runtime('cpu')
sys.path.insert(0, str(ROOT / 'board_package/fpga_v5'))
import numpy as np
import v5_runtime as vr
import run_v5 as workflow
from native_ort_bridge import API, Session


def main():
    sr = vr.sr
    sr.old.UNSAFE = False
    output = vr.HERE / 'results/desktop_workflow'
    reference = output / 'reference'
    reference.mkdir(parents=True, exist_ok=True)
    api = API(LEGACY / 'desktop_validation/ort_audit/windows1171/onnxruntime-win-x64-1.17.1/lib/onnxruntime.dll', verify=False)
    factory = lambda path, threads=1, optimize=False: Session(path, threads, optimize, api=api)
    protocol, items, features = sr.bench.data()
    features = {n: np.ascontiguousarray(x[:, :t, :]) for (n, x), t in zip(features.items(), (43, 47, 53))}
    for name in features:
        items[name] = dict(items[name], frames=features[name].shape[1], duration_seconds=features[name].shape[1]/100)
    execution = sr.execution
    for mode in ('cpu_fp32', 'cpu_int8', 'v4_static'):
        with execution(True, factory=factory):
            model = sr.make(mode, 53, hardware=False)
            try:
                for name, x in features.items():
                    np.save(reference / (mode+'.'+name+'.npy'), model.run(x)[0], allow_pickle=False)
            finally:
                sr.bench.close(model)
    dll_search = os.add_dll_directory('D:/msys64/ucrt64/bin') if hasattr(os, 'add_dll_directory') else None
    p8, pi, pu = ct.POINTER(ct.c_int8), ct.POINTER(ct.c_int32), ct.POINTER(ct.c_uint32)
    v5lib = ct.CDLL(str(ROOT / 'tests/v5_native.dll'))
    pw5, fcm5 = v5lib.call_pw5, v5lib.call_fcm5
    pw4 = ct.CDLL(str(COMPARE / 'diagnostics/pointwise_native.dll')).pointwise
    fcm4 = ct.CDLL(str(LEGACY.parents[1] / 'FPGA-4/fcm_engine/diagnostics/fcm_native.dll')).fcm
    for fn in (pw5, pw4):
        fn.argtypes = [p8, p8, pi, pu, p8, p8, pi] + [ct.c_int]*7
        fn.restype = ct.c_int
    for fn in (fcm5, fcm4):
        fn.argtypes = [p8, p8, pi, pu, p8, p8, p8, pi] + [ct.c_int]*10
        fn.restype = ct.c_int
    hwh5 = ROOT / 'deploy/cam_v5.hwh'
    if not hwh5.exists():
        hwh5 = ROOT / 'vivado/v5/v5.gen/sources_1/bd/system/hw_handoff/system.hwh'
    xml5, xml4 = ET.parse(hwh5).getroot(), ET.parse(sr.old.HW / 'fcm_v4.hwh').getroot()
    def offsets(tree, instance):
        m = next(m for m in tree.iter('MODULE') if m.get('INSTANCE') == instance)
        return {r.get('NAME'): int(r.find("./PROPERTY[@NAME='ADDRESS_OFFSET']").get('VALUE'), 0)
                for r in m.findall('.//REGISTERS/REGISTER') if r.find("./PROPERTY[@NAME='ADDRESS_OFFSET']") is not None}
    for instance, top, pointers, scalars in [('pointwise_0', 'pointwise_v5', vr.pc.POINTERS, vr.pc.SCALARS),
                                           ('fcm_0', 'fcm_v5', sr.old.fcm.POINTERS, sr.old.fcm.SCALARS)]:
        assert vr.register_map(xml5, instance, 'xilinx.com:hls:'+top+':1.0', pointers, scalars) == offsets(xml5, instance)
    allocated, address = {}, [0x08000000]
    native_calls = {'v4_pw': 0, 'v4_fcm': 0, 'v5_pw': 0, 'v5_fcm': 0}
    class Buffer(np.ndarray):
        def __new__(cls, shape, dtype):
            a = np.zeros(shape, dtype).view(cls)
            a.physical_address = address[0]
            address[0] += ((a.nbytes+4095)//4096+1)*4096
            if address[0] > 0x20000000:
                raise AssertionError('Simulated DDR overflow')
            allocated[a.physical_address] = a
            return a
        def __array_finalize__(self, other):
            self.physical_address = getattr(other, 'physical_address', None)
        def flush(self): pass
        def invalidate(self): pass
        def freebuffer(self): allocated.pop(self.physical_address, None)
    class Monitor:
        def __init__(self): self.values = {}; self.armed = False
        def write(self, off, value):
            if off == 0:
                self.armed = bool(value)
                self.values = {}
        def read(self, off): return self.values.get(off, 0)
        def complete(self, selected):
            if self.armed:
                # Deliberately artificial counter values; never a speed claim.
                self.values = {4: 4 | selected << 8, 8: 1000, 16: 10, 24: 5}
                self.armed = False
    class MMIO:
        def __init__(self, owner, selected, label, fn, pointers, scalars, off):
            self.owner, self.selected, self.label, self.fn = owner, selected, label, fn
            self.pointers, self.scalars, self.off, self.reg, self.done = pointers, scalars, off, {}, False
        def read(self, off):
            return (6 if self.done else 4) if off == self.off['CTRL'] else self.reg.get(off, 0)
        def write(self, off, value):
            if off == self.off['IP_ISR']:
                self.reg[off] = self.reg.get(off, 0) ^ value
                return
            self.reg[off] = value
            if off != self.off['CTRL'] or value != 1:
                return
            self.done = False
            arrays = [allocated[self.reg[self.off[n+'_1']] | self.reg[self.off[n+'_2']] << 32] for n in self.pointers]
            args = [v.ctypes.data_as(t) for v, t in zip(arrays, self.fn.argtypes[:len(arrays)])]
            scalar = [ct.c_int32(self.reg[self.off[n]]).value for n in self.scalars]
            code = self.fn(*args, *scalar)
            if code:
                raise AssertionError('Native kernel status '+str(code))
            self.reg[self.off['ap_return']] = code
            self.reg[self.off['IP_ISR']] = 1
            self.done = True
            native_calls[self.label] += 1
            self.owner.monitor.complete(self.selected)
    class NativeEngine(vr.Engine):
        def __init__(self, measuring=False, old=False):
            if allocated:
                raise AssertionError('CMA leak before new runtime')
            address[0] = 0x08000000
            self.measuring, self.poisoned, self.clock = measuring, False, 100.
            self.records, self.calls, self.monitor = [], {1: 0, 2: 0}, Monitor()
            tree = xml4 if old else xml5
            po, fo = offsets(tree, 'pointwise_0'), offsets(tree, 'fcm_0')
            pw = MMIO(self, 1, 'v4_pw' if old else 'v5_pw', pw4 if old else pw5, vr.pc.POINTERS, vr.pc.SCALARS, po)
            fcm = MMIO(self, 2, 'v4_fcm' if old else 'v5_fcm', fcm4 if old else fcm5, sr.old.fcm.POINTERS, sr.old.fcm.SCALARS, fo)
            self.pw = SimpleNamespace(ip=pw if old else vr.MeasuredIP(self, pw, po, 1), offsets=po, timeout=30.)
            self.fcm = SimpleNamespace(ip=fcm if old else vr.MeasuredIP(self, fcm, fo, 2), offsets=fo, timeout=30., poisoned=False)
            self.overlay = SimpleNamespace(pointwise_0=pw)
    @contextmanager
    def desktop_execution(optimize=True, collector=None, factory=None):
        with execution(optimize, collector, factory or native_factory) as value:
            yield value
    native_factory = factory
    @contextmanager
    def desktop_stage(*args, **kwargs): yield
    old_engine, old_fcm, old_platform = vr.Engine, sr.old.fcm.Engine, vr.pc.platform
    old_data, old_execution, old_stage = sr.bench.data, sr.execution, workflow.prior.stage
    original_check, original_save = workflow.check, workflow.save
    original_digest = vr.digest
    original_pynq = sys.modules.get('pynq')
    setup = dict(include_fp32=True, modes=list(workflow.MODES), strict_original_QDQ_gate={'v4_static': False},
                 strict_optimized_INT8_gate={'v4_static': False}, scope='desktop regression', excluded=[])
    def desktop_save(path, value):
        if isinstance(value, dict) and 'actual_hardware' in value:
            value = dict(value, actual_hardware=False, desktop_MMIO_simulation=True)
        original_save(path, value)
    try:
        vr.digest = lambda p: ('desktop_fixture_pending_bitstream' if Path(p) == vr.HERE/'manifest.json' and not Path(p).exists() else original_digest(p))
        sys.modules['pynq'] = SimpleNamespace(allocate=lambda shape, dtype: Buffer(shape, dtype))
        vr.pc.platform = SimpleNamespace(system=lambda: 'Linux', machine=lambda: 'armv7l')
        vr.Engine = NativeEngine
        def old_engine_factory(timeout=30.):
            e = NativeEngine(old=True)
            return SimpleNamespace(ip=e.fcm.ip, offsets=e.fcm.offsets, timeout=timeout,
                                   poisoned=False, overlay=e.overlay, clock=100.)
        sr.old.fcm.Engine = old_engine_factory
        sr.execution = desktop_execution
        sr.bench.data = lambda: (protocol, items, features)
        workflow.prior.stage = desktop_stage
        workflow.check = lambda run, hardware=False: (output, reference, setup)
        workflow.save = desktop_save
        original_save(output / 'setup.json', setup)
        workflow.correctness(output)
        assert not allocated
        workflow.profile(output, repeats=1, warmup=1)
        assert not allocated
        workflow.benchmark(output, repeats=2, warmup=1)
        assert not allocated
        report = json.loads((output / 'hardware_correctness.json').read_text())
        perf = json.loads((output / 'performance.json').read_text())
        assert report['integer_exact'] and report['debug_on_off_exact'] and not report['actual_hardware']
        assert len(perf['summary']) == 8 and all(r['n'] == 2 for r in perf['summary']) and not perf['actual_hardware']
        _, _, full_features = old_data()
        capacity = max(x.shape[1] for x in full_features.values())
        full_gold = {}
        with desktop_execution(True):
            model = sr.make('v4_static', capacity, hardware=False)
            try:
                full_gold = {name: model.run(x)[0] for name, x in full_features.items()}
            finally:
                sr.bench.close(model)
        with desktop_execution(True):
            model = vr.Runtime(debug=True, capacity=capacity)
            try:
                for name, x in full_features.items():
                    raw, detail = model.run(x, audit=True)
                    assert np.array_equal(raw, full_gold[name])
                    assert len(detail['layers']) == 67 and all(r['integer_exact'] for r in detail['layers'])
                    print('V5_DESKTOP_FULL_RECORDING_PASS', name, x.shape, flush=True)
            finally:
                sr.bench.close(model)
        assert not allocated
        validation = dict(pass_=True, actual_hardware=False,
            native_calls=native_calls, lengths=[43, 47, 53], all_67_layers=True, debug_on_off=True,
            fcm_halo_2051=True, packed_tails=True, cma_leak=False,
            full_recordings={n:list(x.shape) for n,x in full_features.items()},
            note='C++ kernels/native ORT + simulated MMIO/CMA. Counter values artificial. No board timing/acceptance.')
        (ROOT / 'reports/desktop_workflow_validation.json').write_text(json.dumps(validation, indent=2), encoding='utf8')
        print('V5_DESKTOP_WORKFLOW_PASS', native_calls, flush=True)
    finally:
        vr.Engine, sr.old.fcm.Engine, vr.pc.platform = old_engine, old_fcm, old_platform
        sr.bench.data, sr.execution, workflow.prior.stage = old_data, old_execution, old_stage
        workflow.check, workflow.save = original_check, original_save
        vr.digest = original_digest
        if original_pynq is None: sys.modules.pop('pynq', None)
        else: sys.modules['pynq'] = original_pynq


if __name__ == '__main__':
    main()
