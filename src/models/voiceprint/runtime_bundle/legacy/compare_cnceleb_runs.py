"""Compare two completed CN-Celeb runs with identical provenance/protocol.
May read user-returned board directories; report writes only into this package.
"""
from pathlib import Path
import argparse
import json
import uuid
import numpy as np
from runtime_core import HERE,compare,save


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('reference',type=Path);p.add_argument('candidate',type=Path)
    p.add_argument('--threshold',type=float);p.add_argument('--threshold-source')
    args=p.parse_args(argv)
    if args.threshold is not None and (not np.isfinite(args.threshold) or not args.threshold_source):
        p.error('Threshold requires documented calibration source')
    left,right=args.reference.resolve(),args.candidate.resolve()
    configs=[json.loads((r/'run_info.json').read_text(encoding='utf-8')) for r in (left,right)]
    for key in ('bundle_version','lists_sha256','subset','protocol','p_target','c_miss','c_fa'):
        if configs[0][key]!=configs[1][key]:
            raise ValueError('Mismatched protocol/provenance: '+key)
    for key in ('frontend','limit_enroll','limit_test'):
        if configs[0]['arguments'][key]!=configs[1]['arguments'][key]:
            raise ValueError('Mismatched selection/frontend '+key)
    metadata=[{r['audio']:r['audio_sha256'] for r in json.loads((path/'audio_metadata.json').read_text(encoding='utf-8'))} for path in (left,right)]
    if metadata[0]!=metadata[1]:
        raise ValueError('Audio content differs')
    a=np.load(left/'trial_scores.npz');b=np.load(right/'trial_scores.npz')
    if not np.array_equal(a['labels'],b['labels']) or a['scores'].shape!=b['scores'].shape:
        raise ValueError('Trial label/order mismatch')
    d=b['scores'].astype(np.float64)-a['scores'].astype(np.float64)
    vectors=[]
    for source in sorted((left/'embeddings').glob('*.npy')):
        target=right/'embeddings'/source.name
        vectors.append({'key':source.stem,**compare(np.load(source),np.load(target))})
    decisions=None
    if args.threshold is not None:
        changed=(a['scores']>=args.threshold)!=(b['scores']>=args.threshold)
        near=np.abs(a['scores']-args.threshold)<=0.02
        decisions={'threshold':args.threshold,'source':args.threshold_source,'changed_trials':int(changed.sum()),
                   'near_threshold_trials':int(near.sum()),'near_threshold_changed':int(np.sum(near&changed))}
    directory=HERE/'test_results'/('comparison_'+uuid.uuid4().hex)
    save(directory/'comparison.json',{'reference':str(left),'candidate':str(right),'configs':configs,
        'normalized_embedding':vectors,'score_max_abs_delta':float(np.abs(d).max()),
        'score_mean_abs_delta':float(np.abs(d).mean()),'score_mean_signed_delta':float(d.mean()),
        'trial_count':len(d),'decision_comparison':decisions,
        'metrics':[json.loads((r/'metrics.json').read_text(encoding='utf-8')) for r in (left,right)],
        'note':'Identical lists/audio/frontend verified; accuracy scope follows subset/full flag, mode and host.'})
    print('COMPARISON report:',directory)
    return directory


if __name__=='__main__':
    main()
