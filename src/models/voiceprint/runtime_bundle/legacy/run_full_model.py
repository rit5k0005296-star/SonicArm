"""Staged WAV -> Fbank -> complete CPU/hybrid -> embedding -> labeled scores.
Diagnostics are untimed for speed claims. Performance requires same-run correctness.
"""
from pathlib import Path
import argparse
import gc
import json
import platform
import sys
import time
import uuid
import numpy as np
from runtime_core import (HERE,BUNDLE,FullCPU,Hybrid,frontend,normalize,compare,stats,save,digest,verify_manifest)


def create(mode,plan,threads,debug=False):
    if mode in ('cpu','cpu_optimized'):
        return FullCPU(threads,optimize=mode=='cpu_optimized')
    return Hybrid(plan,'fpga' if mode=='fpga_debug' else mode,threads,debug or mode=='fpga_debug')


def execute(runtime,path,frontend_kind,registry=None,audit=False):
    start=time.perf_counter()
    f,timing=frontend(path,frontend_kind)
    e,network=runtime.run(f,audit)
    t=time.perf_counter();v=normalize(e)
    scores={speaker:float(vector@v) for speaker,vector in (registry or {}).items()}
    timing.update(embedding_l2_matching_ms=(time.perf_counter()-t)*1000,
                  total_e2e_ms=(time.perf_counter()-start)*1000)
    timing.update(network)
    return f,e,v,scores,timing


