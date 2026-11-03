"""Freeze a manual-board package only after local implementation evidence passes."""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile

ROOT = Path(__file__).resolve().parent
BOARD = ROOT / 'board_package/fpga_v5'
WORKSPACE = ROOT.parents[2]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def notebook():
    def cell(kind, text):
        row = dict(cell_type=kind, id=hashlib.sha256((kind+text).encode('utf8')).hexdigest()[:12],
                   metadata={}, source=text.splitlines(keepends=True))
        if kind == 'code':
            row.update(execution_count=None, outputs=[])
        return row
    cells = [
        cell('markdown', '# FPGA-5：新卷积内核验证与同板整网测速\n手动逐格执行。先关闭其他使用 FPGA 的 Notebook；不要并行运行。原始 test_1/full_model_test 保留。\n\n本包是工程测试候选，保留 FIFO/BRAM 复位等工具警告，详情见 BUILD_STATUS.md；尚无板端性能或产品签核结论。'),
        cell('code', "import sys\nfrom pathlib import Path\nsys.dont_write_bytecode=True\nROOT=Path.cwd().resolve()\nassert (ROOT/'run_v5.py').is_file(), '请在 test_1/fpga_v5 中打开 Notebook'\nsys.path.insert(0,str(ROOT))\nfrom run_v5 import setup, correctness, profile, benchmark\nPREVIOUS_RUN='run_2d8b1cfeaf0c47bfac486cd2a09e49f0'\nRUN_NAME=''  # 恢复时填写本包已创建的 run_<编号>\nINCLUDE_FP32=True\nREPEATS=10\nWARMUP=2\nPROFILE_REPEATS=3\nRUN=setup(PREVIOUS_RUN,RUN_NAME,include_fp32=INCLUDE_FP32)\n"),
        cell('markdown', '## 1. 新硬件正确性\n先测试实际 FCM 2051 帧分块接缝和点卷积非整齐尺寸，再验证三条完整录音的每层 INT8/INT32，以及调试开关前后的完整向量。出现 V5_HARDWARE_READY 后才继续。可能需要数分钟。'),
        cell('code', 'correctness(RUN)\n'),
        cell('markdown', '## 2. CPU 子图、FPGA 层及 PL 周期剖析\n输出 CPU 张量尺寸、每层主机耗时，以及 V5 的 PL 周期/AXI 读写与等待。PL 窗口含硬件 DDR 访问；多个端口的等待计数可重叠。剖析时延包含计数器与记录开销。'),
        cell('code', 'profile(RUN,repeats=PROFILE_REPEATS,warmup=1)\n'),
        cell('markdown', '## 3. 关闭详细剖析，正式整网对照\n完整 INT8 CPU、原 FP32 CPU（可选）、V4 静态图、V5；1 线程，同一完整 Fbank，两轮反序，预热后计时。每次核对完整向量和 12+55 次实际硬件启动。测速不含采集、Fbank、初始化、参考审计与文件保存。倍率大于 1 才表示更快。保留原始 QDQ 漂移失败，不输出鉴权判定。'),
        cell('code', 'benchmark(RUN,repeats=REPEATS,warmup=WARMUP)\n'),
        cell('markdown', '返回 V5_SPEEDUP_COMPARE、performance.json、profile_layers.csv、profile_raw.json、hardware_correctness.json。超时或硬件执行中断后，先让开发板断电重启，再重启 Notebook 内核；不要删活跃标记绕过检查。结果仅写本目录。')]
    (BOARD / '01_v5_validation_and_benchmark.ipynb').write_text(json.dumps(dict(cells=cells,
        metadata=dict(kernelspec=dict(display_name='Python 3', language='python', name='python3'),
                      language_info=dict(name='python', version='3.10')),
        nbformat=4, nbformat_minor=5), ensure_ascii=False, indent=2)+'\n', encoding='utf8')


