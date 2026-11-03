"""Manual four-way same-board model latency; preserve failed numerical gates."""
from pathlib import Path
from contextlib import contextmanager
import csv
import gc
import hashlib
import json
import platform
import sys
import time
import uuid
import numpy as np
from compare_runtime import WORK,ROOT,HW,V4Runtime,FP32CPU
import compare_runtime as runtime
import runtime_core as core
import compatible_all55 as all55
from compatible_one_layer import route
from all55_fast_diagnostic import reference_and_progress,self_check,validate as validate_reference
from native_ort_bridge import backend_details


def save(path,value):
    path=Path(path).resolve()
    if not path.is_relative_to(WORK):raise ValueError('Output escapes comparison folder')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8')


def validate_files():
    core.verify_manifest();all55.validate();validate_reference()
    manifest=json.loads((WORK/'manifest.json').read_text(encoding='utf8'))
    for name,wanted in manifest['files'].items():
        p=(WORK/name).resolve()
        if not p.is_relative_to(WORK):raise ValueError('Unsafe manifest path')
        if p.suffix=='.ipynb':
            code=core.notebook_sources(p)
            observed=hashlib.sha256(json.dumps(code,ensure_ascii=False).encode()).hexdigest()
        else:observed=core.digest(p)
        if observed!=wanted:raise ValueError('Comparison file changed: '+name)
    if core.digest(ROOT/'upload_manifest.json')!=manifest['root_manifest_sha256']:raise ValueError('Wrong original package version')
    if core.digest(HW/'upload_manifest.json')!=manifest['hardware_manifest_sha256']:raise ValueError('Wrong V4 package')
    runtime.fcm.verify_package()
    return manifest


def identity():
    return dict(package_sha256=core.digest(WORK/'manifest.json'),
        compatible_models_sha256=core.digest(all55.ASSETS/'manifest.json'),
        v3_bit_sha256=core.digest(core.BUNDLE/'support/pointwise.bit'),
        v4_bit_sha256=core.digest(HW/'fcm_v4.bit'),backend=backend_details())


def output_dir(directory):
    p=Path(directory).resolve()
    if not p.is_relative_to(WORK/'results'):raise ValueError('Use benchmark_compare/results')
    p.mkdir(parents=True,exist_ok=True)
    return p


def setup(directory):
    if platform.system()!='Linux' or platform.machine().lower() not in ('armv7l','armv8l'):
        raise RuntimeError('Run this Notebook manually on PYNQ-Z2 ARM Linux')
    if runtime.UNSAFE:raise RuntimeError('Previous hardware failure; power-cycle board before retry')
    validate_files();directory=output_dir(directory)
    info=dict(identity=identity(),actual_hardware_run=False,platform=platform.platform(),python=sys.version,numpy=np.__version__,
        scope='fixed canonical full-recording Fbank -> complete CAM++ -> L2 -> registered cosine',
        primary_baseline='same-board complete INT8 QDQ model, ORT_ENABLE_ALL, 1 thread',
        additional_baseline='original FP32 complete CPU model, ORT_ENABLE_ALL, same52 AveragePool compatibility edits',
        excluded=['audio capture','audio read/decode','Fbank','model/Overlay/parameter initialization','integer audits','file I/O'],
        included=['remaining CPU operators','DDR input/output copies','cache synchronization','all pointer/scalar writes','PL start/done polling','L2 and cosine'],
        accuracy_matched_claim=False,authentication_threshold_calibrated=False,frequency_locked=False,
        note='CPU graph optimization differs from validated hybrid CPU chunks. Results measure actual complete implementations; not an isolated arithmetic throughput comparison. Init timing is warm-process, runtime already preloaded.')
    save(directory/'run_info.json',info)
    print('COMPARE_SETUP_PASS:',directory,flush=True)
    return info


def hardware_check(directory):
    from test_fcm_pynq import run_stage,identity as hw_identity
    directory=output_dir(directory);validate_files()
    if runtime.UNSAFE:raise RuntimeError('Previous hardware failure; power-cycle board before retry')
    expected=hw_identity();matches=[]
    for p in (HW/'test_results').glob('*/correctness.json'):
        report=json.loads(p.read_text(encoding='utf8'))
        if report.get('pass') and report.get('actual_hardware') and report.get('identity')==expected:
            matches.append(p)
    if matches:
        proof=sorted(matches,key=lambda p:p.stat().st_mtime)[-1]
    else:
        run=HW/'test_results'/('compare_'+uuid.uuid4().hex)
        try:
            run_stage('smoke',run);run_stage('correctness',run)
        except BaseException:
            # Conservative: do not start another overlay after an interrupted gate.
            runtime.UNSAFE=True;raise
        proof=run/'correctness.json'
    record=dict(identity=identity(),hardware_identity=expected,report=str(proof),report_sha256=core.digest(proof),pass_=True,
                scope='Independent V4 FCM hardware validation; full CAM++ validation follows')
    save(directory/'hardware_prerequisite.json',record)
    print('V4_HARDWARE_READY:',proof,flush=True)
    return record


