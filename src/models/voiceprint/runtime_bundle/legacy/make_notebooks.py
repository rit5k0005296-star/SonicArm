"""Generate clean manual notebooks. No cells are executed here."""
from pathlib import Path
import json
HERE=Path(__file__).resolve().parent


def markdown(s):
    return {'cell_type':'markdown','metadata':{},'source':s.splitlines(True)}


def code(s):
    return {'cell_type':'code','metadata':{},'source':s.splitlines(True),'execution_count':None,'outputs':[]}


def notebook(name,cells):
    document={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},
        'language_info':{'name':'python','version':'3.10'}},'cells':cells}
    for i,cell in enumerate(cells):
        cell['id']='cell-'+str(i)
    (HERE/name).write_text(json.dumps(document,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')


setup="""import sys
from pathlib import Path
sys.dont_write_bytecode = True
ROOT = Path.cwd().resolve()
assert (ROOT / 'bundle').is_dir(), '请在上传后的 full_model_test 目录中打开 Notebook'
sys.path.insert(0, str(ROOT))
from runtime_core import verify_manifest
print('包版本:', verify_manifest())
# 初始 3 个例子均为 16k。numpy16k 需先通过 00 的原 Fbank 一致性门控。
# 任意采样率/官方完整评测优先 canonical，需要板卡自身可用的 torch/torchaudio。
FRONTEND = 'numpy16k'
THREADS = 1
"""


def main():
    notebook('00_environment_probe.ipynb',[
        markdown('# 00 板卡环境探测\n由你手动执行。只读环境、导入运行库、执行完整 CPU 模型和前处理；不加载 Overlay、不访问 FPGA、不安装依赖。若原生库缺失、崩溃、超时，保留 environment.json。'),
        code("import sys\nfrom pathlib import Path\nsys.dont_write_bytecode=True\nROOT=Path.cwd().resolve()\nassert (ROOT/'probe_environment.py').is_file()\nsys.path.insert(0,str(ROOT))\nfrom probe_environment import probe\nprobe_dir=probe()"),
        code("import json\nreport=json.loads((probe_dir/'environment.json').read_text())\nprint(json.dumps(report['gate'],ensure_ascii=False,indent=2))\nprint('将此目录的 environment.json 返回桌面分析:',probe_dir)"),
        markdown('只有 full_cpu_available=true 且所选 frontend=true 才继续。若缺少 ORT，先带回报告，准备匹配 ARMv7/Linux/CPython3.10/glibc 的运行库或源码构建；Windows DLL、ARM64 wheel 不可代用。不要在此 Notebook 盲目 pip install。')])
    notebook('01_complete_cpu.ipynb',[
        markdown('# 01 完整 CPU 闭环\n执行完整音频读取、Fbank、完整 CAM++、192 维 embedding、L2 和有标签的两个声纹试验。优化关闭/开启都保留。未校准阈值，只输出分数。'),
        code(setup),code("from run_full_model import main\ncpu_run=main(['--mode','cpu','--frontend',FRONTEND,'--threads',str(THREADS)])"),
        markdown('结果在唯一 run_* 目录。正式鉴权仍为 null。先查看 correctness.json 的 Fbank 检查、scores 和 optimization_audit。')])
    notebook('02_one_layer_fpga.ipynb',[
        markdown('# 02 一个层真实接入\n**本 Notebook 会由你手动加载第三版 Overlay 并调用 FPGA。** 首层使用真实当前 CPU 中间张量。先验证原 ONNX 切分、软件整数替换，再验证 FPGA INT32 调试及关闭调试两条路径。'),
        code(setup),code("from run_full_model import main\none_run=main(['--mode','fpga','--plan','one','--frontend',FRONTEND,'--threads',str(THREADS)])"),
        markdown('只有 correctness pass=true 才继续计时。此单元会重新做正确性门控后再测量，预热3次、正式20次。完整模型 ORT优化开启/关闭的耗时均保留，开启优化若数值不等价会明确标记其比值不满足精度匹配。'),
        code("one_timing=main(['--mode','fpga','--plan','one','--frontend',FRONTEND,'--threads',str(THREADS),'--benchmark','--warmup','3','--repeats','20'])"),
        markdown('返回整个 run_* 目录。每层逐次重写全部指针和标量。若超时，禁止继续复用 IP/释放仍在访问的 DDR；重启板卡后再测试。')])
    notebook('03_all55_diagnostic.ipynb',[
        markdown('# 03 55 层连续接入：目前先做诊断\n**已知桌面 all55 整数模型在一段例子上未通过原 QDQ embedding 漂移门控。** 所以本阶段先保存数值与逐层报告，不启动计时。不会放宽门控。需要同版本 02 的单层 FPGA 正确性通过。'),
        code(setup),code("from run_full_model import main\n# 若触发门控，预期会抛 AssertionError；日志里会打印结果目录。\nall55_run=main(['--mode','fpga','--plan','all55','--frontend',FRONTEND,'--threads',str(THREADS)])"),
        markdown('查看失败目录的 correctness.json、layers/integer、layers/fpga_debug 和 layers/fpga，区分整数相对 QDQ 的传播与 FPGA 相对整数的错误。只有 all55 pass=true 后，才可给同样参数增加 --benchmark；当前不要执行55层性能测试。')])
    notebook('04_cnceleb_protocol.ipynb',[
        markdown('# 04 原 CN-Celeb 协议\n先小规模，再完整。保留官方 enroll.lst/test.lst/trials.lst、完整注册录音与 L2 余弦评分。下列默认只执行 CPU；修改配置后由你手动执行。numpy16k 遇到非16k会停止，不静默重采样。'),
        code(setup),code("EVAL_ROOT=Path('/home/xilinx/jupyter_notebooks/SonicArm/CN-Celeb_flac/eval')\nassert (EVAL_ROOT/'lists/enroll.lst').is_file(), '填写实际评测数据目录'\nMODE='cpu_optimized'\nPLAN='one'\nLIMIT_ENROLL=2\nLIMIT_TEST=50\n# 与此前评测一样优先 canonical；没有板载 torch 时仅对确认全部16k的数据用 numpy16k。\nfrom evaluate_full_cnceleb import main\ncn_run=main(['--eval-root',str(EVAL_ROOT),'--mode',MODE,'--plan',PLAN,'--frontend',FRONTEND,'--threads',str(THREADS),'--limit-enroll',str(LIMIT_ENROLL),'--limit-test',str(LIMIT_TEST)])"),
        markdown('小规模子集可能没有同时包含正负标签，此时指标计算会明确停止，需要增大子集；不能删试验来凑指标。正式完整评测将两个 limit 改为0。FPGA/整数先要求同版本 smoke 门控通过；研究55层数值传播对EER的影响时可显式用 --diagnostic-evaluation，只作精度诊断。不要用本次评测耗时当20次性能基准。')])
    notebook('05_numerical_diagnosis.ipynb',[
        markdown('# 05 连续整数误差传播定位\nCPU 数值诊断，比较同一音频的完整原图边界和当前整数前向边界。不是 FPGA 结果。'),
        code(setup),code("from diagnose_propagation import diagnose\ndiagnostic_dir=diagnose(FRONTEND)"),
        markdown('input_vs_full_original 显示上游误差，integer_vs_QDQ_same_current_input 显示该层自身舍入差异，output_vs_full_original 显示该层累计输出差异。')])
    print('Generated 6 manual notebooks; no execution')


if __name__=='__main__':
    main()