def correctness(args,directory):
    protocol=json.loads((BUNDLE/'smoke_protocol.json').read_text())
    items={x['id']:x for x in protocol['audio']}
    references={};front_checks=[];embedding_checks=[];scores={};timings=[];cold=[];vectors={}
    modes=['cpu','cpu_optimized'] if args.mode=='cpu' else ['cpu','cpu_optimized','bypass','integer']+(['fpga_debug','fpga'] if args.mode=='fpga' else [])
    for mode in modes:
        start=time.perf_counter();runtime=create(mode,args.plan,args.threads)
        cold.append({'mode':mode,'load_allocate_overlay_ms':(time.perf_counter()-start)*1000})
        registry={};vectors[mode]={}
        try:
            # Enroll first. Every mode registers from its own complete model output.
            enroll_audio=list(protocol['enroll'].values())
            order=list(dict.fromkeys(enroll_audio+[x['id'] for x in protocol['audio']]))
            for audio in order:
                item=items[audio];path=BUNDLE/item['path']
                if digest(path)!=item['sha256']:
                    raise ValueError('Audio hash mismatch')
                if isinstance(runtime,Hybrid):
                    runtime.audit_sink=lambda layer:save(directory/'layers'/mode/(audio+'.layer{:02d}.json'.format(layer['index'])),layer)
                f,e,v,s,tm=execute(runtime,path,args.frontend,registry,audit=not mode.startswith('cpu'))
                # Golden Fbank was generated using existing common.py, no crop or padding.
                golden=np.load(BUNDLE/item['features'],allow_pickle=False)
                if f.shape!=golden.shape:
                    raise AssertionError('Fbank shape mismatch')
                d=np.abs(f-golden)
                passed=bool(d.max()<=1e-4 and d.mean()<=1e-5)
                front_checks.append({'mode':mode,'audio':audio,'pass':passed,'max_abs':float(d.max()),'mean_abs':float(d.mean())})
                if not passed:
                    raise AssertionError('Frontend equivalence gate failed')
                references.setdefault(audio,{})[mode]=e.copy();vectors[mode][audio]=v
                for speaker,registered_audio in protocol['enroll'].items():
                    if registered_audio==audio:
                        registry[speaker]=v
                row={'mode':mode,'audio':audio,**tm};timings.append(row)
                for layer in tm.get('layers',[]):
                    save(directory/'layers'/mode/(audio+'.layer{:02d}.json'.format(layer['index'])),layer)
                np.save(directory/(mode+'.'+audio+'.embedding.npy'),e)
                save(directory/(mode+'.'+audio+'.timing.json'),row)
                print('[CORRECTNESS]',mode,audio,'T=',f.shape[1],flush=True)
        finally:
            runtime.close();del runtime;gc.collect()
        score_rows=[]
        for trial in protocol['trials']:
            enrolled=vectors[mode][protocol['enroll'][trial['speaker']]]
            score=float(enrolled@vectors[mode][trial['audio']])
            baseline=float(vectors['cpu'][protocol['enroll'][trial['speaker']]]@vectors['cpu'][trial['audio']])
            score_rows.append({**trial,'score':score,'cpu_score':baseline,'score_delta':score-baseline,
                'decision':None if args.threshold is None else score>=args.threshold,
                'cpu_decision':None if args.threshold is None else baseline>=args.threshold,
                'decision_changed':None if args.threshold is None else (score>=args.threshold)!=(baseline>=args.threshold),
                'threshold':args.threshold,'threshold_source':args.threshold_source,
                'distance_to_threshold':None if args.threshold is None else score-args.threshold,
                'near_threshold':None if args.threshold is None else abs(baseline-args.threshold)<=args.near_threshold})
        scores[mode]=score_rows
    gates=[]
    for audio,by_mode in references.items():
        for mode,e in by_mode.items():
            if mode in ('cpu','cpu_optimized'):
                continue
            reference=by_mode['integer'] if mode.startswith('fpga') else by_mode['cpu']
            metric=compare(reference,e)
            # The pre-existing consistency criteria govern bypass reconstruction.
            # FPGA must reproduce the complete integer replacement model.
            if mode=='bypass' or mode.startswith('fpga'):
                passed=bool(np.allclose(reference,e,atol=1e-4,rtol=1e-3) and metric['cosine']>=0.99999)
                criterion='existing consistency criterion: allclose(1e-4,1e-3), cosine>=0.99999'
            else:
                passed=bool(metric['cosine']>=args.integer_cosine_min and metric['relative_l2']<=args.integer_relative_max)
                criterion='provisional engineering drift limits; does not establish EER/minDCF'
            row={'audio':audio,'mode':mode,'reference':'integer' if mode.startswith('fpga') else 'original QDQ CPU',
                 'pass':passed,'criterion':criterion,**metric}
            gates.append(passed);embedding_checks.append(row)
    if args.mode!='cpu':
        for mode,rows in scores.items():
            if mode in ('cpu','cpu_optimized'):
                continue
            gates.extend(abs(r['score_delta'])<=args.score_delta_max for r in rows)
            if args.threshold is not None:
                gates.extend(not r['decision_changed'] for r in rows)
    result={'pass':all(gates),'scope':'full recording smoke correctness; labeled examples only',
        'mode':args.mode,'plan':args.plan,'frontend':args.frontend,'embedding':embedding_checks,
        'frontend_checks':front_checks,'scores':scores,'cold_start':cold,
        'auth_status':'pending calibration' if args.threshold is None else 'fixed user threshold; smoke only',
        'policy':{'integer_cosine_min':args.integer_cosine_min,'integer_relative_l2_max':args.integer_relative_max,
                  'score_delta_max':args.score_delta_max,'note':'provisional smoke gates, not recognition accuracy certification'},
        'versions':{'bundle':verify_manifest(),'threads':args.threads},
        'host':{'platform':platform.platform(),'machine':platform.machine()},
        'fpga_executed':args.mode=='fpga','performance_claim':False,
        'optimization_audit':[{'audio':a,**compare(v['cpu'],v['cpu_optimized'])} for a,v in references.items()],
        'CPU_reference_note':'cpu uses optimizations OFF to preserve float QDQ boundaries; cpu_optimized uses ON as existing evaluator. Its numerical differences are audited separately, never silently substituted for the boundary reference.'}
    save(directory/'correctness.json',result)
    if not result['pass']:
        raise AssertionError('Embedding/score gate failed; see correctness.json. Performance not run.')
    return result