def data():
    import wave
    protocol=json.loads((core.BUNDLE/'smoke_protocol.json').read_text())
    items={x['id']:x for x in protocol['audio']}
    names=[protocol['enroll']['speaker1'],*[x['audio'] for x in protocol['trials']]]
    features={n:np.load(core.BUNDLE/items[n]['features'],allow_pickle=False) for n in dict.fromkeys(names)}
    for n,x in features.items():
        if x.dtype!=np.float32 or x.shape!=(1,items[n]['frames'],80) or not np.isfinite(x).all():raise ValueError('Invalid canonical Fbank: '+n)
        with wave.open(str(core.BUNDLE/items[n]['path']),'rb') as audio:
            items[n]['duration_seconds']=audio.getnframes()/audio.getframerate()
    return protocol,items,features


@contextmanager
def execution(factory=None):
    mapping=all55.validate()
    with route(mapping,factory),reference_and_progress() as original:
        yield original


def make_runtime(mode,capacity,debug=False):
    if mode=='cpu_int8_reference':return core.FullCPU(1,False)
    if mode=='cpu_int8':return core.FullCPU(1,True)
    if mode=='cpu_fp32':return FP32CPU()
    if mode=='v3_software':return core.Hybrid('all55','integer',1,debug)
    if mode=='v3':
        if runtime.UNSAFE:raise RuntimeError('Previous hardware failure')
        return core.Hybrid('all55','fpga',1,debug)
    if mode=='v4_rebuild':return V4Runtime('bypass',False,capacity)
    if mode=='v4_software':return V4Runtime('integer',False,capacity)
    if mode=='v4':return V4Runtime('fpga',debug,capacity)
    raise ValueError('Unknown complete-model mode')


def close(model):
    contexts=[getattr(model,'fpga',None),getattr(model,'fcm_context',None)]
    base=getattr(model,'base',None)
    if base:contexts.append(base.fpga)
    if any(c is not None and not c.safe for c in contexts):runtime.UNSAFE=True
    model.close();gc.collect()


def integration_check(directory,include_fp32=True):
    directory=output_dir(directory);validate_files()
    proof=json.loads((directory/'hardware_prerequisite.json').read_text())
    if proof.get('identity')!=identity() or not proof.get('pass_'):raise ValueError('Matching V4 hardware gate required')
    if core.digest(proof['report'])!=proof['report_sha256']:raise ValueError('Hardware receipt changed')
    protocol,items,features=data();capacity=max(x.shape[1] for x in features.values())
    modes=['cpu_int8_reference','cpu_int8','v4_rebuild','v3_software','v3','v4_software','v4']
    if include_fp32:modes.append('cpu_fp32')
    vectors={};audits=[];quality=[]
    try:
        with execution() as original:
            checks=self_check(original);save(directory/'reference_self_check.json',checks)
            for mode in modes:
                print('[INTEGRATE]',mode,'INITIALIZE',flush=True)
                model=make_runtime(mode,capacity,debug=mode in ('v3','v4'))
                try:
                    vectors[mode]={}
                    for name,x in features.items():
                        raw,detail=model.run(x,audit=mode in ('v3','v4'))
                        if raw.shape!=(1,192) or not np.isfinite(raw).all():raise AssertionError('Invalid full embedding')
                        vectors[mode][name]=raw.copy();np.save(directory/(mode+'.'+name+'.npy'),raw,allow_pickle=False)
                        if mode=='v4_rebuild':
                            metric=core.compare(vectors['cpu_int8_reference'][name],raw)
                            if not np.allclose(vectors['cpu_int8_reference'][name],raw,atol=1e-4,rtol=1e-3) or metric['cosine']<.99999:
                                raise AssertionError('FCM CPU subgraph reconstruction failed')
                        if mode in ('v3','v4'):
                            fcm_rows=[r for r in detail['layers'] if r.get('component')=='FCM']
                            point_rows=[r for r in detail['layers'] if r.get('component')!='FCM']
                            if len(point_rows)!=55 or (mode=='v4' and len(fcm_rows)!=12) or any(not r.get('integer_exact') for r in detail['layers']):
                                raise AssertionError('Missing real hardware INT8/INT32 audit')
                            if not np.array_equal(vectors[mode+'_software'][name],raw):raise AssertionError('Full hardware differs from matching integer model')
                            audits.append(dict(mode=mode,audio=name,pointwise_layers=55,fcm_layers=len(fcm_rows),
                                actual_chunks=sum(r['chunks'] for r in detail['layers']),integer_embedding_exact=True,layers=detail['layers']))
                        quality.append(dict(mode=mode,audio=name,**core.compare(vectors['cpu_int8_reference'][name],raw)))
                        print('[INTEGRATION PASS]',mode,name,flush=True)
                finally:close(model)
    except BaseException as error:
        save(directory/'integration_failed.json',dict(pass_=False,error=repr(error),hardware_may_be_active=runtime.UNSAFE))
        print('STOP: return full output; on hardware timeout/interruption keep kernel until power-cycle.',flush=True);raise
    enrolled=protocol['enroll']['speaker1'];scores=[]
    for trial in protocol['trials']:
        n=trial['audio']
        entry=dict(audio=n,label=trial['label'],scores={})
        for mode,rows in vectors.items():entry['scores'][mode]=float(core.normalize(rows[enrolled])@core.normalize(rows[n]))
        entry['V3_abs_score_delta']=abs(entry['scores']['v3']-entry['scores']['cpu_int8_reference'])
        entry['V4_abs_score_delta']=abs(entry['scores']['v4']-entry['scores']['cpu_int8_reference'])
        scores.append(entry)
    strict={}
    for mode in ('v3','v4'):
        q=[r for r in quality if r['mode']==mode]
        strict[mode]=all(r['cosine']>=.99999 and r['relative_l2']<=.01 for r in q) and all(s[mode.upper()+'_abs_score_delta']<=.001 for s in scores)
    report=dict(identity=identity(),integration_ready=True,actual_hardware=True,include_fp32=bool(include_fp32),
        graph_reconstruction_pass=True,hardware_integer_consistency_pass=True,strict_QDQ_drift_gate=strict,
        embedding_audit=quality,paired_scores=scores,hardware_audits=audits,
        thresholds=dict(integer_cosine_min=.99999,integer_relative_l2_max=.01,score_abs_delta_max=.001),
        authentication_threshold=None,accuracy_matched_speedup_claim=False,
        feature_sha256={n:core.digest(core.BUNDLE/items[n]['features']) for n in features})
    save(directory/'integration.json',report)
    print('STRICT_QDQ_DRIFT_GATE:',json.dumps(strict),flush=True)
    print('INTEGRATION_READY:',directory/'integration.json',flush=True)
    return report


