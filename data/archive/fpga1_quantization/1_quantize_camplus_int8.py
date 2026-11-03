"""Static PTQ QDQ INT8 convolution experiment; calibration uses dev speakers only."""
from pathlib import Path
import argparse
import json
import random
import sys
from collections import Counter
import numpy as np
from common import HERE, PYNQ, MODEL, EVAL, audio_features, import_runtime, session, output_path, save_json, sha256


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--onnx',type=Path,default=MODEL)
    parser.add_argument('--dataset',type=Path,default=EVAL.parent)
    parser.add_argument('--output',type=Path,default=HERE/'artifacts/quantization/camplus_int8_qdq.onnx')
    parser.add_argument('--samples',type=int,default=128)
    parser.add_argument('--seed',type=int,default=20261010)
    parser.add_argument('--seconds',type=float,default=0.,help='0: full calibration recordings; >0: optional feature crop')
    parser.add_argument('--method',choices=['minmax','entropy','percentile'],default='minmax')
    parser.add_argument('--per-tensor',action='store_true',help='Use per-tensor weights instead of per-channel')
    args=parser.parse_args()
    if args.samples<1 or args.seconds<0: parser.error('Invalid samples/seconds')
    import_runtime('cpu')
    import torch
    import onnx
    from onnxruntime.quantization import (CalibrationDataReader, quantize_static, QuantFormat,
                                         QuantType, CalibrationMethod)
    from onnxruntime.quantization.shape_inference import quant_pre_process
    torch.set_num_threads(4)
    sys.path.append(str(PYNQ))
    from evaluate_cnceleb import load_lists
    root=args.dataset.resolve()
    enrollment,tests=load_lists(root/'eval')
    eval_ids={n.removesuffix('-enroll') for n in enrollment}
    eval_ids.update(Path(n).stem.split('-')[0] for n in tests)
    dev_ids=[n.strip() for n in (root/'dev/dev.lst').read_text().splitlines() if n.strip()]
    if eval_ids.intersection(dev_ids): raise ValueError('Development/evaluation speakers overlap')
    rng=random.Random(args.seed)
    rng.shuffle(dev_ids)
    if args.samples>len(dev_ids): parser.error('samples must not exceed development speaker count')
    selected=[]
    for speaker in dev_ids[:args.samples]:
        directory=(root/'data'/speaker).resolve()
        if not directory.is_relative_to((root/'data').resolve()): raise ValueError('Unsafe speaker path')
        paths=sorted([*directory.glob('*.flac'),*directory.glob('*.wav')])
        if not paths: raise FileNotFoundError('No development audio: '+str(directory))
        selected.append((speaker,rng.choice(paths)))
    provenance=json.loads(args.onnx.with_suffix('.export.json').read_text(encoding='utf-8'))
    if provenance['onnx_sha256']!=sha256(args.onnx): raise ValueError('FP32 hash mismatch')
    output=output_path(args.output)
    prepared=output.with_suffix('.prepared.onnx')
    # Keep optimization separate. Preserve source model; run shape inference only here.
    quant_pre_process(str(args.onnx),str(prepared),skip_optimization=True,skip_symbolic_shape=True)
    records=[]

    class Reader(CalibrationDataReader):
        def __init__(self): self.index=0
        def get_next(self):
            if self.index>=len(selected): return None
            speaker,path=selected[self.index]
            feat=audio_features(path)
            complete_frames=feat.shape[1]
            if args.seconds:
                frames=max(20,round(args.seconds*100))
                start=rng.randrange(max(1,complete_frames-frames+1))
                feat=feat[:,start:start+frames,:].copy()
            records.append({'speaker':speaker,'path':str(path),'audio_sha256':sha256(path),
                            'full_frames':complete_frames,'calibration_frames':feat.shape[1]})
            self.index+=1
            print(f'[CALIBRATION] {self.index}/{len(selected)} {speaker} T={feat.shape[1]}',flush=True)
            return {'features':feat}

    method={'minmax':CalibrationMethod.MinMax,'entropy':CalibrationMethod.Entropy,
            'percentile':CalibrationMethod.Percentile}[args.method]
    quantize_static(str(prepared),str(output),Reader(),quant_format=QuantFormat.QDQ,
                    op_types_to_quantize=['Conv'],per_channel=not args.per_tensor,
                    activation_type=QuantType.QInt8,weight_type=QuantType.QInt8,
                    calibrate_method=method,calibration_providers=['CPUExecutionProvider'],
                    extra_options={'WeightSymmetric':True,'ActivationSymmetric':False})
    graph=onnx.load(str(output)); onnx.checker.check_model(graph,full_check=True)
    counts=Counter(n.op_type for n in graph.graph.node)
    if not counts['QuantizeLinear'] or not counts['DequantizeLinear']:
        raise RuntimeError('No quantization nodes generated')
    configuration={'method':'static PTQ QDQ','calibration':args.method,
                   'weight':'INT8 symmetric per-tensor' if args.per_tensor else 'INT8 symmetric per-output-channel',
                   'activation':'INT8 asymmetric per-tensor','operators':['Conv'],
                   'remaining_operators':'FP32/shape; this is mixed precision, not full integer FPGA inference',
                   'sample_count':args.samples,'seed':args.seed,'crop_seconds':args.seconds}
    metadata={**provenance,'onnx_sha256':sha256(output),'parent_fp32_sha256':sha256(args.onnx),
              'quantization':configuration,'calibration_records':records,
              'quantizer_version':import_runtime('cpu').__version__}
    save_json(output.with_suffix('.export.json'),metadata)
    # Runtime smoke test on the first selected development recording, never the eval set.
    feature=audio_features(selected[0][1])
    if args.seconds: feature=feature[:,:max(20,round(args.seconds*100)),:].copy()
    reference=session(args.onnx).run(['embedding'],{'features':feature})[0]
    actual=session(output).run(['embedding'],{'features':feature})[0]
    if actual.shape!=(1,192) or not np.isfinite(actual).all() or np.linalg.norm(actual)<1e-12:
        raise RuntimeError('Quantized model generated invalid embedding')
    a=reference.astype(np.float64).reshape(-1); b=actual.astype(np.float64).reshape(-1)
    report={'configuration':configuration,'operators':dict(counts),
            'fp32_bytes':args.onnx.stat().st_size,'int8_bytes':output.stat().st_size,
            'smoke_runtime_pass':True,'smoke_embedding_cosine':float(a@b/(np.linalg.norm(a)*np.linalg.norm(b))),
            'note':'Calibration and one development audio only; no full EER/minDCF validation yet'}
    save_json(output.with_suffix('.quantization_report.json'),report)
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__': main()
