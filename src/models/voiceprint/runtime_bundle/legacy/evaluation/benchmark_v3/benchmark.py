"""Manual V3 model-latency diagnostic. Quality drift is retained, not accepted.
Frozen full-recording Fbank -> complete model -> L2 -> enrolled cosine score.
One runtime is resident at a time; two measurement blocks reverse mode order.
"""
from pathlib import Path
import argparse
import gc
import json
import platform
import sys
import time
import uuid
sys.dont_write_bytecode = True
WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import runtime_core as core
import compatible_all55 as all55
from compatible_one_layer import route
from all55_fast_diagnostic import reference_and_progress, self_check, validate as validate_reference
from native_ort_bridge import backend_details


def validate():
    core.verify_manifest(); all55.validate(); validate_reference()
    manifest = json.loads((WORK/'manifest.json').read_text(encoding='utf-8'))
    for name, expected in manifest['files'].items():
        path = (WORK/name).resolve()
        if not path.is_relative_to(WORK):
            raise ValueError('Benchmark path escapes folder')
        if path.suffix == '.ipynb':
            if core.notebook_sources(path) != manifest['notebook_cells'][name]:
                raise ValueError('Benchmark notebook code changed')
        elif core.digest(path) != expected:
            raise ValueError('Benchmark source changed: '+name)


def prior_hardware(backend):
    matches = []
    for path in (ROOT/'test_results').glob('compatible_all55_fast_*/fpga/correctness.json'):
        row = json.loads(path.read_text(encoding='utf-8'))
        if (row.get('diagnostic_completed') and row.get('hardware_consistency_gate') is True
                and row.get('diagnostic_manifest') == core.digest(all55.ASSETS/'manifest.json')
                and row.get('exact_reference_manifest') == core.digest(ROOT/'all55_fast_manifest.json')
                and row.get('native_backend') == backend):
            matches.append((path, row))
    if not matches:
        raise ValueError('Matching actual 03b all55 hardware report required')
    return sorted(matches, key=lambda v: v[0].stat().st_mtime)[-1]


def snapshot():
    result = {}
    for name, path in {
        'meminfo': '/proc/meminfo',
        'governor': '/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor',
        'cpu_frequency': '/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq',
        'temperature': '/sys/class/thermal/thermal_zone0/temp',
    }.items():
        try:
            result[name] = Path(path).read_text().strip()
        except OSError:
            result[name] = None
    return result


def invoke(runtime, features, registry):
    start = time.perf_counter()
    raw, detail = runtime.run(features, audit=False)
    model_end = time.perf_counter()
    vector = core.normalize(raw)
    score = float(registry @ vector)
    end = time.perf_counter()
    row = {'model_ms': (model_end-start)*1000, 'model_l2_score_ms': (end-start)*1000,
           'l2_score_ms': (end-model_end)*1000,
           'CPU_remaining_ms': detail['cpu_remaining_ms'],
           'layer_callback_ms': detail.get('layer_callback_ms', 0.),
           'score': score}
    for key in ('parameter_address_size_switch_ms','input_ddr_copy_flush_ms','fpga_start_done_ms',
                'output_invalidate_copy_ms','output_concat_ms','layout_ms'):
        row[key] = sum(layer.get(key,0.) for layer in detail['layers'])
    return raw, row