def snapshot():
    result={}
    for name,path in dict(meminfo='/proc/meminfo',governor='/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor',
        frequency='/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq',temperature='/sys/class/thermal/thermal_zone0/temp').items():
        try:result[name]=Path(path).read_text().strip()
        except OSError:result[name]=None
    return result


def invoke(model,x,registry):
    t=time.perf_counter();raw,detail=model.run(x,audit=False);end=time.perf_counter()
    v=core.normalize(raw);score=float(registry@v);finish=time.perf_counter()
    row=dict(model_ms=(end-t)*1000,model_l2_score_ms=(finish-t)*1000,l2_score_ms=(finish-end)*1000,
        CPU_remaining_ms=detail['cpu_remaining_ms'],layer_callback_ms=detail.get('layer_callback_ms',0.),score=score,
        fcm_chunks=sum(r.get('chunks',0) for r in detail['layers'] if r.get('component')=='FCM'),
        pointwise_chunks=sum(r.get('chunks',0) for r in detail['layers'] if r.get('component')!='FCM'))
    for key in ('parameter_address_size_switch_ms','input_ddr_copy_flush_ms','fpga_start_done_ms','output_invalidate_copy_ms','output_concat_ms'):
        row[key]=sum(r.get(key,0.) for r in detail['layers'])
    return raw,row


