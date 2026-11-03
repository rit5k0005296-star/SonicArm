"""Desktop-only notebook/manifest/archive builder; never connects to board."""
from pathlib import Path
import ast
import hashlib
import json
import zipfile

WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[1]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def cell(kind, source):
    value = dict(cell_type=kind, metadata={}, source=source.splitlines(True))
    if kind == 'code':
        ast.parse(source)
        value.update(execution_count=None, outputs=[])
    return value


def main():
    cells = [cell('markdown', '''# 07 CPU 子图优化对照与逐层耗时

在电脑解压，将整个 `optimization_profile` 文件夹复制到已有 `full_model_test/evaluation/`，与 `benchmark_compare` 同级。由你手动运行，不安装依赖、不改原模型或硬件。

先关闭其他使用 FPGA 的 Notebook，重启本 Notebook 内核。顺序执行；遇到异常停止，返回完整输出。若硬件执行中超时或中断，保持内核直到开发板断电重启，之后再重启内核。不要强制结束硬件子进程或在运行中切换 Overlay。
'''), cell('code', '''from pathlib import Path
import sys, uuid
sys.dont_write_bytecode=True
WORK=Path.cwd().resolve()
assert WORK.name=='optimization_profile' and (WORK/'optimization_profile.py').is_file(), '请在evaluation/optimization_profile中打开本Notebook'
sys.path.insert(0,str(WORK))
from optimization_profile import setup, correctness, profile, benchmark
PREVIOUS_RUN=WORK.parent/'benchmark_compare/results/run_c44659411d5d4285b8888dc237a52a67'
RUN=WORK/'results'/('run_'+uuid.uuid4().hex)
PROFILE_REPEATS=3
REPEATS=10  # 正式测量总次数/模式/查询；可改20，必须为偶数
WARMUP=2
setup_report=setup(RUN,PREVIOUS_RUN)
print('本次结果目录：',RUN)
'''), cell('markdown', '''## 1. 先剖析当前版本：CPU 子图与 FPGA 各层

这一步仅使用现有 CPU INT8、V3 OFF 和 V4 OFF，复用上一轮已经通过的真实硬件验证；每次输出还必须与上一轮同模式向量完全一致。不必先运行新的优化模式。

记录 V3 的 56 个 CPU 会话、V4 的 57 个 CPU 会话，以及 55/67 个 FPGA 层。完整输入输出尺寸和字节在 `baseline_profile_raw.json`，汇总在 `baseline_profile_summary.csv`。

出现 `BASELINE_PROFILE_COMPLETED` 后，可先返回 `BASELINE_PROFILE_TOP` 和这两个文件，定位现有瓶颈。后面的单元格用于进一步验证优化收益。
'''), cell('code', 'baseline_profile=profile(RUN,repeats=PROFILE_REPEATS,warmup=1,baseline_only=True)\n'),
        cell('markdown', '''## 2. CPU 子图优化 OFF/ON 正确性门控

检查 CPU 子图优化 OFF/ON 的向量与评分变化，并对四个混合模式分别比较软件整数参考与真实 FPGA 的逐层 INT8/INT32。

出现 `OPT_ENGINEERING_READY` 才继续。`OPTIMIZATION_DRIFT_GATE` 或 `ORIGINAL_QDQ_DRIFT_GATE` 为 false 时保留失败；工程测速可用于定位性能，但不能宣称精度一致或鉴权通过。此阶段参考计算可能较久，In [*] 时等待，不要重复运行。
'''), cell('code', 'correctness_report=correctness(RUN)\n'),
        cell('markdown', '''## 3. 优化前后的逐层剖析

记录 V3 的 56 个 CPU 会话、V4 的 57 个 CPU 会话，以及 55/67 个 FPGA 层；同时记录输入输出数量、尺寸和字节数。CPU 完整模型也保留一个会话作为对照。

默认每条查询预热 1 次、剖析 3 次。`PROFILE_TOP` 输出最慢八项。完整明细在 `profile_raw.json`，汇总在 `profile_summary.csv`。剖析 wall time 包含收集元数据的开销，不作为正式速度结论。
'''), cell('code', 'profile_report=profile(RUN,repeats=PROFILE_REPEATS,warmup=1)\n'),
        cell('markdown', '''## 4. 关闭详细剖析，正式比较优化前后速度

模式：完整 INT8 CPU、V3 OFF/ON、V4 OFF/ON，均为 1 线程、原完整 Fbank。一次只保留一个模式，分两轮反序测量。整数参考、INT32 调试及逐层审计关闭；仍核对向量稳定和实际调用数量。

输出中 `V3_OFF_over_ON` / `V4_OFF_over_ON` >1 表示 CPU 图优化后更快；`CPU_INT8_over_V4_ON` >1 才表示第四版优化后超过完整 INT8 CPU。本单元格也可能需要较长时间，等待完成。
'''), cell('code', 'performance_report=benchmark(RUN,repeats=REPEATS,warmup=WARMUP)\n'),
        cell('markdown', '''请返回：

- 先返回 `BASELINE_PROFILE_TOP`、`baseline_profile_raw.json`、`baseline_profile_summary.csv`
- 完成后续优化对照时，再返回 `OPTIMIZATION_DRIFT_GATE`、`ORIGINAL_QDQ_DRIFT_GATE`
- `PROFILE_TOP`、`OPT_SPEEDUP_COMPARE`
- 本次 `results/run_编号/` 中的 `profile_raw.json`、`profile_summary.csv`、`performance.json`、`correctness.json`

原 06 的文件和结果均保留。此测试不采集 LINE IN，不包含音频读取/Fbank 时间，不输出未经校准的身份决策。
''')]
    notebook = dict(nbformat=4, nbformat_minor=4,
                    metadata=dict(kernelspec=dict(name='python3', display_name='Python 3 (ipykernel)', language='python')),
                    cells=cells)
    nb = WORK / '07_cpu_graph_optimization_profile.ipynb'
    nb.write_text(json.dumps(notebook, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    files = {name: sha(WORK / name) for name in ('optimization_profile.py', 'README.md')}
    sources = [''.join(c['source']) for c in cells if c['cell_type'] == 'code']
    files[nb.name] = hashlib.sha256(json.dumps(sources, ensure_ascii=False).encode('utf8')).hexdigest()
    manifest = dict(version='optimization_profile_2', files=files, notebook_cells={nb.name: sources},
                    comparison_manifest_sha256=sha(WORK.parent / 'benchmark_compare/manifest.json'),
                    actual_board_tested=False)
    (WORK / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf8')
    archive = ROOT / 'updates/cpu_optimization_profile.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for name in [*files, 'manifest.json']:
            z.write(WORK / name, 'optimization_profile/' + name)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise AssertionError('Archive corruption')
    print('OPT_PACKAGE_READY', archive, archive.stat().st_size, sha(archive), flush=True)


if __name__ == '__main__':
    main()
