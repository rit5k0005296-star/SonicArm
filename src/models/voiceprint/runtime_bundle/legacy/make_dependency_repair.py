"""Prepare a small manual dependency step, without running anything on the board."""
from pathlib import Path
import json
HERE=Path(__file__).resolve().parent


def main():
    cells=[]
    def md(source):
        cells.append({'cell_type':'markdown','metadata':{},'source':source.splitlines(True)})
    def code(source):
        cells.append({'cell_type':'code','metadata':{},'execution_count':None,'outputs':[],
                      'source':source.splitlines(True)})
    md('# 00a 先修复音频读取依赖\n由你手动运行。不加载FPGA、不安装ONNX Runtime、不升级NumPy。只在本项目的 `_board_deps` 中安装固定版本 soundfile；先检查已有CFFI和libsndfile。任一步失败就保留输出，不继续后面的单元格。')
    code("""import sys, json, uuid, ctypes, ctypes.util, importlib.util
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path.cwd().resolve()
assert (ROOT/'runtime_core.py').is_file(), '请在 full_model_test 目录中打开此 Notebook'
DEPS=ROOT/'_board_deps'
sys.path.insert(0,str(DEPS))
LOG=ROOT/'dependency_results'/('soundfile_'+uuid.uuid4().hex)
LOG.mkdir(parents=True)
sndfile=ctypes.util.find_library('sndfile')
report={'python':sys.executable,'cffi_available':False,'libsndfile':sndfile,'native_library_loadable':False}
try:
    import cffi
    cffi.FFI()
    report['cffi_available']=True
    report['cffi_version']=cffi.__version__
except Exception as error:
    report['cffi_error']=repr(error)
try:
    if sndfile:
        ctypes.CDLL(sndfile)
        report['native_library_loadable']=True
except Exception as error:
    report['libsndfile_error']=repr(error)
(LOG/'prerequisites.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
print('日志目录:',LOG)
assert report['cffi_available'] and report['native_library_loadable'], '前置依赖缺失：把以上完整输出返回；先不要运行下个单元格'
""")
    code("""import subprocess, os
DEPS.mkdir(exist_ok=True)
command=[sys.executable,'-B','-m','pip','install','--disable-pip-version-check',
         '--no-cache-dir','--no-deps','--target',str(DEPS),'soundfile==0.12.1']
# --no-deps 避免修改已验证的NumPy；不调用sudo、不修改板卡公共Python环境。
proc=subprocess.run(command,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
(LOG/'install.log').write_text(proc.stdout,encoding='utf-8')
print(proc.stdout)
assert proc.returncode==0, '安装未完成：返回完整输出，不要继续'
""")
    code('''# 在新子进程中验证，避免Notebook已经导入的模块缓存干扰。
script="""
from runtime_core import *
import soundfile as sf
print('soundfile',sf.__version__,'libsndfile',sf.__libsndfile_version__)
protocol=json.loads((BUNDLE/'smoke_protocol.json').read_text())
rows=[]
for audio in protocol['audio']:
    f,timing=frontend(BUNDLE/audio['path'],'numpy16k')
    ref=np.load(BUNDLE/audio['features'],allow_pickle=False)
    assert f.shape==ref.shape, 'Fbank shape mismatch'
    d=np.abs(f-ref)
    row={'audio':audio['id'],'shape':list(f.shape),'max_abs':float(d.max()),'mean_abs':float(d.mean())}
    rows.append(row)
    print(row,flush=True)
    assert d.max()<=1e-4 and d.mean()<=1e-5, 'Fbank equivalence gate failed'
print('NUMPY_FRONTEND_PASS: 3/3. Full CPU/FPGA still requires ONNX Runtime.')
"""
proc=subprocess.run([sys.executable,'-B','-c',script],cwd=str(ROOT),text=True,
    stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
(LOG/'frontend_validation.log').write_text(proc.stdout,encoding='utf-8')
print(proc.stdout)
assert proc.returncode==0, '前处理仍未通过：返回完整输出'
print('这一步完成。返回此输出后，再处理匹配ARMv7/Python3.10的完整模型运行库。')
''')
    md('看到 `NUMPY_FRONTEND_PASS: 3/3` 说明音频读取与这三段例子的NumPy前处理通过。还不能进入01或FPGA：ONNX Runtime尚未解决。保留 dependency_results 日志及原 test_results。soundfile依赖说明：https://pypi.org/project/soundfile/0.12.1/')
    for i,cell in enumerate(cells):
        cell['id']='audio-deps-'+str(i)
    nb={'nbformat':4,'nbformat_minor':5,'cells':cells,'metadata':{
        'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python'}}}
    (HERE/'00a_prepare_audio_dependencies.ipynb').write_text(json.dumps(nb,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    print('Created 00a_prepare_audio_dependencies.ipynb; no board code executed')


if __name__=='__main__':
    main()
