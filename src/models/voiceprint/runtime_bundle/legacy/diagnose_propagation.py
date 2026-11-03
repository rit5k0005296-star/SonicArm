"""Compare current integer trajectory with original full-network boundary tensors.
Desktop or board CPU only; not a hardware result and never a timing benchmark.
"""
import json
import time
import uuid
import numpy as np
from runtime_core import HERE,BUNDLE,Hybrid,FullCPU,ort_session,frontend,compare,normalize,save,verify_manifest


def differences(a,b):
    d=np.abs(a.astype(np.int16)-b.astype(np.int16))
    return {'changed':int(np.count_nonzero(d)),'max_lsb':int(d.max())}


def diagnose(kind='canonical'):
    directory=HERE/'test_results'/('diagnosis_'+uuid.uuid4().hex)
    directory.mkdir(parents=True)
    original=ort_session(BUNDLE/'diagnostic_boundaries.onnx')
    model=Hybrid('all55','integer',1)
    full=FullCPU(1)
    protocol=json.loads((BUNDLE/'smoke_protocol.json').read_text())
    reports=[]
    try:
        for audio in protocol['audio']:
            f,_=frontend(BUNDLE/audio['path'],kind)
            values=original.run(None,{'features':f})
            tensors=dict(zip([x.name for x in original.get_outputs()],values));rows=[]
            raw,_=full.run(f)
            materialization=compare(raw,tensors['embedding'])
            if not np.allclose(raw,tensors['embedding'],atol=1e-4,rtol=1e-3):
                raise AssertionError('Diagnostic graph changed original embedding')
            def capture(layer,x,q,gold,island):
                local=differences(gold,island)
                inp=differences(x,tensors[layer['input_tensor']])
                out=differences(q,tensors[layer['output_tensor']])
                row={'index':layer['index'],'name':layer['name'],'input_vs_full_original':inp,
                     'integer_vs_QDQ_same_current_input':local,'output_vs_full_original':out}
                if local['changed']:
                    indices=np.argwhere(gold!=island)[:16]
                    row['local_examples']=[{'index':idx.tolist(),'integer':int(gold[tuple(idx)]),
                                            'QDQ':int(island[tuple(idx)])} for idx in indices]
                rows.append(row)
            model.trace_sink=capture
            e,_=model.run(f,audit=True)
            first=next((r for r in rows if r['integer_vs_QDQ_same_current_input']['changed']),None)
            reports.append({'audio':audio['id'],'first_local_difference':first,'layers':rows,
                            'embedding':compare(tensors['embedding'],e),'diagnostic_vs_original':materialization})
            save(directory/(audio['id']+'.json'),reports[-1])
            print('[DIAGNOSIS]',audio['id'],'first local layer',first['index'] if first else None,flush=True)
    finally:
        model.close();full.close()
    save(directory/'summary.json',{'scope':'CPU numerical propagation diagnosis; no FPGA',
        'bundle_version':verify_manifest(),'audio':reports})
    print('DIAGNOSIS report:',directory)
    return directory


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--frontend',choices=['canonical','numpy16k'],default='canonical')
    diagnose(p.parse_args().frontend)