def main():
    notebook()
    routed = json.loads((ROOT / 'reports/routed_summary.json').read_text())
    if not routed.get('run_complete') or routed['wns_ns'] <= 0 or routed['whs_ns'] <= 0 or routed['drc_errors'] or routed.get('needs_refresh', True):
        raise RuntimeError('Routed implementation/timing required; no deployment package')
    acceptance = json.loads((ROOT / 'reports/implementation_acceptance.json').read_text())
    if not acceptance.get('pass_') or acceptance.get('actual_hardware') or acceptance.get('production_signoff'):
        raise RuntimeError('Current implementation report audit and honest candidate status required')
    for name, expected in acceptance['reports_sha256'].items():
        if sha(ROOT / 'reports' / name) != expected:
            raise RuntimeError('Implementation report changed after audit: ' + name)
    for name, expected in acceptance['artifacts_sha256'].items():
        if sha(ROOT / 'deploy' / name) != expected:
            raise RuntimeError('Implementation image changed after audit: ' + name)
    validation = json.loads((ROOT / 'reports/local_validation.json').read_text())
    if validation.get('matched_ip_hdl_files', 0) <= 0 or validation.get('packed_fragment_guard_cases') != 1152 or not validation.get('packed_mutation_rejected'):
        raise RuntimeError('Current Vivado HDL/packed-byte regression evidence required')
    current_sources = {p.relative_to(ROOT).as_posix():sha(p) for p in sorted((ROOT / 'src').glob('*')) if p.is_file()}
    if validation['source_sha256'] != current_sources:
        raise RuntimeError('Kernel sources changed after local validation')
    if validation['rtl_source_sha256'] != {p.relative_to(ROOT).as_posix():sha(p) for p in sorted((ROOT/'rtl').glob('*.v'))} or validation['connected_axi_signal_triples'] != 54:
        raise RuntimeError('Passive monitor/wiring checks incomplete or stale')
    inputs = [*ROOT.glob('src/*'), *ROOT.glob('rtl/*.v'),
              ROOT/'hls/pw/hls/impl/ip/component.xml', ROOT/'hls/fcm/hls/impl/ip/component.xml']
    if max(p.stat().st_mtime for p in inputs if p.is_file()) > (ROOT/'deploy/cam_v5.bit').stat().st_mtime:
        raise RuntimeError('Deployment image is older than the current kernel/IP/RTL')
    for name in ('pw', 'fcm'):
        if 'C/RTL co-simulation finished: PASS' not in (ROOT / ('logs/hls_'+name+'_cosim.log')).read_text(errors='replace'):
            raise RuntimeError('Matching HLS C/RTL pass required: '+name)
    hardware = BOARD / 'hardware'
    hardware.mkdir(exist_ok=True)
    for name in ('cam_v5.bit', 'cam_v5.hwh'):
        shutil.copy2(ROOT / 'deploy' / name, hardware / name)
    shutil.copy2(ROOT / 'reports/implementation_acceptance.json', BOARD / 'build_status.json')
    manifest = dict(version=5, actual_hardware_validated=False, clock_mhz=100,
        test1_manifest_sha256=sha(WORKSPACE / 'test_1/manifest.json'),
        source_sha256=current_sources,
        routed_summary=routed, implementation_audit=acceptance,
        files={p.relative_to(BOARD).as_posix():sha(p) for p in sorted(BOARD.rglob('*'))
               if p.is_file() and p.suffix != '.ipynb' and p.name != 'manifest.json'
               and 'results' not in p.parts and '__pycache__' not in p.parts})
    (BOARD / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf8')
    with zipfile.ZipFile(ROOT / 'deploy/fpga_v5_manual_tests.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for name in sorted([*manifest['files'], 'manifest.json', '01_v5_validation_and_benchmark.ipynb']):
            z.write(BOARD / name, 'fpga_v5/' + name)
    print('V5_MANUAL_PACKAGE_READY', ROOT / 'deploy/fpga_v5_manual_tests.zip')


if __name__ == '__main__':
    main()