def run(directory, repeats=20, warmup=3, session_factory=None, backend=None):
    if repeats < 4 or repeats % 2 or warmup < 1:
        raise ValueError('Use even repeats>=4, warmup>=1; standard run is 20/3')
    directory = Path(directory).resolve()
    if not directory.is_relative_to(WORK/'results'):
        raise ValueError('Output must stay in benchmark_v3/results')
    directory.mkdir(parents=True, exist_ok=True)
    validate(); backend = backend or backend_details()
    prerequisite_path, prerequisite = prior_hardware(backend)
    protocol = json.loads((core.BUNDLE/'smoke_protocol.json').read_text())
    items = {v['id']:v for v in protocol['audio']}
    enrolled = protocol['enroll']['speaker1']
    queries = [v['audio'] for v in protocol['trials']]
    features = {name:np.load(core.BUNDLE/items[name]['features'],allow_pickle=False)
                for name in dict.fromkeys([enrolled,*queries])}
    modes = ('cpu_reference','cpu_optimized','fpga')
    samples = []; initializations = []; references = {}; quality = []; registry_vectors = {}
    info = {'scope':'frozen Fbank -> complete model -> L2 -> enrolled cosine',
        'excluded':'audio read/decode/Fbank/acquisition; model/Overlay/parameter initialization; audit; file writes',
        'timing_clock':'perf_counter', 'repeats_per_mode_query':repeats,
        'blocks':2,'warmup_per_block_query':warmup,'threads':1,'backend':backend,
        'CPU_policy':{'cpu_reference':'ORT_DISABLE_ALL','cpu_optimized':'ORT_ENABLE_ALL'},
        'resident_policy':'one complete runtime at a time; resident FPGA parameters and scratch; address writes and input/output transfers included in model latency',
        'accuracy_matched_speedup_claim':False,'model_acceptance':False,
        'prior_QDQ_drift_gate':prerequisite['QDQ_drift_gate'],
        'hardware_report':{'file':str(prerequisite_path),'sha256':core.digest(prerequisite_path)},
        'compatible_models_sha256':core.digest(all55.ASSETS/'manifest.json'),
        'bit_sha256':core.digest(core.BUNDLE/'support/pointwise.bit'),
        'hwh_sha256':core.digest(core.BUNDLE/'support/pointwise.hwh'),
        'features':{n:core.digest(core.BUNDLE/items[n]['features']) for n in features},
        'note':'Engineering latency comparison with known numerical drift; not an equal-accuracy claim. Native library already loaded for verification before session initialization timing.'}
    core.save(directory/'run_info.json',info)
    mapping = all55.validate()
    with route(mapping, session_factory), reference_and_progress() as original_reference:
        core.save(directory/'reference_check.json',{'checks':self_check(original_reference)})
        for block in range(2):
            order = modes if block==0 else tuple(reversed(modes))
            for mode in order:
                print('[BENCH]',block+1,'/2',mode,'INITIALIZE',flush=True)
                before = snapshot(); start = time.perf_counter()
                runtime = core.Hybrid('all55','fpga',1,False) if mode=='fpga' else core.FullCPU(1,mode=='cpu_optimized')
                initialization = (time.perf_counter()-start)*1000
                try:
                    registered, _ = runtime.run(features[enrolled], audit=mode=='fpga' and block==0)
                    registry = core.normalize(registered)
                    if mode not in registry_vectors:
                        registry_vectors[mode]=registry.copy()
                    elif not np.array_equal(registry_vectors[mode],registry):
                        raise AssertionError('Registration changed between measurement blocks')
                    for name in queries:
                        # Untimed validation; FPGA checks current INT8/INT32 and guards once.
                        expected, _ = runtime.run(features[name], audit=mode=='fpga' and block==0)
                        prior = references.setdefault(mode,{}).setdefault(name,expected.copy())
                        if not np.array_equal(prior,expected):
                            raise AssertionError('Model output changed between blocks')
                        if block==0:
                            np.save(directory/(mode+'.'+name+'.raw.npy'),expected)
                            metric = core.compare(references['cpu_reference'][name],expected)
                            quality.append({'mode':mode,'audio':name,**metric})
                        for i in range(warmup):
                            raw, _ = invoke(runtime,features[name],registry)
                            if not np.array_equal(raw,expected):
                                raise AssertionError('Output changed during warmup')
                        for i in range(repeats//2):
                            raw, row = invoke(runtime,features[name],registry)
                            if not np.array_equal(raw,expected):
                                raise AssertionError('Output changed during timing')
                            samples.append({'block':block,'mode':mode,'audio':name,'repeat':i,**row})
                            print('[TIMING]',block+1,mode,name,str(i+1)+'/'+str(repeats//2),
                                  'model_ms',round(row['model_ms'],3),flush=True)
                        core.save(directory/'samples.json',samples)
                finally:
                    runtime.close(); del runtime; gc.collect()
                    initializations.append({'block':block,'mode':mode,
                        'session_overlay_parameter_init_ms':initialization,'before':before,'after':snapshot()})
                    core.save(directory/'initialization.json',initializations)
    summary=[]
    keys=('model_ms','model_l2_score_ms','l2_score_ms','CPU_remaining_ms','layer_callback_ms',
          'parameter_address_size_switch_ms','input_ddr_copy_flush_ms','fpga_start_done_ms',
          'output_invalidate_copy_ms','output_concat_ms','layout_ms')
    for name in queries:
        entries={}
        for mode in modes:
            rows=[v for v in samples if v['mode']==mode and v['audio']==name]
            assert len(rows)==repeats
            entries[mode]={key:core.stats([v[key] for v in rows]) for key in keys}
        candidate=entries['fpga']['model_l2_score_ms']['median_ms']
        row={'audio':name,'modes':entries,
             'cpu_reference_over_V3':entries['cpu_reference']['model_l2_score_ms']['median_ms']/candidate,
             'cpu_optimized_over_V3':entries['cpu_optimized']['model_l2_score_ms']['median_ms']/candidate,
             'accuracy_matched':False}
        summary.append(row)
        print('V3_LATENCY_RATIO:',json.dumps({k:v for k,v in row.items() if k!='modes'}),flush=True)
    result={**info,'benchmark_completed':True,'summary':summary,'embedding_quality_audit':quality,
            'frequency_locked':False,'samples':samples,'initializations':initializations,
            'FPGA_executed':True,'end_to_end_audio_speedup':None}
    core.save(directory/'performance_diagnostic.json',result)
    print('BENCHMARK_COMPLETED:',directory/'performance_diagnostic.json',flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--repeats',type=int,default=20)
    parser.add_argument('--warmup',type=int,default=3)
    args=parser.parse_args()
    if platform.system()!='Linux' or platform.machine().lower() not in ('armv7l','armv8l'):
        parser.error('Execute manually on PYNQ-Z2 ARM Linux')
    run(args.output,args.repeats,args.warmup)
