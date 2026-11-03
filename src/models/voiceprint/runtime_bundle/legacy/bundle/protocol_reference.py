"""CN-Celeb official concatenated enrollment protocol, original ECAPA embeddings."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SOURCE = ROOT / 'SIG_project/project3/voiceprint'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, path)


def resolve_audio(root, name):
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Audio path escapes eval directory: ' + name)
    if path.is_file():
        return path
    alternative = path.with_suffix('.flac')
    if alternative.is_file():
        return alternative
    raise FileNotFoundError(path)


def load_lists(root, limit_enroll=0, limit_test=0):
    enrollment = {}
    for line in (root/'lists/enroll.lst').read_text().splitlines():
        if not line.strip():
            continue
        identity, audio = line.split()
        if identity in enrollment:
            raise ValueError('Repeated enrollment identity: ' + identity)
        enrollment[identity] = audio
    tests = [line.strip() for line in (root/'lists/test.lst').read_text().splitlines() if line.strip()]
    if len(tests) != len(set(tests)):
        raise ValueError('Repeated test list entry')
    if limit_enroll:
        enrollment = dict(list(enrollment.items())[:limit_enroll])
    if limit_test:
        tests = tests[:limit_test]
    return enrollment, tests


def detection_metrics(scores, labels, p_target=0.01, c_miss=1., c_fa=1., threshold=None):
    """Accept when score >= threshold. Sweep tied scores as groups, interpolate EER."""
    scores = np.asarray(scores, dtype=np.float64)
    labels = np.asarray(labels)
    if scores.ndim != 1 or labels.shape != scores.shape or not np.isfinite(scores).all():
        raise ValueError('Invalid score/label arrays')
    if not np.isin(labels, [0, 1]).all():
        raise ValueError('Labels must be 0/1')
    nt = int(np.sum(labels == 1)); nn = len(labels)-nt
    if not nt or not nn:
        raise ValueError('Both target and non-target trials are required')
    order = np.argsort(-scores, kind='stable')
    sorted_scores = scores[order]
    target = labels[order] == 1
    ends = np.r_[np.flatnonzero(sorted_scores[:-1] != sorted_scores[1:]), len(scores)-1]
    accepted_targets = np.cumsum(target, dtype=np.int64)[ends]
    accepted_non = ends+1-accepted_targets
    frr = np.r_[1., 1.-accepted_targets/nt]
    far = np.r_[0., accepted_non/nn]
    thresholds = np.r_[np.nextafter(sorted_scores[0], np.inf), sorted_scores[ends]]
    delta = far-frr
    k = int(np.searchsorted(delta, 0.))
    if delta[k] == 0:
        eer = far[k]
    else:
        fraction = -delta[k-1]/(delta[k]-delta[k-1])
        eer = far[k-1]+fraction*(far[k]-far[k-1])
    norm = min(c_miss*p_target, c_fa*(1-p_target))
    costs = (c_miss*p_target*frr+c_fa*(1-p_target)*far)/norm
    j = int(np.argmin(costs))
    result = {'trials':len(scores), 'target_trials':nt, 'non_target_trials':nn,
              'eer_percent':float(eer*100), 'eer_method':'linear interpolation of tie-grouped DET points',
              'min_dcf_normalized':float(costs[j]), 'min_dcf_threshold':float(thresholds[j]),
              'p_target':p_target, 'c_miss':c_miss, 'c_fa':c_fa}
    if threshold is not None:
        accepted = scores >= threshold
        result['fixed_threshold'] = {'threshold':threshold,
            'far_percent':float(np.mean(accepted[labels == 0])*100),
            'frr_percent':float(np.mean(~accepted[labels == 1])*100),
            'note':'user-supplied threshold; not calibrated on this evaluation set'}
    return result, thresholds, far, frr


def extract_all(args, root, enrollment, tests, cache, identity, model_loader=None):
    import soundfile as sf
    import torch
    if model_loader is None:
        sys.path.insert(0, str(SOURCE))
        from voiceprint_core import load_classifier
        model_loader = load_classifier
    torch.set_num_threads(args.threads)
    # Reuse the old loader, but use a workspace copy so pretrainer writes cannot alter old files.
    import shutil
    snapshot = args.output/'model_snapshot'
    snapshot.mkdir(exist_ok=True)
    for path in args.model_dir.iterdir():
        if path.is_file() and path.suffix in {'.yaml','.ckpt','.txt','.bin','.pt','.json'}:
            dest = snapshot/path.name
            if not dest.exists() or digest(path) != digest(dest):
                shutil.copy2(path, dest)
    classifier, device = model_loader(snapshot, args.device)
    audio_names = list(dict.fromkeys([*enrollment.values(), *tests]))
    computed=0; cache_hits=0; seconds=0.; elapsed_total=0.
    records=[]
    for i, name in enumerate(audio_names, 1):
        path = resolve_audio(root, name)
        st = path.stat()
        signature = {'path':str(path), 'size':st.st_size, 'mtime_ns':st.st_mtime_ns,
                     'run_identity':identity}
        key = hashlib.sha256(name.encode()).hexdigest()
        vector_path=cache/(key+'.npy'); metadata_path=cache/(key+'.json')
        try:
            metadata=json.loads(metadata_path.read_text(encoding='utf-8'))
            valid=metadata['signature']==signature
        except (OSError, ValueError, KeyError):
            valid=False
        if valid and vector_path.exists():
            vector=np.load(vector_path, allow_pickle=False)
            valid=vector.shape==(192,) and np.isfinite(vector).all() and abs(np.linalg.norm(vector)-1)<1e-4
        if valid:
            cache_hits+=1
        else:
            start=time.perf_counter()
            # Float32 libsndfile PCM scaling equals the original PCM16 / 32768 pipeline.
            pcm, sample_rate=sf.read(str(path), dtype='float32', always_2d=True)
            if pcm.size==0 or not np.isfinite(pcm).all():
                raise ValueError('Empty or invalid audio: '+str(path))
            mono=pcm.mean(axis=1)
            duration=len(mono)/sample_rate
            if duration < 0.45:
                raise ValueError('Audio <0.45 seconds; do not silently drop official trials: '+str(path))
            waveform=torch.from_numpy(mono.copy())
            if sample_rate != 16000:
                import torchaudio.functional as af
                waveform=af.resample(waveform,sample_rate,16000)
            waveform=waveform.unsqueeze(0).to(device)
            if device=='cuda': torch.cuda.synchronize()
            with torch.inference_mode():
                embedding=classifier.encode_batch(waveform,torch.ones(1,device=device)).reshape(-1)
                norm=torch.linalg.vector_norm(embedding)
                if not torch.isfinite(norm) or norm.item()<1e-12:
                    raise ValueError('Invalid embedding: '+str(path))
                vector=(embedding/norm).cpu().numpy().astype(np.float32)
            if device=='cuda': torch.cuda.synchronize()
            elapsed=time.perf_counter()-start
            if vector.shape!=(192,) or not np.isfinite(vector).all():
                raise ValueError('Invalid embedding shape/value: '+str(path))
            metadata={'signature':signature,'audio_seconds':duration,'elapsed_seconds':elapsed,
                      'original_sample_rate':sample_rate,'rms':float(np.sqrt(np.mean(mono.astype(np.float64)**2))),
                      'peak':float(np.max(np.abs(mono))), 'device':device}
            temp=vector_path.with_suffix('.tmp.npy')
            np.save(temp,vector); os.replace(temp,vector_path)
            save_json(metadata_path,metadata)
            computed+=1; seconds+=duration; elapsed_total+=elapsed
        records.append({'audio':name,**{k:v for k,v in metadata.items() if k!='signature'}})
        if i==1 or i%25==0 or i==len(audio_names):
            print(f'[EMBED] {i}/{len(audio_names)} new={computed} cached={cache_hits}',flush=True)
    save_json(args.output/'audio_metadata.json',records)
    return {'device':device,'new_audio':computed,'cache_hits':cache_hits,
            'new_audio_seconds':seconds,'new_extraction_seconds':elapsed_total,
            'new_extraction_rtf':elapsed_total/seconds if seconds else None,
            'timing_scope':'read/decode/resample/encode/L2/output transfer; excludes model load, cache writes and scoring'}


def score_trials(root, enrollment, tests, cache, output, subset):
    def load(name):
        key=hashlib.sha256(name.encode()).hexdigest()
        vector=np.load(cache/(key+'.npy'),allow_pickle=False)
        if vector.shape!=(192,) or not np.isfinite(vector).all():
            raise ValueError('Invalid cached vector: '+name)
        return vector/np.linalg.norm(vector)
    enroll_ids=list(enrollment); ei={name:i for i,name in enumerate(enroll_ids)}
    ti={name:i for i,name in enumerate(tests)}
    a=np.stack([load(enrollment[name]) for name in enroll_ids])
    b=np.stack([load(name) for name in tests])
    similarities=a @ b.T
    scores=[]; labels=[]; seen=0
    trials=root/'lists/trials.lst'
    with trials.open(encoding='utf-8') as f:
        for line_number,line in enumerate(f,1):
            if not line.strip(): continue
            fields=line.split()
            if len(fields)!=3 or fields[2] not in {'0','1'}:
                raise ValueError(f'Malformed trial at line {line_number}')
            speaker,audio,label=fields; seen+=1
            if speaker not in ei or audio not in ti:
                if subset: continue
                raise ValueError(f'Trial references unknown entry at line {line_number}')
            scores.append(similarities[ei[speaker],ti[audio]]); labels.append(int(label))
    scores=np.asarray(scores,dtype=np.float32); labels=np.asarray(labels,dtype=np.uint8)
    np.savez(output/'trial_scores.npz',scores=scores,labels=labels)
    # Trial order follows trials.lst; subset mode filters unselected list entries.
    return scores,labels,seen


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--eval-root',type=Path,default=HERE/'data/cn-celeb_v2/CN-Celeb_flac/eval')
    parser.add_argument('--model-dir',type=Path,default=SOURCE/'pretrained_models/spkrec-ecapa-voxceleb')
    parser.add_argument('--output',type=Path,default=HERE/'results/cnceleb_ecapa')
    parser.add_argument('--device',choices=['cpu','cuda','auto'],default='cpu')
    parser.add_argument('--threads',type=int,default=4)
    parser.add_argument('--limit-enroll',type=int,default=0)
    parser.add_argument('--limit-test',type=int,default=0)
    parser.add_argument('--p-target',type=float,default=0.01)
    parser.add_argument('--c-miss',type=float,default=1.)
    parser.add_argument('--c-fa',type=float,default=1.)
    parser.add_argument('--threshold',type=float,default=None)
    parser.add_argument('--inspect-only',action='store_true')
    args=parser.parse_args()
    if args.threads<1 or min(args.limit_enroll,args.limit_test)<0:
        parser.error('Threads must be positive and limits nonnegative')
    if not 0<args.p_target<1 or min(args.c_miss,args.c_fa)<=0:
        parser.error('Invalid DCF parameters')
    args.output=args.output.resolve(); args.model_dir=args.model_dir.resolve()
    if not args.output.is_relative_to(ROOT.resolve()):
        parser.error('Output must remain inside the desktop SonicArm workspace')
    root=args.eval_root.resolve()
    enrollment,tests=load_lists(root,args.limit_enroll,args.limit_test)
    for name in [*enrollment.values(),*tests]: resolve_audio(root,name)
    if not enrollment or not tests: raise ValueError('Empty enrollment/test selection')
    subset=bool(args.limit_enroll or args.limit_test)
    print(f'[PROTOCOL] enrollment={len(enrollment)} tests={len(tests)} subset={subset}',flush=True)
    if args.inspect_only:
        print('All selected audio paths exist. No model inference or output writes.')
        return
    args.output.mkdir(parents=True,exist_ok=True)
    packages={n:importlib.metadata.version(n) for n in ['torch','torchaudio','speechbrain','numpy','soundfile']}
    identity_data={'pipeline':'original encode_batch(normalize=False) + L2; concatenated enrollment v1',
                   'model':{p.name:digest(p) for p in args.model_dir.iterdir() if p.suffix in {'.yaml','.ckpt'}},
                   'source_sha256':digest(SOURCE/'voiceprint_core.py'),
                   'evaluator_sha256':digest(Path(__file__)), 'packages':packages,
                   'device_requested':args.device,'threads':args.threads}
    identity=hashlib.sha256(json.dumps(identity_data,sort_keys=True).encode()).hexdigest()
    cache=args.output/'cache'/identity
    cache.mkdir(parents=True,exist_ok=True)
    lists_hash={p.name:digest(p) for p in (root/'lists').glob('*.lst')}
    save_json(args.output/'run_config.json',{'identity':identity_data,'cache_id':identity,
        'eval_root':str(root),'list_sha256':lists_hash,'subset':subset,
        'enrollment_method':'one embedding of each complete official concatenated enrollment recording',
        'audio_policy':'complete recordings; no cropping, chunk averaging, VAD or score normalization',
        'note':'No low-RMS exclusion; invalid audio fails explicitly rather than deleting trials'})
    timing=extract_all(args,root,enrollment,tests,cache,identity)
    print('[SCORE] Computing official trial scores',flush=True)
    scores,labels,total=score_trials(root,enrollment,tests,cache,args.output,subset)
    metrics,thresholds,far,frr=detection_metrics(scores,labels,args.p_target,args.c_miss,args.c_fa,args.threshold)
    metrics.update({'subset_smoke_test':subset,'official_list_trials':total,
                    'enrollment_recordings':len(enrollment),'test_recordings':len(tests),
                    'timing':timing,'scope':'PC software baseline, not PYNQ/FPGA benchmark'})
    save_json(args.output/'metrics.json',metrics)
    # Compact DET sample for plotting; exact EER/minDCF use all grouped points.
    indices=np.unique(np.r_[np.linspace(0,len(far)-1,min(2000,len(far)),dtype=int),np.argmin(np.abs(far-frr))])
    np.savez(args.output/'det_curve.npz',thresholds=thresholds[indices],far=far[indices],frr=frr[indices])
    print(json.dumps(metrics,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':
    main()