def performance(args,directory,gate):
    if not gate['pass']:
        raise RuntimeError('Correctness prerequisite')
    protocol=json.loads((BUNDLE/'smoke_protocol.json').read_text())
    items={x['id']:x for x in protocol['audio']};samples=[];cold=[]
    selected=['cpu_optimized','cpu'] if args.mode=='cpu' else ['cpu_optimized','cpu',args.mode]
    runtimes={};registries={}
    try:
        for mode in selected:
            start=time.perf_counter();runtimes[mode]=create(mode,args.plan,args.threads)
            cold.append({'mode':mode,'model_overlay_buffer_parameter_load_ms':(time.perf_counter()-start)*1000})
            registries[mode]={}
            for speaker,audio in protocol['enroll'].items():
                _,_,v,_,tm=execute(runtimes[mode],BUNDLE/items[audio]['path'],args.frontend)
                registries[mode][speaker]=v
                cold.append({'mode':mode,'first_registration_call':tm})
        # Interleave same-host full model and actual replacement, alternating order.
        # Output allocation, graph feeds, pointer/scalar writes, input transfers remain inside calls.
        for trial_index,trial in enumerate(protocol['trials']):
            audio=trial['audio'];path=BUNDLE/items[audio]['path']
            for repeat in range(args.warmup+args.repeats):
                sequence=selected if repeat%2==0 else list(reversed(selected))
                for mode in sequence:
                    _,_,_,s,tm=execute(runtimes[mode],path,args.frontend,registries[mode],False)
                    if repeat>=args.warmup:
                        samples.append({'mode':mode,'audio':audio,'repeat':repeat-args.warmup,
                                        'scores':s,**tm})
                    if repeat==0 or repeat==args.warmup+args.repeats-1:
                        print('[TIMING]',audio,mode,repeat,'e2e_ms',round(tm['total_e2e_ms'],3),flush=True)
    finally:
        for runtime in runtimes.values():
            runtime.close()
    keys=['total_e2e_ms','audio_read_decode_mono_ms','fbank_resample_normalize_ms','cpu_remaining_ms',
          'layer_callback_ms','embedding_l2_matching_ms']
    summary=[]
    for trial in protocol['trials']:
        audio=trial['audio'];entries={}
        for mode in selected:
            rows=[x for x in samples if x['mode']==mode and x['audio']==audio]
            entries[mode]={k:stats([x[k] for x in rows if k in x]) for k in keys}
            layer_keys=('parameter_address_size_switch_ms','input_ddr_copy_flush_ms','fpga_start_done_ms',
                        'output_invalidate_copy_ms','output_concat_ms','layout_ms')
            entries[mode]['pointwise_subtotals']={k:stats([sum(l.get(k,0.) for l in row['layers']) for row in rows]) for k in layer_keys}
        ratio=None
        if args.mode!='cpu':
            ratio=entries['cpu_optimized']['total_e2e_ms']['median_ms']/entries[args.mode]['total_e2e_ms']['median_ms']
        matched=None if args.mode=='cpu' else entries['cpu']['total_e2e_ms']['median_ms']/entries[args.mode]['total_e2e_ms']['median_ms']
        opt_audit=next((x for x in gate['optimization_audit'] if x['audio']==audio),None)
        opt_equivalent=bool(opt_audit and opt_audit['cosine']>=0.99999 and opt_audit['relative_l2']<=0.01)
        summary.append({'audio':audio,'modes':entries,'same_host_boundary_reference_cpu_over_candidate':matched,
                        'same_host_optimized_cpu_over_candidate':ratio,
                        'optimized_CPU_equivalence_gate':opt_equivalent,
                        'optimized_ratio_accuracy_matched':opt_equivalent and args.mode!='cpu'})
    report={'scope':'read/decode/mono/resample/Fbank/full network/L2/enrolled identity matching',
        'excluded':'microphone acquisition waiting; initial model/overlay/DDR parameter loading shown separately; report file writes; untimed reference comparisons',
        'resident_policy':'layer weights/bias/multipliers/LUT resident DDR; shared scratch preallocated; every layer binds all pointers/scalars; no per-layer parameter refresh',
        'warmup':args.warmup,'repeats':args.repeats,'samples':samples,'summary':summary,'cold_start':cold,
        'correctness_sha256':digest(directory/'correctness.json'),'bundle_version':verify_manifest(),
        'host':{'platform':platform.platform(),'machine':platform.machine()},
        'fpga_executed':args.mode=='fpga','is_board_end_to_end_result':args.mode=='fpga',
        'CPU_baselines':'Both complete ORT_DISABLE_ALL boundary reference and complete ORT_ENABLE_ALL prior-evaluation policy are reported. Optimizer-dependent accuracy differences must accompany speed comparisons.',
        'note':'CPU/integer/bypass desktop times cannot substitute for board CPU/FPGA times.'}
    save(directory/'performance.json',report)
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=['cpu','bypass','integer','fpga'],default='integer')
    p.add_argument('--plan',choices=['one','all55'],default='one')
    p.add_argument('--frontend',choices=['canonical','numpy16k'],default='canonical')
    p.add_argument('--threads',type=int,default=1)
    p.add_argument('--benchmark',action='store_true')
    p.add_argument('--warmup',type=int,default=3)
    p.add_argument('--repeats',type=int,default=20)
    p.add_argument('--threshold',type=float)
    p.add_argument('--threshold-source')
    p.add_argument('--near-threshold',type=float,default=0.02)
    p.add_argument('--integer-cosine-min',type=float,default=0.99999)
    p.add_argument('--integer-relative-max',type=float,default=0.01)
    p.add_argument('--score-delta-max',type=float,default=0.001)
    args=p.parse_args(argv)
    if args.threads<1 or args.repeats<1 or args.warmup<1:
        p.error('Positive threads/repeats/warmup required')
    if args.threshold is not None and (not np.isfinite(args.threshold) or not args.threshold_source):
        p.error('Threshold needs finite value and documented development-set source')
    if args.mode=='fpga' and (platform.system()!='Linux' or platform.machine().lower() not in ('armv7l','armv8l')):
        p.error('FPGA must be run manually on PYNQ-Z2')
    version=verify_manifest()
    if args.mode=='fpga' and args.plan=='all55':
        prior=[]
        for file in (HERE/'test_results').glob('run_*/correctness.json'):
            data=json.loads(file.read_text(encoding='utf-8'))
            if data.get('pass') and data.get('fpga_executed') and data.get('plan')=='one' and data.get('versions',{}).get('bundle')==version and data.get('frontend')==args.frontend:
                prior.append(str(file))
        if not prior:
            p.error('Run same-version --mode fpga --plan one correctness on this board before all55')
    directory=HERE/'test_results'/('run_'+uuid.uuid4().hex)
    directory.mkdir(parents=True)
    save(directory/'run_info.json',{'run_id':directory.name,'version_id':version,'arguments':vars(args),
        'wall_clock_untrusted':time.strftime('%Y-%m-%d %H:%M:%S'),'timing_clock':'perf_counter',
        'python':sys.version,'platform':platform.platform(),
        'notebook_source_sha256':{p.name:__import__('runtime_core').notebook_source_digest(p) for p in HERE.glob('*.ipynb')}})
    import importlib.metadata
    environment={'packages':{},'cpu_frequency_governor':{},'cpu_frequency_locked':False,
                 'frequency_note':'Read-only snapshots; no governor/frequency settings changed',
                 'model_sha256':digest(BUNDLE/'camplus_int8_qdq.onnx'),
                 'bit_sha256':digest(BUNDLE/'support/pointwise.bit'),'hwh_sha256':digest(BUNDLE/'support/pointwise.hwh')}
    for name in ('numpy','onnxruntime','soundfile','torch','torchaudio','pynq'):
        try:
            environment['packages'][name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            environment['packages'][name]=None
    for name in ('scaling_cur_freq','scaling_governor'):
        file=Path('/sys/devices/system/cpu/cpu0/cpufreq')/name
        try:
            environment['cpu_frequency_governor'][name]=file.read_text().strip()
        except OSError:
            environment['cpu_frequency_governor'][name]=None
    if (HERE/'_native_ort/manifest.json').is_file() and platform.system()=='Linux' and platform.machine().lower() in ('armv7l','armv8l'):
        # Do not load the library while collecting environment snapshots: its first load
        # belongs to the first model's measured cold initialization.
        native_info=json.loads((HERE/'_native_ort/manifest.json').read_text(encoding='utf-8'))
        environment['actual_ORT_backend']={'backend':'native C API','package_version':native_info['version'],
            'library_sha256':digest(HERE/'_native_ort/libonnxruntime.so.1.17.1'),
            'loaded_library_version':'recorded after first measured model initialization'}
    save(directory/'environment.json',environment)
    try:
        gate=correctness(args,directory)
        if 'actual_ORT_backend' in environment:
            from native_ort_bridge import backend_details
            environment['actual_ORT_backend']=backend_details()
            save(directory/'environment.json',environment)
        if args.benchmark:
            performance(args,directory,gate)
        save(directory/'summary.json',{'pass':True,'correctness':True,'benchmark':args.benchmark,
            'fpga_executed':args.mode=='fpga','auth_threshold_calibrated':args.threshold is not None})
    except Exception as error:
        save(directory/'summary.json',{'pass':False,'error':repr(error),'fpga_executed':args.mode=='fpga'})
        print('FAILED report:',directory,flush=True)
        raise
    print('PASSED report:',directory,flush=True)
    return directory


if __name__=='__main__':
    main()
