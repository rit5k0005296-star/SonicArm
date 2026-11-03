"""Manual board probe. No SSH, network, pip install, Overlay or FPGA allocation.
Native imports/model execution run in child processes so failures are recorded.
"""
from pathlib import Path
import json
import os
import platform
import subprocess
import sys
import sysconfig
import time
import uuid
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent


def probe():
    result_dir=HERE/'test_results'/('probe_'+uuid.uuid4().hex)
    result_dir.mkdir(parents=True)
    def child(code,timeout=120):
        start=time.perf_counter()
        try:
            local_deps=str(HERE/'_board_deps')
            python_path=os.pathsep.join([local_deps,os.environ.get('PYTHONPATH','')])
            proc=subprocess.run([sys.executable,'-B','-c',code],cwd=str(HERE),capture_output=True,
                text=True,timeout=timeout,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':python_path})
            return {'returncode':proc.returncode,'stdout':proc.stdout[-24000:],'stderr':proc.stderr[-12000:],
                    'elapsed_seconds':time.perf_counter()-start,'pass':proc.returncode==0}
        except subprocess.TimeoutExpired as error:
            return {'pass':False,'error':'timeout '+str(timeout),'stdout':str(error.stdout)[-4000:]}
    data={'run_id':result_dir.name,'scope':'environment/full CPU probe; no FPGA execution',
          'platform':platform.platform(),'machine':platform.machine(),'python':sys.version,
          'executable':sys.executable,'SOABI':sysconfig.get_config_var('SOABI'),
          'wall_clock_untrusted':time.strftime('%Y-%m-%d %H:%M:%S'),
          'timing_clock':'perf_counter','packages':{},'host_reads':{}}
    for name in ('numpy','soundfile','onnxruntime','torch','torchaudio','pynq'):
        data['packages'][name]=child("import importlib; m=importlib.import_module("+repr(name)+
            "); print(getattr(m,'__version__','unknown'));print(getattr(m,'__file__',None))",60)
    for path in ('/proc/cpuinfo','/proc/meminfo','/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq',
                 '/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor','/proc/sys/vm/overcommit_memory'):
        try:
            data['host_reads'][path]=Path(path).read_text()[:24000]
        except OSError as error:
            data['host_reads'][path]={'unavailable':str(error)}
    data['pip_tags']=child('import subprocess,sys; subprocess.run([sys.executable,"-m","pip","debug","--verbose"],check=True)',30)
    data['full_cpu']=child("from runtime_core import *; version=verify_manifest(); "
        "p=json.loads((BUNDLE/'smoke_protocol.json').read_text()); "
        "f=np.load(BUNDLE/p['audio'][0]['features']); t=time.perf_counter(); "
        "r=FullCPU(1); print('load_ms',(time.perf_counter()-t)*1000); "
        "e,report=r.run(f); print('version',version,'embedding',e.shape,'norm',np.linalg.norm(e),'timing',report); "
        "assert e.shape==(1,192) and np.isfinite(e).all(); r.close()",300)
    if (HERE/'_native_ort/manifest.json').is_file() and platform.system()=='Linux' and platform.machine().lower() in ('armv7l','armv8l'):
        data['native_backend']=child("import json; from native_ort_bridge import backend_details; "
            "print(json.dumps(backend_details(),ensure_ascii=False,indent=2))",60)
        data['backend_note']='Native ORT C API is selected on ARM. The separate Python onnxruntime package may remain absent; full_cpu execution gate is authoritative.'
    for kind in ('canonical','numpy16k'):
        data['frontend_'+kind]=child("from runtime_core import *; "
            "p=json.loads((BUNDLE/'smoke_protocol.json').read_text()); "
            "a=p['audio'][0]; f,tm=frontend(BUNDLE/a['path'],"+repr(kind)+
            "); ref=np.load(BUNDLE/a['features']); "
            "d=np.abs(f-ref); print('shape',f.shape,'max_abs',d.max(),'mean_abs',d.mean(),'timing',tm); "
            "assert f.shape==ref.shape and d.max()<=1e-4 and d.mean()<=1e-5",120)
    data['gate']={'board_arm_linux':platform.system()=='Linux' and platform.machine().lower() in ('armv7l','armv8l'),
        'full_cpu_available':data['full_cpu']['pass'],
        'canonical_frontend':data['frontend_canonical']['pass'],
        'numpy16k_frontend':data['frontend_numpy16k']['pass'],
        'next':'Run CPU/one-layer correctness only if full CPU and chosen frontend pass. Otherwise return this report; do not install desktop Windows libraries on board.'}
    (result_dir/'environment.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Report:',result_dir/'environment.json')
    print(json.dumps(data['gate'],ensure_ascii=False,indent=2))
    return result_dir


if __name__=='__main__':
    probe()
