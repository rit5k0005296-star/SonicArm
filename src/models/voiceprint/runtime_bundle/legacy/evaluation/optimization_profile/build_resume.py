"""Create a standalone resume entry point, preserving 07 and all manifests."""
from pathlib import Path
import ast
import hashlib
import json
import zipfile

WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[1]


def cell(kind, source):
    value = dict(cell_type=kind, metadata={}, source=source.splitlines(True))
    if kind == 'code':
        ast.parse(source)
        value.update(execution_count=None, outputs=[])
    return value


def main():
    cells = [cell('markdown', '''# 08 恢复已有 RUN，仅继续正式测速

将本文件放在已有 `full_model_test/evaluation/optimization_profile/`，由你手动打开执行。依赖已修复空行校验的 v2 测试包。保持原 07 Notebook 内容不变。

旧 RUN 已完成正确性与逐层剖析。本入口仅恢复变量和检查已有凭据，不重跑它们。先确认其他 Notebook 没有正在使用 FPGA。普通 NameError 不表示硬件超时；若另有硬件超时或活跃硬件中断，仍应先对板卡断电重启。
'''), cell('code', '''from pathlib import Path
import sys
sys.dont_write_bytecode=True
WORK=Path.cwd().resolve()
assert WORK.name=='optimization_profile' and (WORK/'optimization_profile.py').is_file(), '请在evaluation/optimization_profile目录中打开'
sys.path.insert(0,str(WORK))
from optimization_profile import benchmark, check_gate
RUN=WORK/'results'/'run_2348265b8eca4b48917ec3050039f912'
REPEATS=10
WARMUP=2
RUN, gate_report=check_gate(RUN)
print('RESUME_READY:',RUN)
print('OPTIMIZATION_DRIFT_GATE:',gate_report['optimization_drift_gate'])
print('ORIGINAL_QDQ_DRIFT_GATE:',gate_report['original_QDQ_drift_gate'])
print('只恢复既有结果，不重新运行正确性或逐层剖析。')
'''), cell('markdown', '''出现 `RESUME_READY` 后运行下一格。它将复用已验证的同模式向量，关闭详细剖析和整数审计，按两轮反序进行正式测速。

完整 INT8 CPU、V3 OFF/ON、V4 OFF/ON，每条查询合计 10 次，预热次数为每轮每条查询 2 次。估计 15～30 分钟，实际取决于优化模式速度和初始化时间。In [*] 时等待，不要重复点击，不要跨 Notebook 并行运行。

已有数值漂移失败继续保留，完成工程测速不等于精度一致或正式鉴权通过。
'''), cell('code', 'performance_report=benchmark(RUN,repeats=REPEATS,warmup=WARMUP)\n'),
        cell('markdown', '''完成标记：`OPT_BENCHMARK_COMPLETED`。返回 `OPT_SPEEDUP_COMPARE` 和本 RUN 中的 `performance.json`、`raw_samples.json`。原来的 `correctness.json`、`profile_raw.json` 和 `profile_summary.csv` 保留。若出现错误，停止并返回完整输出。
''')]
    name = '08_resume_optimization_benchmark.ipynb'
    nb = dict(nbformat=4, nbformat_minor=4, cells=cells,
              metadata=dict(kernelspec=dict(name='python3', display_name='Python 3 (ipykernel)', language='python')))
    (WORK/name).write_text(json.dumps(nb, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    archive = ROOT/'updates/optimization_benchmark_resume.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(WORK/name, 'optimization_profile/'+name)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() or z.namelist() != ['optimization_profile/'+name]:
            raise AssertionError('Bad resume archive')
    print('RESUME_NOTEBOOK_READY',archive,archive.stat().st_size,hashlib.sha256(archive.read_bytes()).hexdigest())


if __name__=='__main__':
    main()
