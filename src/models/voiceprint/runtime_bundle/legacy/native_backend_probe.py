"""User-run ARM native ORT gate: complete recordings and one-layer CPU reconstruction.
No Overlay, FPGA allocation, network access, pip install, or model simplification.
"""
from pathlib import Path
import argparse
import json
import platform
import sys
import time
import numpy as np
from runtime_core import HERE,BUNDLE,FullCPU,Hybrid,frontend,compare,normalize,save,verify_manifest,digest
from native_ort_bridge import backend_details


def parity(reference,actual):
    metric=compare(reference,actual)
    return {**metric,'pass':bool(np.allclose(reference,actual,atol=1e-4,rtol=1e-3)
                                and metric['cosine']>=0.99999)}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    if platform.system()!='Linux' or platform.machine().lower() not in ('armv7l','armv8l'):
        parser.error('Execute manually on PYNQ-Z2 ARM Linux')
    directory=args.output.resolve()
    if not directory.is_relative_to(HERE):
        parser.error('Output must stay in full_model_test')
    directory.mkdir(parents=True,exist_ok=True)
    result={'scope':'actual board full CPU inference and one-layer software reconstruction; no FPGA',
        'fpga_executed':False,'performance_claim':False,'cpu_available':False,'frontend_pass':False,
        'python':sys.version,'platform':platform.platform(),'numpy_version':np.__version__,
        'threads':1,'timing_clock':'perf_counter','audio':[]}
    runtime=None;candidate=None
    try:
        result['bundle_version']=verify_manifest()
        result['backend']=backend_details()
        result['model_sha256']=digest(BUNDLE/'camplus_int8_qdq.onnx')
        start=time.perf_counter();runtime=FullCPU(1)
        result['model_load_ms']=(time.perf_counter()-start)*1000
        protocol=json.loads((BUNDLE/'smoke_protocol.json').read_text(encoding='utf-8'))
        saved=[]
        for audio in protocol['audio']:
            features,timing=frontend(BUNDLE/audio['path'],'numpy16k')
            golden_features=np.load(BUNDLE/audio['features'],allow_pickle=False)
            if features.shape!=golden_features.shape:
                raise AssertionError('Fbank shape mismatch')
            difference=np.abs(features-golden_features)
            if difference.max()>1e-4 or difference.mean()>1e-5:
                raise AssertionError('Fbank equivalence gate failed')
            # Isolate library/architecture drift using precisely the same stored Fbank first.
            original_features_embedding,gold_timing=runtime.run(golden_features)
            desktop=np.load(BUNDLE/'audio'/(audio['id']+'.desktop_qdq_embedding.npy'),allow_pickle=False)
            desktop_compare=parity(desktop,original_features_embedding)
            # Then run the actual read/decode/Fbank/full model chain, without cached layer inputs.
            embedding,network_timing=runtime.run(features)
            normalized=normalize(embedding)
            row={'audio':audio['id'],'audio_sha256':digest(BUNDLE/audio['path']),
                 'frames':features.shape[1],'embedding_shape':list(embedding.shape),
                 'embedding_norm':float(np.linalg.norm(embedding)),
                 'fbank':{'max_abs':float(difference.max()),'mean_abs':float(difference.mean())},
                 'desktop_reference_same_fbank':desktop_compare,
                 'fbank_implementation_embedding_effect':compare(original_features_embedding,embedding),
                 'timing':{**timing,**network_timing},'same_fbank_timing':gold_timing}
            np.save(directory/(audio['id']+'.raw_embedding.npy'),embedding)
            np.save(directory/(audio['id']+'.normalized_embedding.npy'),normalized)
            result['audio'].append(row);saved.append((audio,features,embedding))
            save(directory/'native_cpu_gate.json',result)
            print('[FULL CPU]',audio['id'],'embedding',embedding.shape,'norm',row['embedding_norm'],flush=True)
            print('  desktop same-Fbank cosine:',desktop_compare['cosine'],'max_abs:',desktop_compare['max_abs'],flush=True)
        runtime.close();runtime=None
        result['frontend_pass']=True;result['cpu_available']=True
        reconstruction=[]
        for mode in ('bypass','integer'):
            candidate=Hybrid('one',mode,1)
            for audio,features,reference in saved:
                embedding,report=candidate.run(features,audit=True)
                metric=parity(reference,embedding) if mode=='bypass' else compare(reference,embedding)
                if mode=='integer':
                    metric['pass']=bool(metric['cosine']>=0.99999 and metric['relative_l2']<=0.01)
                reconstruction.append({'audio':audio['id'],'mode':mode,**metric,'layers':report['layers']})
                print('[ONE LAYER SOFTWARE]',mode,audio['id'],'pass',metric['pass'],flush=True)
            candidate.close();candidate=None
        result['one_layer_software']=reconstruction
        result['one_layer_bypass_pass']=all(x['pass'] for x in reconstruction if x['mode']=='bypass')
        result['one_layer_integer_pass']=all(x['pass'] for x in reconstruction if x['mode']=='integer')
        result['desktop_reference_gate']=all(x['desktop_reference_same_fbank']['pass'] for x in result['audio'])
        result['pass']=result['frontend_pass'] and result['cpu_available'] and result['one_layer_bypass_pass']
        result['next']='Return this report before FPGA. Desktop numerical drift and integer replacement are separate diagnostics; existing one-layer FPGA gates remain required.'
        save(directory/'native_cpu_gate.json',result)
        if not result['pass']:
            raise AssertionError('Native CPU reconstruction gate failed')
        print('FULL_CPU_BACKEND_PASS: 3/3',flush=True)
        print('ONE_LAYER_CPU_RECONSTRUCTION_PASS: 3/3',flush=True)
        print('DESKTOP_REFERENCE_GATE:',result['desktop_reference_gate'],flush=True)
        print('SOFTWARE_INTEGER_ONE_GATE:',result['one_layer_integer_pass'],flush=True)
        print('REPORT:',directory/'native_cpu_gate.json',flush=True)
    except Exception as error:
        result['error']=repr(error)
        result['pass']=False
        save(directory/'native_cpu_gate.json',result)
        raise
    finally:
        if runtime:
            runtime.close()
        if candidate:
            candidate.close()
    return directory


if __name__=='__main__':
    main()
