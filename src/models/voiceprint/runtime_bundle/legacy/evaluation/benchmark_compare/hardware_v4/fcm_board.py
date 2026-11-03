"""V4 FCM references and manual PYNQ-Z2 driver. Import has no hardware effects."""
from pathlib import Path
import hashlib
import json
import platform
import time
import xml.etree.ElementTree as ET
import numpy as np

HERE = Path(__file__).resolve().parent
POINTERS = ('input_r', 'weights', 'bias', 'multiplier', 'post_lut', 'residual', 'output_r', 'accumulator_out')
SCALARS = ('cin', 'cout', 'freq', 'frames', 'kernel', 'stride_f', 'input_zp', 'output_zp', 'requant_shift', 'flags')
RETAINED_BUFFERS = []
GUARD = 16
DEBUG_SENTINEL = 0x5a5a5a5a


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def exact(a, b, label):
    a, b = np.asarray(a), np.asarray(b)
    if a.shape != b.shape or a.dtype != b.dtype:
        raise AssertionError(label+' shape/dtype mismatch')
    indices = np.flatnonzero(a.ravel() != b.ravel())
    if indices.size:
        k = int(indices[0])
        raise AssertionError('%s: %d differences, first %d (%s vs %s)' % (label, indices.size, k, a.ravel()[k], b.ravel()[k]))


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf8')


def checked_config(cfg, allow_long=False):
    if any(type(cfg.get(k)) is not int for k in SCALARS):
        raise ValueError('Integer scalar config required')
    if not (1 <= cfg['cin'] <= 32 and 1 <= cfg['cout'] <= 32 and 1 <= cfg['freq'] <= 80 and
            1 <= cfg['frames'] and (allow_long or cfg['frames'] <= 2048) and cfg['kernel'] in (1, 3) and cfg['stride_f'] in (1, 2)):
        raise ValueError('Unsupported FCM shape')
    if not (-128 <= cfg['input_zp'] <= 127 and -128 <= cfg['output_zp'] <= 127 and
            8 <= cfg['requant_shift'] <= 40 and 0 <= cfg['flags'] <= 7):
        raise ValueError('Unsupported quantization/flags')
    if cfg['flags'] & 4 and not cfg['flags'] & 1:
        raise ValueError('Residual requires LUT')


def bounds(inputs, cfg):
    delta = max(abs(-128-cfg['input_zp']), abs(127-cfg['input_zp']))
    bound = np.abs(inputs['weights'].astype(np.int64)).sum((1, 2, 3))*delta+np.abs(inputs['bias'].astype(np.int64))
    if np.any(bound > 2147483647):
        raise ValueError('INT32 partial-sum bound failed')


def checked_inputs(inputs, cfg):
    ci, co, f, t, k = (cfg[x] for x in ('cin', 'cout', 'freq', 'frames', 'kernel'))
    of = (f+cfg['stride_f']-1)//cfg['stride_f']
    shapes = dict(input_r=((ci, f, t), 'i1'), weights=((co, ci, k, k), 'i1'), bias=((co,), '<i4'),
                  multiplier=((co,), '<u4'), post_lut=((65536 if cfg['flags'] & 4 else 256,), 'i1'),
                  residual=((co, of, t), 'i1'))
    if set(inputs) != set(shapes):
        raise ValueError('Unexpected input buffers')
    for name, (shape, dtype) in shapes.items():
        if inputs[name].shape != shape or inputs[name].dtype != np.dtype(dtype):
            raise ValueError('Wrong input shape/dtype: '+name)
    bounds(inputs, cfg)


