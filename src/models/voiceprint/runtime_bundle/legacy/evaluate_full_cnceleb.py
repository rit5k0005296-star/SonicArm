"""Manual official CN-Celeb evaluation, same lists/complete recordings/L2/tied DET.
No benchmark claims. CPU optimized, CPU diagnostic, integer or actual FPGA embeddings.
Full protocol can be slow on ARM; start with a subset. Never crop long enrollment audio.
"""
from pathlib import Path
import argparse
import importlib.util
import json
import platform
import time
import uuid
import numpy as np
from runtime_core import HERE,BUNDLE,save,digest,frontend,normalize,compare,verify_manifest
from run_full_model import create


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--eval-root',type=Path,required=True)
    p.add_argument('--mode',choices=['cpu_optimized','cpu','integer','fpga'],default='cpu_optimized')
    p.add_argument('--plan',choices=['one','all55'],default='one')
    p.add_argument('--frontend',choices=['canonical','numpy16k'],default='canonical')
    p.add_argument('--threads',type=int,default=1)
    p.add_argument('--limit-enroll',type=int,default=0)
    p.add_argument('--limit-test',type=int,default=0)
    p.add_argument('--threshold',type=float)
    p.add_argument('--threshold-source')
    p.add_argument('--diagnostic-evaluation',action='store_true',help='Quantify accuracy drift even if smoke acceptance failed; no speed claim')
    args=p.parse_args(argv)
    if args.threshold is not None and (not np.isfinite(args.threshold) or not args.threshold_source):
        p.error('Threshold requires finite value and development-set source')
    if args.threads<1 or min(args.limit_enroll,args.limit_test)<0:
        p.error('Invalid thread/count')
    if args.mode=='fpga' and (platform.system()!='Linux' or platform.machine().lower() not in ('armv7l','armv8l')):
        p.error('Run actual FPGA manually on PYNQ-Z2')
    version=verify_manifest()
    if args.mode in ('integer','fpga') and not args.diagnostic_evaluation:
        accepted=[]
        for file in (HERE/'test_results').glob('run_*/correctness.json'):
            d=json.loads(file.read_text(encoding='utf-8'))
            if d.get('pass') and d.get('mode')==args.mode and d.get('plan')==args.plan and d.get('frontend')==args.frontend and d.get('versions',{}).get('bundle')==version:
                accepted.append(str(file))
        if not accepted:
            p.error('Same-version smoke correctness required. Use --diagnostic-evaluation only to investigate known drift.')
    spec=importlib.util.spec_from_file_location('original_cnceleb_protocol',BUNDLE/'protocol_reference.py')
    protocol=importlib.util.module_from_spec(spec);spec.loader.exec_module(protocol)
    root=args.eval_root.resolve()
    enroll,tests=protocol.load_lists(root,args.limit_enroll,args.limit_test)
    if not enroll or not tests:
        raise ValueError('Empty lists')
    names=list(dict.fromkeys([*enroll.values(),*tests]))
    for name in names:
        protocol.resolve_audio(root,name)
    directory=HERE/'test_results'/('cnceleb_'+uuid.uuid4().hex);directory.mkdir(parents=True)
    vectors=directory/'embeddings';vectors.mkdir()
    save(directory/'run_info.json',{'bundle_version':version,'arguments':{k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()},
        'subset':bool(args.limit_enroll or args.limit_test),'platform':platform.platform(),
        'lists_sha256':{x.name:digest(x) for x in (root/'lists').glob('*.lst')},
        'protocol':'complete official concatenated enrollment, no crop/VAD/chunk averaging/score normalization',
        'p_target':0.01,'c_miss':1.,'c_fa':1.,'threshold_status':'uncalibrated' if args.threshold is None else args.threshold_source})
    runtime=create(args.mode,args.plan,args.threads);records=[]
    try:
        for i,name in enumerate(names,1):
            path=protocol.resolve_audio(root,name)
            f,front_timing=frontend(path,args.frontend)
            e,network=runtime.run(f,False)
            v=normalize(e)
            key=__import__('hashlib').sha256(name.encode()).hexdigest()
            np.save(vectors/(key+'.npy'),v)
            records.append({'audio':name,'audio_sha256':digest(path),'frames':f.shape[1],
                            **front_timing,'cpu_remaining_ms':network['cpu_remaining_ms'],
                            'layer_callback_ms':network.get('layer_callback_ms',0)})
            if i==1 or i%25==0 or i==len(names):
                save(directory/'audio_metadata.json',records)
                print('[CNCELEB]',i,'/',len(names),args.mode,flush=True)
        scores,labels,total=protocol.score_trials(root,enroll,tests,vectors,directory,bool(args.limit_enroll or args.limit_test))
        metrics,thresholds,far,frr=protocol.detection_metrics(scores,labels,.01,1.,1.,args.threshold)
        metrics.update(mode=args.mode,plan=args.plan,frontend=args.frontend,subset_smoke_test=bool(args.limit_enroll or args.limit_test),
                       official_list_trials=total,FPGA_executed=args.mode=='fpga',diagnostic_evaluation=args.diagnostic_evaluation,
                       performance_claim=False,bundle_version=version,threshold_source=args.threshold_source)
        save(directory/'metrics.json',metrics)
        np.savez(directory/'det_curve.npz',thresholds=thresholds,far=far,frr=frr)
        save(directory/'summary.json',{'pass':True,'metrics':metrics,'performance_claim':False})
    except Exception as error:
        save(directory/'summary.json',{'pass':False,'error':repr(error),'performance_claim':False})
        raise
    finally:
        runtime.close()
    print('CNCELEB report:',directory)
    return directory


if __name__=='__main__':
    main()
