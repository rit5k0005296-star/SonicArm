"""Read local tool evidence; never promote desktop checks to board proof."""
from pathlib import Path
import hashlib
import json
import runpy
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    pins = json.loads((ROOT / 'reports/baseline_pins.json').read_text())
    for name, expected in pins.items():
        if name.startswith('v3/'):
            path = ROOT.parent / 'FPGA-3/pointwise_engine' / name[3:]
        elif name.startswith('v4/'):
            path = ROOT.parent / 'FPGA-4/fcm_engine' / name[3:]
        else:
            path = ROOT / name
        if sha(path) != expected:
            raise ValueError('Pinned baseline/reference changed: ' + name)
    kernels = {}
    for name, top, loop, count in [('pw', 'pointwise_v5', 'mac_channels', 110), ('fcm', 'fcm_v5', 'mac_kernel', 48)]:
        log = (ROOT / ('logs/hls_'+name+'_cosim.log')).read_text(errors='replace')
        if 'C/RTL co-simulation finished: PASS' not in log:
            raise ValueError('RTL cosim incomplete: '+name)
        csim = (ROOT / ('logs/hls_'+name+'_csim.log')).read_text(errors='replace')
        if '0 errors' not in csim:
            raise ValueError('C simulation incomplete: '+name)
        count_marker = ('pointwise '+str(count)+' real cases') if name=='pw' else ('FCM_TEST_PASS real_cases='+str(count)+' mode=FULL_C')
        if count_marker not in csim:
            raise ValueError('C simulation real-case count differs: '+name)
        report = ET.parse(ROOT / ('hls/'+name+'/hls/syn/report/'+top+'_csynth.xml')).getroot()
        mac = ET.parse(ROOT / ('hls/'+name+'/hls/syn/report/compute_Pipeline_'+loop+'_csynth.xml')).getroot()
        ii = mac.findtext('.//SummaryOfLoopLatency/'+loop+'/PipelineII')
        if ii != '1':
            raise ValueError('MAC loop II changed: '+name)
        if name == 'fcm':
            synth = (ROOT / 'logs/hls_fcm_synth.log').read_text(errors='replace')
            if 'detected/extracted 3 process function(s)' not in synth:
                raise ValueError('FCM dataflow was serialized again')
        kernels[name] = dict(csim_real_cases=count, rtl_cosim_pass=True, mac_loop_ii=int(ii),
            hls_estimates={r.tag:int(r.text) for r in report.findall('.//AreaEstimates/Resources/*')},
            ip_component_sha256=sha(ROOT / ('hls/'+name+'/hls/impl/ip/component.xml')))
    independent = (ROOT / 'logs/fcm_independent_rtl.log').read_text(errors='replace')
    monitor = (ROOT / 'logs/monitor_sim.log').read_text(errors='replace')
    wrapper = (ROOT / 'logs/monitor_wrapper_sim.log').read_text(errors='replace')
    if 'V5_FCM_INDEPENDENT_RTL_PASS' not in independent or 'V5_MONITOR_RTL_PASS' not in monitor:
        raise ValueError('Independent RTL/monitor proof missing')
    if 'V5_MONITOR_WRAPPER_RTL_PASS' not in wrapper:
        raise ValueError('Passive monitor wrapper RTL proof missing')
    packed = (ROOT / 'logs/packed_bytes.log').read_text(errors='replace')
    if 'V5_PACKED_BYTE_MASK_PASS 1152' not in packed:
        raise ValueError('Packed byte-mask/guard regression incomplete')
    mutation = json.loads((ROOT / 'reports/packed_mutation.json').read_text())
    if not mutation.get('pass_') or mutation['source_sha256'] != sha(ROOT / 'src/packed.h'):
        raise ValueError('Current packed-byte checker negative control required')
    runpy.run_path(str(ROOT/'tests/check_bus_connectivity.py'),run_name='__main__')
    runpy.run_path(str(ROOT/'tests/check_ip_sources.py'),run_name='__main__')
    bus = json.loads((ROOT/'reports/bus_connectivity.json').read_text())
    ip_sources = json.loads((ROOT/'reports/ip_source_audit.json').read_text())
    desktop = json.loads((ROOT / 'reports/desktop_workflow_validation.json').read_text())
    if not desktop.get('pass_') or desktop.get('actual_hardware') or len(desktop.get('full_recordings',{})) != 3:
        raise ValueError('Full-recording desktop regression incomplete')
    value = dict(actual_hardware=False, baseline_files_verified=len(pins), kernels=kernels,
        independent_fcm_rtl_cases=8, packed_fragment_guard_cases=1152, packed_mutation_rejected=True,
        counter_rtl_pass=True, monitor_wrapper_rtl_pass=True,
        connected_axi_signal_triples=bus['signals'], desktop_workflow=desktop,
        matched_ip_hdl_files=ip_sources['matched_ip_hdl_files'],
        rtl_source_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in sorted((ROOT/'rtl').glob('*.v'))},
        source_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in sorted((ROOT/'src').glob('*')) if p.is_file()},
        note='HLS estimates are not routed resources. No V5 board speedup or accuracy acceptance claimed.')
    (ROOT / 'reports/local_validation.json').write_text(json.dumps(value, indent=2)+'\n', encoding='utf8')
    print('V5_LOCAL_VALIDATION_PASS', len(pins), 'baseline/reference files unchanged')


if __name__ == '__main__':
    main()