def requantize(acc, inputs, cfg):
    p = acc.astype(np.int64)*inputs['multiplier'].astype(np.int64)[:, None, None]
    mag = np.abs(p)
    shift = cfg['requant_shift']
    whole = mag >> shift
    rem = mag & ((1 << shift)-1)
    whole += (rem > (1 << (shift-1))) | ((rem == (1 << (shift-1))) & ((whole & 1) != 0))
    q = np.clip(np.where(p < 0, -whole, whole)+cfg['output_zp'], -128, 127).astype(np.int8)
    if cfg['flags'] & 1:
        index = q.astype(np.int32)+128
        if cfg['flags'] & 4:
            index = index*256+inputs['residual'].astype(np.int32)+128
        q = inputs['post_lut'][index]
    return q


def software_reference(inputs, cfg):
    """INT64-only oracle for small smoke/halo cases; full real cases have frozen hashes."""
    checked_config(cfg, allow_long=True)
    bounds(inputs, cfg)
    c, f, t, k = cfg['cin'], cfg['freq'], cfg['frames'], cfg['kernel']
    of = (f+cfg['stride_f']-1)//cfg['stride_f']
    xc = np.pad(inputs['input_r'].astype(np.int64)-cfg['input_zp'], ((0, 0), (k//2, k//2), (k//2, k//2)))
    acc = np.broadcast_to(inputs['bias'].astype(np.int64)[:, None, None], (cfg['cout'], of, t)).copy()
    for ci in range(c):
        for kf in range(k):
            for kt in range(k):
                patch = xc[ci, kf:kf+of*cfg['stride_f']:cfg['stride_f'], kt:kt+t]
                acc += inputs['weights'][:, ci, kf, kt].astype(np.int64)[:, None, None]*patch
    return dict(output_r=requantize(acc, inputs, cfg), accumulator_out=acc.astype(np.int32))


def verify_package():
    manifest = json.loads((HERE/'upload_manifest.json').read_text(encoding='utf8'))
    for name, expected in manifest['files'].items():
        path = (HERE/name).resolve()
        if not path.is_relative_to(HERE.resolve()):
            raise ValueError('Unsafe manifest path')
        # Notebook output/metadata may change after user execution; code must not.
        if path.suffix == '.ipynb':
            code = [''.join(c['source']) for c in json.loads(path.read_text(encoding='utf8'))['cells'] if c['cell_type'] == 'code']
            actual = hashlib.sha256(json.dumps(code, ensure_ascii=False).encode('utf8')).hexdigest()
        else:
            actual = digest(path)
        if actual != expected:
            raise ValueError('Package hash failed: '+name)
    return manifest


def load_case(name):
    directory = (HERE/'cases'/name).resolve()
    if directory.parent != (HERE/'cases').resolve():
        raise ValueError('Unsafe case name')
    cfg = json.loads((directory/'config.json').read_text(encoding='utf8'))
    checked_config(cfg)
    report = json.loads((HERE/'reference_report.json').read_text(encoding='utf8'))
    item = next((x for x in report['cases'] if x['case'] == name), None)
    if item != cfg:
        raise ValueError('Case configuration differs from verified reference report')
    for file, expected in cfg['files_sha256'].items():
        path = (directory/file).resolve()
        if path.parent != directory or digest(path) != expected:
            raise ValueError('Case hash failed: '+file)
    ci, co, f, t, k = (cfg[x] for x in ('cin', 'cout', 'freq', 'frames', 'kernel'))
    of = (f+cfg['stride_f']-1)//cfg['stride_f']
    def array(file, dtype, shape):
        path = directory/file
        if path.stat().st_size != int(np.prod(shape))*np.dtype(dtype).itemsize:
            raise ValueError('Wrong binary size: '+file)
        return np.fromfile(path, dtype=dtype).reshape(shape)
    values = dict(input_r=array('input_int8.bin', 'i1', (ci, f, t)), weights=array('weights_int8.bin', 'i1', (co, ci, k, k)),
                  bias=array('bias_int32.bin', '<i4', (co,)), multiplier=array('multiplier_uint32.bin', '<u4', (co,)),
                  post_lut=array('post_lut_int8.bin', 'i1', (65536 if cfg['flags'] & 4 else 256,)),
                  residual=array('residual_int8.bin', 'i1', (co, of, t)))
    refs = dict(output_r=array('reference_output_int8.bin', 'i1', (co, of, t)),
                accumulator_out=array('reference_accum_int32.bin', '<i4', (co, of, t)))
    bounds(values, cfg)
    exact(requantize(refs['accumulator_out'], values, cfg), refs['output_r'], 'Stored integer Q reference')
    return cfg, values, refs


def offsets_from_hwh():
    tree = ET.parse(HERE/'fcm_v4.hwh').getroot()
    module = next((m for m in tree.iter('MODULE') if m.get('INSTANCE') == 'fcm_0'), None)
    pw = next((m for m in tree.iter('MODULE') if m.get('INSTANCE') == 'pointwise_0'), None)
    if module is None or module.get('VLNV') != 'xilinx.com:hls:fcm:1.0' or pw is None or pw.get('VLNV') != 'xilinx.com:hls:pointwise:1.0':
        raise ValueError('Expected V4 dual-IP HWH')
    offsets = {}
    for reg in module.findall('.//REGISTERS/REGISTER'):
        prop = reg.find("./PROPERTY[@NAME='ADDRESS_OFFSET']")
        if prop is not None:
            offsets[reg.get('NAME')] = int(prop.get('VALUE'), 0)
    required = ['CTRL', 'GIER', 'IP_IER', 'ap_return']+list(SCALARS)
    for name in POINTERS:
        required += [name+'_1', name+'_2']
    if any(k not in offsets for k in required):
        raise ValueError('Incomplete V4 HWH register map')
    ps = next(m for m in tree.iter('MODULE') if m.get('INSTANCE') == 'processing_system7_0')
    params = {p.get('NAME'): p.get('VALUE') for p in ps.iter('PARAMETER')}
    if abs(float(params['PCW_FPGA0_PERIPHERAL_FREQMHZ'])-100) > .01 or params['PCW_USE_M_AXI_GP0'] != '1' or params['PCW_USE_S_AXI_HP0'] != '1':
        raise ValueError('Unexpected PS7 AXI or clock config')
    return offsets


class Engine:
    def __init__(self, timeout=30.):
        if platform.system() != 'Linux' or platform.machine().lower() not in ('armv7l', 'armv8l'):
            raise RuntimeError('Manual PYNQ-Z2 ARM Linux execution required')
        from pynq import Overlay, Clocks
        verify_package()
        self.offsets = offsets_from_hwh()
        self.timeout = timeout
        self.poisoned = False
        self.overlay = Overlay(str(HERE/'fcm_v4.bit'))
        self.ip = self.overlay.fcm_0
        self.clock = float(Clocks.fclk0_mhz)
        if abs(self.clock-100) > .5:
            raise RuntimeError('Clock is not 100 MHz')
        self.ip.write(self.offsets['GIER'], 0)
        self.ip.write(self.offsets['IP_IER'], 0)

    def session(self, cfg, inputs):
        if self.poisoned:
            raise RuntimeError('Previous timeout; reboot board before retrying')
        return Session(self, cfg, inputs)


class Session:
    def __init__(self, engine, cfg, inputs):
        from pynq import allocate
        checked_config(cfg)
        checked_inputs(inputs, cfg)
        self.engine, self.cfg = engine, dict(cfg)
        self.buffers, self.shapes = {}, {}
        self.safe = True
        of = (cfg['freq']+cfg['stride_f']-1)//cfg['stride_f']
        values = dict(inputs)
        values['output_r'] = np.zeros((cfg['cout'], of, cfg['frames']), np.int8)
        values['accumulator_out'] = np.zeros(values['output_r'].shape, np.int32)
        try:
            for name in POINTERS:
                value = np.ascontiguousarray(values[name])
                self.shapes[name] = value.shape
                buf = allocate(shape=(value.size+GUARD,), dtype=value.dtype)
                self.buffers[name] = buf
                address = int(buf.physical_address)
                if address < 0 or address+buf.nbytes > 0x20000000:
                    raise ValueError('Buffer outside mapped 512 MiB DDR')
                self.view(name)[:] = value
                buf[value.size:] = self.sentinel(name)
                buf.flush()
        except Exception:
            self.close()
            raise

    def sentinel(self, name):
        return DEBUG_SENTINEL if name == 'accumulator_out' else 85

    def view(self, name):
        return self.buffers[name][:int(np.prod(self.shapes[name]))].reshape(self.shapes[name])

    def call(self, flags=None):
        if self.engine.poisoned:
            raise RuntimeError('Previous timeout; reboot board')
        cfg = dict(self.cfg)
        if flags is not None:
            cfg['flags'] = flags
        checked_config(cfg)
        if (cfg['flags'] & 5) != (self.cfg['flags'] & 5):
            raise ValueError('Cannot change LUT/residual mode for allocated buffers')
        for name in ('output_r', 'accumulator_out'):
            self.buffers[name].fill(self.sentinel(name))
            self.buffers[name].flush()
        ip, off = self.engine.ip, self.engine.offsets
        if not ip.read(off['CTRL']) & 4:
            raise RuntimeError('FCM IP is busy before launch')
        # Rebind every pointer and scalar: never rely on a preceding layer's state.
        for name in POINTERS:
            address = int(self.buffers[name].physical_address)
            ip.write(off[name+'_1'], address & 0xffffffff)
            ip.write(off[name+'_2'], address >> 32)
        for name in SCALARS:
            ip.write(off[name], cfg[name] & 0xffffffff)
        start = time.perf_counter()
        self.safe = False
        try:
            ip.write(off['CTRL'], 1)
            while not ip.read(off['CTRL']) & 2:
                if time.perf_counter()-start > self.engine.timeout:
                    raise TimeoutError('FCM timeout; buffers retained. Reboot board before retrying.')
        except BaseException:
            self.engine.poisoned = True
            raise
        self.safe = True
        elapsed = (time.perf_counter()-start)*1000
        rc = ip.read(off['ap_return'])
        if rc != 0:
            raise RuntimeError('FCM return code '+str(rc))
        for name, buf in self.buffers.items():
            buf.invalidate()
            if np.any(buf[int(np.prod(self.shapes[name])):] != self.sentinel(name)):
                raise AssertionError('Guard overwritten: '+name)
        if not cfg['flags'] & 2 and np.any(self.view('accumulator_out') != DEBUG_SENTINEL):
            raise AssertionError('Debug disabled but accumulator changed')
        return dict(output_r=np.array(self.view('output_r'), copy=True),
                    accumulator_out=np.array(self.view('accumulator_out'), copy=True) if cfg['flags'] & 2 else None,
                    kernel_call_ms=elapsed, pointer_pairs_bound=8)

    def close(self):
        if self.safe:
            for buf in self.buffers.values():
                buf.freebuffer()
        else:
            RETAINED_BUFFERS.extend(self.buffers.values())
        self.buffers = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def temporal_chunks(cfg, inputs):
    """Invocation windows with real 1-frame halos for K3, no synthetic seam pad.
    Core length <=2048, crop is in output-time coordinates (time stride is 1).
    """
    checked_config(cfg, allow_long=True)
    total = cfg['frames']
    halo = cfg['kernel']//2
    payload = 2048-2*halo
    for start in range(0, total, payload):
        stop = min(start+payload, total)
        lo, hi = max(0, start-halo), min(total, stop+halo)
        cc = dict(cfg, frames=hi-lo)
        vv = dict(inputs, input_r=np.ascontiguousarray(inputs['input_r'][..., lo:hi]),
                  residual=np.ascontiguousarray(inputs['residual'][..., lo:hi]))
        yield cc, vv, start-lo, stop-start, start