def benchmark(directory,repeats=20,warmup=3,include_fp32=True):
    directory=output_dir(directory);validate_files()
    gate=json.loads((directory/'integration.json').read_text())
    if not gate.get('integration_ready') or not gate.get('actual_hardware') or gate.get('identity')!=identity():raise ValueError('Actual matching integration gate required')
    if include_fp32 and not gate.get('include_fp32'):raise ValueError('Run FP32 integration before including its timing')
    if repeats<4 or repeats%2 or warmup<1:raise ValueError('Use even repeats>=4 and warmup>=1; standard20/3')
    if runtime.UNSAFE:raise RuntimeError('Previous hardware failure; power-cycle board first')
    protocol,items,features=data();enrolled=protocol['enroll']['speaker1'];queries=[r['audio'] for r in protocol['trials']]
    modes=['cpu_int8','v3','v4']
    if include_fp32:modes.insert(0,'cpu_fp32')
    samples=[];initializations=[];references={};registry_vectors={};capacity=max(x.shape[1] for x in features.values())
    try:
        with execution():
            for block in range(2):
                order=modes if block==0 else list(reversed(modes))
                for mode in order:
                    print('[BENCH]',block+1,'/2',mode,'INITIALIZE',flush=True)
                    before=snapshot();t=time.perf_counter();model=make_runtime(mode,capacity,False)
                    initialization=(time.perf_counter()-t)*1000
                    try:
                        raw,_=model.run(features[enrolled],audit=False);registry=core.normalize(raw)
                        old=registry_vectors.setdefault(mode,registry.copy())
                        if not np.array_equal(old,registry):raise AssertionError('Registration changed between blocks')
                        for name in queries:
                            expected,_=model.run(features[name],audit=False)
                            old=references.setdefault(mode,{}).setdefault(name,expected.copy())
                            if not np.array_equal(old,expected):raise AssertionError('Model changed between blocks')
                            # This also proves debug-OFF timed mode agrees with prior audited/debug-ON mode.
                            audited=np.load(directory/((mode if mode.startswith('cpu') else mode)+'.'+name+'.npy'),allow_pickle=False)
                            if not np.array_equal(expected,audited):raise AssertionError('Timed mode differs from integration gate')
                            for i in range(warmup):
                                actual,_=invoke(model,features[name],registry)
                                if not np.array_equal(actual,expected):raise AssertionError('Warmup output changed')
                            for i in range(repeats//2):
                                actual,row=invoke(model,features[name],registry)
                                if not np.array_equal(actual,expected):raise AssertionError('Timed output changed')
                                if mode=='v3' and row['pointwise_chunks']<55:raise AssertionError('V3 missing hardware calls')
                                if mode=='v4' and (row['fcm_chunks']<12 or row['pointwise_chunks']<55):raise AssertionError('V4 missing hardware calls')
                                samples.append(dict(block=block,mode=mode,audio=name,repeat=i,**row))
                                print('[TIMING]',block+1,mode,name,str(i+1)+'/'+str(repeats//2),'model_ms',round(row['model_ms'],3),flush=True)
                            save(directory/'raw_samples.json',samples)
                    finally:
                        close(model)
                        initializations.append(dict(block=block,mode=mode,session_overlay_parameter_init_ms=initialization,before=before,after=snapshot()))
                        save(directory/'initialization.json',initializations)
    except BaseException as error:
        save(directory/'benchmark_failed.json',dict(completed=False,error=repr(error),hardware_may_be_active=runtime.UNSAFE))
        raise
    summary=[];ratios=[]
    for name in queries:
        medians={}
        for mode in modes:
            rows=[r for r in samples if r['mode']==mode and r['audio']==name]
            if len(rows)!=repeats:raise AssertionError('Wrong sample count')
            stats=core.stats([r['model_l2_score_ms'] for r in rows]);medians[mode]=stats['median_ms']
            row=dict(audio=name,mode=mode,samples=repeats,**stats,
                real_time_factor=stats['median_ms']/1000/items[name]['duration_seconds'])
            summary.append(row);print('MODEL_LATENCY:',json.dumps(row),flush=True)
        ratio=dict(audio=name,INT8_CPU_over_V3=medians['cpu_int8']/medians['v3'],INT8_CPU_over_V4=medians['cpu_int8']/medians['v4'],
                   V3_over_V4=medians['v3']/medians['v4'],accuracy_matched_claim=False)
        if include_fp32:ratio.update(FP32_CPU_over_V3=medians['cpu_fp32']/medians['v3'],FP32_CPU_over_V4=medians['cpu_fp32']/medians['v4'])
        ratios.append(ratio);print('SPEEDUP_COMPARE:',json.dumps(ratio),flush=True)
    result=dict(identity=identity(),completed=True,actual_hardware=True,summary=summary,ratios=ratios,
        strict_QDQ_drift_gate=gate['strict_QDQ_drift_gate'],accuracy_matched_speedup_claim=False,
        frequency_locked=False,scope='frozen canonical Fbank -> full model -> L2 -> cosine',
        audio_end_to_end_speedup=None,initializations=initializations,raw_samples=samples)
    save(directory/'performance.json',result)
    with (directory/'summary.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(summary[0]));writer.writeheader();writer.writerows(summary)
    lines=['# 同板完整模型时延对照','', '| 音频 | 配置 | 样本数 | 中位数ms | P95ms |','|---|---|---:|---:|---:|']
    lines += ['| {audio} | {mode} | {samples} | {median_ms:.3f} | {p95_ms:.3f} |'.format(**r) for r in summary]
    lines+=['','倍率>1为分母配置更快，<1则更慢；不是同精度或音频采集端到端加速。','', '```json',json.dumps(ratios,indent=2),'```']
    (directory/'summary.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    print('COMPARE_BENCHMARK_COMPLETED:',directory/'performance.json',flush=True)
    return result
