"""One-time isolated source import. Never import generated V5 IP or build caches."""
from pathlib import Path
import csv
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parent
V5 = ROOT.parent / 'FPGA-5'
RUN = V5 / 'analysis/run_4c5e10fec13d43d9a055a4042888adb5'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def rewrite(s):
    return (s.replace('FPGA-5','FPGA-6').replace('fpga_v5','fpga_v6')
            .replace('V5','V6').replace('v5','v6').replace('pw5','pw6').replace('fcm5','fcm6')
            .replace('W:/','V:/').replace('W:\\','V:\\').replace('W:', 'V:')
            .replace('56355046','56365046'))
files = [
 'src/pointwise.cpp','src/pointwise.h','src/fcm.cpp','src/fcm.h','src/packed.h',
 'rtl/axi_perf_monitor.v','rtl/axi_perf_wrapper.v','rtl/axi_ram_model.sv',
 'rtl/tb_axi_perf_monitor.sv','rtl/tb_axi_perf_wrapper.sv',
 'tests/tb_pointwise.cpp','tests/tb_fcm.cpp','tests/abi_adapters.h','tests/test_packed.cpp',
 'tests/native_exports.cpp','tests/make_rtl_harness.py','tests/make_monitor_wrapper.py',
 'tests/check_bus_connectivity.py','tests/check_ip_sources.py','tests/check_packed_mutation.py',
 'tests/desktop_workflow_check.py','tests/audit_implementation.py','tests/audit_manual_package.py',
 'run_hls.ps1','run_vivado.ps1','run_local_checks.ps1','pw.cfg','fcm.cfg',
 'create_vivado.tcl','build_vivado.tcl','collect_vivado.tcl','implementation_reports.tcl',
 'connect_monitor.tcl','package_monitor.tcl','ps7_config.tcl','open_project.tcl',
 'make_board_package.py','verify_local_evidence.py',
 'board_package/fpga_v5/v5_runtime.py','board_package/fpga_v5/run_v5.py',
 'board_package/fpga_v5/README.md','board_package/fpga_v5/BUILD_STATUS.md',
]
pins = {}
for name in files:
    source = V5 / name
    target = ROOT / rewrite(name)
    if target.exists(): raise RuntimeError('Refusing to overwrite ' + str(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rewrite(source.read_text(encoding='utf8')), encoding='utf8')
    pins['FPGA-5/' + name] = sha(source)
for kind in ('pw','fcm'):
    target = ROOT / f'tests/{kind}_cases'
    if target.exists(): raise RuntimeError('Cases already exist')
    shutil.copytree(V5 / f'tests/{kind}_cases',target)
    for p in target.rglob('*'):
        if p.is_file(): pins[p.relative_to(ROOT).as_posix()] = sha(p)
for d in ('reports','logs','deploy','rtl_sim','rtl_kernel_sim','tool_temp'):
    (ROOT/d).mkdir(exist_ok=True)
evidence = {}
for p in sorted(RUN.iterdir()):
    if p.suffix == '.json':
        value = json.loads(p.read_text(encoding='utf-8-sig'))
        evidence[p.name] = {'sha256':sha(p),'bytes':p.stat().st_size,
                            'top_level_keys':list(value) if isinstance(value,dict) else None,
                            'records':len(value) if isinstance(value,list) else None}
    elif p.suffix == '.csv':
        rows = list(csv.DictReader(p.open(encoding='utf-8-sig',newline='')))
        evidence[p.name] = {'sha256':sha(p),'rows':len(rows),'fields':list(rows[0])}
    else: evidence[p.name] = {'sha256':sha(p),'bytes':p.stat().st_size}
    pins['FPGA-5/analysis/' + RUN.name + '/' + p.name] = sha(p)
(ROOT/'reports/v5_evidence_inventory.json').write_text(json.dumps(evidence,indent=2),encoding='utf8')
(ROOT/'reports/baseline_pins.json').write_text(json.dumps(pins,indent=2),encoding='utf8')
print('V6_ISOLATED_IMPORT', len(files), 'source files;',len(pins),'baseline/reference pins')
print(json.dumps(evidence,indent=2))
