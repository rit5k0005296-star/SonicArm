"""User runs run_stage in a persistent Notebook kernel; no automatic board access.
Not a full CAM++/authentication test or a measured acceleration claim.
"""
from pathlib import Path
import hashlib
import json
import platform
import sys
import time
import traceback
import numpy as np
from fcm_board import (HERE, Engine, digest, exact, load_case, software_reference,
                       temporal_chunks, save_json, verify_package)


def identity():
    manifest = verify_package()
    return dict(manifest_sha256=digest(HERE/'upload_manifest.json'), bit_sha256=digest(HERE/'fcm_v4.bit'),
                hwh_sha256=digest(HERE/'fcm_v4.hwh'), model_sha256=manifest['original_model_sha256'])


def smoke_case(long=False):
    ci, co, f, t, k, s = (1, 3, 3, 2051, 3, 1) if long else (3, 9, 7, 35, 3, 2)
    cfg = dict(cin=ci, cout=co, freq=f, frames=t, kernel=k, stride_f=s, input_zp=11,
               output_zp=-7, requant_shift=38, flags=7)
    of = (f+s-1)//s
    values = dict(input_r=((np.arange(ci*f*t, dtype=np.int64)*73+17)%256-128).astype(np.int8).reshape(ci, f, t),
                  weights=((np.arange(co*ci*k*k)*31+9)%256-128).astype(np.int8).reshape(co, ci, k, k),
                  bias=(np.arange(co, dtype=np.int32)-15)*7919,
                  multiplier=np.arange(co, dtype=np.uint32)+np.uint32(1073741824),
                  post_lut=((np.arange(65536)*17+np.arange(65536)//256)%256-128).astype(np.int8),
                  residual=((np.arange(co*of*t)*11+19)%256-128).astype(np.int8).reshape(co, of, t))
    return cfg, values


def check_result(actual, refs, debug, label):
    exact(actual['output_r'], refs['output_r'], label+' INT8')
    if debug:
        exact(actual['accumulator_out'], refs['accumulator_out'], label+' INT32')


def one(engine, cfg, values, refs, both=True):
    with engine.session(cfg, values) as session:
        out = session.call()
        check_result(out, refs, cfg['flags'] & 2, cfg.get('case', 'synthetic'))
        if both:
            no_debug = session.call(flags=cfg['flags'] & ~2)
            check_result(no_debug, refs, False, cfg.get('case', 'synthetic')+' no debug')
            exact(no_debug['output_r'], out['output_r'], 'Debug mode parity')
    return out


def check_v3(engine):
    """One known V3 real transaction using the ORIGINAL copied driver and IP."""
    import xml.etree.ElementTree as ET
    from types import SimpleNamespace
    import pointwise_v3_readonly as v3
    directory = HERE/'v3_regression'
    cfg = json.loads((directory/'config.json').read_text(encoding='utf8'))
    ci, co, t = cfg['cin'], cfg['cout'], cfg['frames']
    def arr(name, dtype, shape):
        return np.fromfile(directory/name, dtype=dtype).reshape(shape)
    values = dict(input_r=arr('input_int8.bin', 'i1', (ci, t)), weights=arr('weights_int8.bin', 'i1', (co, ci)),
                  bias=arr('bias_int32.bin', '<i4', (co,)), multiplier=arr('multiplier_uint32.bin', '<u4', (co,)),
                  post_lut=arr('post_lut_int8.bin', 'i1', (256,)))
    refs = dict(output_r=arr('reference_output_int8.bin', 'i1', (co, t)),
                accumulator_out=arr('reference_accum_int32.bin', '<i4', (co, t)))
    tree = ET.parse(HERE/'fcm_v4.hwh').getroot()
    module = next(m for m in tree.iter('MODULE') if m.get('INSTANCE') == 'pointwise_0')
    offsets = {}
    for reg in module.findall('.//REGISTERS/REGISTER'):
        prop = reg.find("./PROPERTY[@NAME='ADDRESS_OFFSET']")
        if prop is not None:
            offsets[reg.get('NAME')] = int(prop.get('VALUE'), 0)
    e = SimpleNamespace(ip=engine.overlay.pointwise_0, offsets=offsets, timeout=30.)
    e.ip.write(offsets['GIER'], 0)
    e.ip.write(offsets['IP_IER'], 0)
    try:
        with v3.Session(e, cfg, values) as s:
            s.call(values, refs, flags=2)
            s.call(values, refs, flags=0)
    except BaseException:
        engine.poisoned = True
        raise
    return dict(real_case=cfg['case'], debug_on_off_exact=True, calls=2,
                scope='One representative V3 layer regression in the V4 dual-IP bitstream; not all55 or full-model acceptance')


def run_stage(stage, run_dir):
    if stage not in ('smoke', 'correctness'):
        raise ValueError('Choose smoke or correctness')
    run_dir = Path(run_dir).resolve()
    if not run_dir.is_relative_to((HERE/'test_results').resolve()):
        raise ValueError('Results must stay in this package test_results')
    run_dir.mkdir(parents=True, exist_ok=True)
    run_id = identity()
    if stage == 'correctness':
        prev = json.loads((run_dir/'smoke.json').read_text(encoding='utf8'))
        if prev.get('identity') != run_id or prev.get('pass') is not True or prev.get('actual_hardware') is not True:
            raise RuntimeError('Matching actual hardware smoke PASS required first')
    report = dict(stage=stage, identity=run_id, actual_hardware=False, pass_pending=True,
                  platform=platform.platform(), machine=platform.machine(), python=sys.version, numpy=np.__version__,
                  scope='FCM integer hardware consistency. Not complete CAM++, accuracy acceptance or speedup.',
                  original_qdq_equivalence_claim=False, authentication_threshold_calibrated=False,
                  calls=0, cases=[])
    engine = None
    try:
        engine = Engine()
        report['actual_hardware'] = True
        report['clock_mhz'] = engine.clock
        if stage == 'smoke':
            cfg, values = smoke_case()
            refs = software_reference(values, cfg)
            one(engine, cfg, values, refs)
            report['calls'] += 2
            for name in ('audio02_isolated01', 'audio02_isolated02', 'audio02_isolated03', 'audio02_isolated04', 'audio02_isolated12'):
                cfg, values, refs = load_case(name)
                one(engine, cfg, values, refs)
                report['calls'] += 2
                report['cases'].append(name)
                print('[FCM SMOKE PASS]', name, flush=True)
            report['v3_regression'] = check_v3(engine)
            print('[V3 COEXISTENCE REGRESSION PASS] one real layer, debug on/off', flush=True)
        else:
            names = (HERE/'cases/all_cases.txt').read_text().splitlines()
            if len(names) != 48 or len(set(names)) != 48:
                raise ValueError('Expected 48 distinct real cases')
            for i, name in enumerate(names, 1):
                cfg, values, refs = load_case(name)
                one(engine, cfg, values, refs)
                report['calls'] += 2
                report['cases'].append(name)
                print('[FCM REAL PASS] %d/48 %s INT8/INT32 exact; debug on/off' % (i, name), flush=True)
            # Reconstruct with ACTUAL preceding FPGA outputs and branches.
            # Frozen chain inputs are assertions, not substitutes for those outputs.
            report['recursive_fcm'] = []
            for ai in (1, 2):
                cfg, first, _ = load_case('audio%02d_chain01' % ai)
                computed = {cfg['input_tensor']: first['input_r'].copy()}
                for li in range(1, 13):
                    name = 'audio%02d_chain%02d' % (ai, li)
                    cfg, values, refs = load_case(name)
                    x = computed[cfg['input_tensor']]
                    exact(x, values['input_r'], 'Actual preceding FPGA input '+name)
                    values['input_r'] = x
                    if cfg['skip_tensor']:
                        values['residual'] = computed[cfg['skip_tensor']]
                        exact(values['residual'], load_case(name)[1]['residual'], 'Actual FPGA shortcut '+name)
                    out = one(engine, cfg, values, refs, both=False)
                    computed[cfg['post_output_tensor']] = out['output_r']
                    report['calls'] += 1
                final = computed[cfg['post_output_tensor']]
                report['recursive_fcm'].append(dict(audio_index=ai, layers=12, exact=True,
                    output_sha256=hashlib.sha256(final.tobytes()).hexdigest()))
                print('[FCM RECURSIVE PASS] audio', ai, '12 actual successive layers', flush=True)
            cfg, values = smoke_case(long=True)
            refs = software_reference(values, cfg)
            chunks = []
            y = np.empty_like(refs['output_r'])
            a = np.empty_like(refs['accumulator_out'])
            for cc, vv, crop, count, start in temporal_chunks(cfg, values):
                with engine.session(cc, vv) as s:
                    out = s.call()
                y[..., start:start+count] = out['output_r'][..., crop:crop+count]
                a[..., start:start+count] = out['accumulator_out'][..., crop:crop+count]
                chunks.append(dict(start=start, payload=count, invocation_frames=cc['frames'], crop=crop))
                report['calls'] += 1
            exact(y, refs['output_r'], 'Temporal halo seam INT8')
            exact(a, refs['accumulator_out'], 'Temporal halo seam INT32')
            report['temporal_halo_test'] = dict(frames=2051, chunks=chunks, exact=True,
                scope='One small-channel K3 convolution seam check, not full long-record FCM validation')
            print('[FCM HALO PASS] 2051 frames, 2 actual calls, seam equals unsplit INT64 oracle', flush=True)
        report['pass'] = True
        report.pop('pass_pending', None)
        save_json(run_dir/(stage+'.json'), report)
        print('V4_FCM_'+stage.upper()+'_PASS:', run_dir/(stage+'.json'), flush=True)
        return report
    except BaseException as error:
        report['pass'] = False
        report['error'] = repr(error)
        report['traceback'] = traceback.format_exc()
        report['hardware_may_be_active'] = bool(engine and engine.poisoned)
        save_json(run_dir/(stage+'_failed.json'), report)
        print('STOP: return complete output. On IP timeout/interruption reboot board before retry; keep this kernel alive until power-off.', flush=True)
        raise
