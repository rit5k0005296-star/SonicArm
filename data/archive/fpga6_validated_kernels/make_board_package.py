"""Freeze a manual-board package only after local implementation evidence passes."""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile
from verify_local_evidence import read_log

ROOT = Path(__file__).resolve().parent
BOARD = ROOT / 'board_package/fpga_v6'
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
        cell('markdown', '# FPGA-6：新卷积内核验证与同板整网测速\n手动逐格执行。先关闭其他使用 FPGA 的 Notebook；不要并行运行。原始 test_1/full_model_test 保留。\n\n本包是工程测试候选，保留 FIFO/BRAM 复位等工具警告，详情见 BUILD_STATUS.md；尚无板端性能或产品签核结论。'),
        cell('code', "import sys\nfrom pathlib import Path\nsys.dont_write_bytecode=True\nROOT=Path.cwd().resolve()\nassert (ROOT/'run_v6.py').is_file(), '请在 test_1/fpga_v6 中打开 Notebook'\nsys.path.insert(0,str(ROOT))\nfrom run_v6 import setup, correctness, profile, benchmark\nPREVIOUS_RUN='run_2d8b1cfeaf0c47bfac486cd2a09e49f0'\nRUN_NAME=''  # 恢复时填写本包已创建的 run_<编号>\nINCLUDE_FP32=True\nREPEATS=10\nWARMUP=2\nPROFILE_REPEATS=3\nRUN=setup(PREVIOUS_RUN,RUN_NAME,include_fp32=INCLUDE_FP32)\n"),
        cell('markdown', '## 1. 新硬件正确性\n先测试实际 FCM 2051 帧分块接缝和点卷积非整齐尺寸，再验证三条完整录音的每层 INT8/INT32，以及调试开关前后的完整向量。出现 V6_HARDWARE_READY 后才继续。可能需要数分钟。'),
        cell('code', 'correctness(RUN)\n'),
        cell('markdown', '## 2. CPU 子图、FPGA 层及 PL 周期剖析\n输出 CPU 张量尺寸、每层主机耗时，以及 V6 的 PL 周期/AXI 读写与等待。PL 窗口含硬件 DDR 访问；多个端口的等待计数可重叠。剖析时延包含计数器与记录开销。'),
        cell('code', 'profile(RUN,repeats=PROFILE_REPEATS,warmup=1)\n'),
        cell('markdown', '## 3. 关闭详细剖析，正式整网对照\n完整 INT8 CPU、原 FP32 CPU（可选）、当前 V5、V6；1 线程，同一完整 Fbank，两轮反序，预热后计时。保留旁边已验证的 test_1/fpga_v5 包；首格核对其原始指纹。每次核对完整向量和 12+55 次实际硬件启动。测速不含采集、Fbank、初始化、参考审计与文件保存。倍率大于 1 才表示更快。保留原始 QDQ 漂移失败，不输出鉴权判定。'),
        cell('code', 'benchmark(RUN,repeats=REPEATS,warmup=WARMUP)\n'),
        cell('markdown', '返回 V6_SPEEDUP_COMPARE、performance.json、profile_layers.csv、profile_raw.json、hardware_correctness.json。超时或硬件执行中断后，先让开发板断电重启，再重启 Notebook 内核；不要删活跃标记绕过检查。结果仅写本目录。')]
    (BOARD / '01_v6_validation_and_benchmark.ipynb').write_text(json.dumps(dict(cells=cells,
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
    if validation.get('independent_fcm_rtl_cases') != 12 or not validation.get('fcm_carry_mutation_rejected'):
        raise RuntimeError('V6-specific AXI/carry checks required')
    current_sources = {p.relative_to(ROOT).as_posix():sha(p) for p in sorted((ROOT / 'src').glob('*')) if p.is_file()}
    if validation['source_sha256'] != current_sources:
        raise RuntimeError('Kernel sources changed after local validation')
    if validation['rtl_source_sha256'] != {p.relative_to(ROOT).as_posix():sha(p) for p in sorted((ROOT/'rtl').glob('*.v'))} or validation['connected_axi_signal_triples'] != 54:
        raise RuntimeError('Passive monitor/wiring checks incomplete or stale')
    inputs = [*ROOT.glob('src/*'), *ROOT.glob('rtl/*.v'),
              ROOT/'hls/pw/hls/impl/ip/component.xml', ROOT/'hls/fcm/hls/impl/ip/component.xml']
    if max(p.stat().st_mtime for p in inputs if p.is_file()) > (ROOT/'deploy/cam_v6.bit').stat().st_mtime:
        raise RuntimeError('Deployment image is older than the current kernel/IP/RTL')
    for name in ('pw', 'fcm'):
        if 'C/RTL co-simulation finished: PASS' not in read_log(ROOT / ('logs/hls_'+name+'_cosim.log')):
            raise RuntimeError('Matching HLS C/RTL pass required: '+name)
    hardware = BOARD / 'hardware'
    hardware.mkdir(exist_ok=True)
    for name in ('cam_v6.bit', 'cam_v6.hwh'):
        shutil.copy2(ROOT / 'deploy' / name, hardware / name)
    metrics=acceptance['metrics']
    (BOARD/'BUILD_STATUS.md').write_text(
        '# FPGA-6 本地构建状态\n\n'
        '本包已完成当前源码的C参考、边界检查、HLS综合、C/RTL协同仿真、12个独立AXI背压用例、'
        '计数器RTL、桌面完整录音回归、新IP接入及普通Vivado综合/布局布线。bit/HWH与当前源码对应。\n\n'
        f"100 MHz；WNS {metrics['wns_ns']:+.3f} ns，WHS {metrics['whs_ns']:+.3f} ns，WPWS {metrics['wpws_ns']:+.3f} ns；"
        'TNS/THS/TPWS为0，完整路由，零路由错误和DRC错误。详情及工具警告见build_status.json。\n\n'
        'actual_hardware=false，production_signoff=false。V6尚未进行板端正确性、PL剖析或整网测速。'
        '原始QDQ漂移失败、accuracy_matched_claim=false、未校准鉴权阈值继续保留；不输出鉴权判定。\n\n'
        '57个CPU会话、55个点卷积和12个FCM逻辑调用保持不变；不做跨层融合。'
        '主改动是FCM持续标量重定量化、残差预取、行缓存和跨时间块打包。'
        'HLS估计和独立RTL周期比较均不能替代同板、同输入、同计时口径的V5/INT8 CPU对照。\n\n'
        'FIFO/BRAM复位及DSP流水等工具警告以build_status.json中实际列表为准；'
        '尚无板端复位/重载/长期DDR稳定性及产品签核结论。\n',encoding='utf8')
    shutil.copy2(ROOT / 'reports/implementation_acceptance.json', BOARD / 'build_status.json')
    manifest = dict(version=6, actual_hardware_validated=False, clock_mhz=100,
        v5_manifest_sha256=sha(ROOT.parent / 'FPGA-5/board_package/fpga_v5/manifest.json'),
        test1_manifest_sha256=sha(WORKSPACE / 'test_1/manifest.json'),
        source_sha256=current_sources,
        routed_summary=routed, implementation_audit=acceptance,
        files={p.relative_to(BOARD).as_posix():sha(p) for p in sorted(BOARD.rglob('*'))
               if p.is_file() and p.suffix != '.ipynb' and p.name != 'manifest.json'
               and 'results' not in p.parts and '__pycache__' not in p.parts})
    (BOARD / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf8')
    with zipfile.ZipFile(ROOT / 'deploy/fpga_v6_manual_tests.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for name in sorted([*manifest['files'], 'manifest.json', '01_v6_validation_and_benchmark.ipynb']):
            z.write(BOARD / name, 'fpga_v6/' + name)
    print('V6_MANUAL_PACKAGE_READY', ROOT / 'deploy/fpga_v6_manual_tests.zip')


if __name__ == '__main__':
    main()
