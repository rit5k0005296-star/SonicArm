"""Audit the exact local physical candidate; never claim board/production signoff."""
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / 'reports'
REPORT_NAMES = ('timing_routed.rpt', 'route_status_routed.rpt', 'check_timing_routed.rpt',
                'clock_interaction_routed.rpt', 'clocks_routed.rpt', 'cdc_routed.rpt',
                'exceptions_routed.rpt', 'bus_skew_routed.rpt', 'methodology_routed.rpt',
                'drc_routed.rpt', 'qor_assessment_routed.rpt', 'utilization_routed.rpt',
                'implemented_constraints.xdc', 'implementation_run_properties.rpt')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def timing_metrics(text):
    lines = text.splitlines()
    index = next(i for i, line in enumerate(lines) if line.strip().startswith('WNS(ns)'))
    values = lines[index + 2].split()
    if len(values) != 12:
        raise ValueError('Unrecognized design timing summary')
    names = ('wns_ns', 'tns_ns', 'setup_failing_endpoints', 'setup_endpoints',
             'whs_ns', 'ths_ns', 'hold_failing_endpoints', 'hold_endpoints',
             'wpws_ns', 'tpws_ns', 'pulse_failing_endpoints', 'pulse_endpoints')
    result = dict(zip(names, map(float, values)))
    for name in ('wns_ns', 'whs_ns', 'wpws_ns'):
        if result[name] <= 0:
            raise AssertionError('Strict positive timing margin required: ' + name)
    for name in ('tns_ns', 'ths_ns', 'tpws_ns', 'setup_failing_endpoints',
                 'hold_failing_endpoints', 'pulse_failing_endpoints'):
        if result[name] != 0:
            raise AssertionError('Timing violation: ' + name)
    return result


def findings(text):
    rows = re.findall(r'^\|\s*(\S+)\s*\|\s*(Warning|Critical Warning|Error|Advisory)\s*\|[^\n]*\|\s*(\d+)\s*\|$', text, re.M)
    if not rows:
        raise AssertionError('Cannot parse report finding summary')
    return {rule: dict(severity=severity, count=int(count)) for rule, severity, count in rows}


def utilization_metrics(text):
    result = {}
    labels = {
        'lut': 'Slice LUTs',
        'register': 'Slice Registers',
        'slice': 'Slice',
        'bram_tile': 'Block RAM Tile',
        'dsp': 'DSPs',
    }
    for key, label in labels.items():
        match = re.search(r'^\|\s*' + re.escape(label) +
                          r'\s*\|\s*(\d+)\s*\|\s*\d+\s*\|\s*\d+\s*\|\s*(\d+)\s*\|\s*([0-9.]+)\s*\|$',
                          text, re.M)
        if not match:
            raise AssertionError('Utilization row missing: ' + label)
        result[key] = dict(used=int(match[1]), available=int(match[2]), percent=float(match[3]))
    return result


def main():
    routed = json.loads((REPORTS / 'routed_summary.json').read_text())
    if not routed['run_complete'] or routed['needs_refresh'] or routed['part'] != 'xc7z020clg400-1':
        raise AssertionError('A fresh completed target implementation is required')
    texts = {name: (REPORTS / name).read_text(errors='replace') for name in REPORT_NAMES}
    metrics = timing_metrics(texts['timing_routed.rpt'])
    for name in ('wns_ns', 'whs_ns'):
        if abs(metrics[name] - routed[name]) > 0.0006:
            raise AssertionError('Timing report does not match exported candidate')
    checks = {name: int(count) for name, count in
              re.findall(r'checking (\w+) \((\d+)\)', texts['check_timing_routed.rpt'])}
    if len(checks) < 12 or any(checks.values()):
        raise AssertionError('Missing or failing timing coverage checks: ' + str(checks))
    route = texts['route_status_routed.rpt']
    counts = {}
    for label in ('routable nets', 'fully routed nets', 'nets with routing errors'):
        match = re.search(r'# of ' + label + r'\.+\s*:\s*(\d+)', route)
        if not match:
            raise AssertionError('Route status field missing: ' + label)
        counts[label] = int(match[1])
    if counts['routable nets'] != counts['fully routed nets'] or counts['nets with routing errors']:
        raise AssertionError('Routing is incomplete')
    if 'All paths are Safely Timed.' not in texts['cdc_routed.rpt']:
        raise AssertionError('CDC report needs review')
    if 'No bus skew constraints' not in texts['bus_skew_routed.rpt']:
        raise AssertionError('New bus-skew constraints require explicit coverage review')
    if not re.search(r'^clk_fpga_0\s+10\.000\s+\{0\.000 5\.000\}', texts['clocks_routed.rpt'], re.M):
        raise AssertionError('Wrong PL clock')
    if 'Clean' not in texts['clock_interaction_routed.rpt']:
        raise AssertionError('Clock relationship needs review')
    constraints = texts['implemented_constraints.xdc']
    if re.search(r'CLOCK_DEDICATED_ROUTE\s+(FALSE|false|0)', constraints):
        raise AssertionError('Clock routing must not be weakened')
    if 'create_clock -period 10.000 -name clk_fpga_0' not in constraints:
        raise AssertionError('Full implemented clock constraints missing')
    exceptions = texts['exceptions_routed.rpt']
    exception_rows = [line for line in exceptions.splitlines() if re.match(r'^\d+\s', line)]
    if not exception_rows or any('src_arst' not in line and 'syncstages_ff_reg[0]' not in line for line in exception_rows):
        raise AssertionError('Unexpected timing exceptions require review')
    if 'Ignored' in exceptions or 'Invalid' in exceptions:
        raise AssertionError('Ignored/invalid exceptions require review')
    drc = findings(texts['drc_routed.rpt'])
    methodology = findings(texts['methodology_routed.rpt'])
    utilization = utilization_metrics(texts['utilization_routed.rpt'])
    expected_drc = {'DPIP-1', 'DPOP-1', 'DPOP-2', 'PDCN-1569', 'REQP-1839', 'RTSTAT-10'}
    if not set(drc).issubset(expected_drc) or not set(methodology).issubset({'LUTAR-1'}):
        raise AssertionError('New finding types require review')
    if any(item['severity'] != 'Warning' for item in [*drc.values(), *methodology.values()]):
        raise AssertionError('DRC/methodology errors or critical warnings')
    props = texts['implementation_run_properties.rpt']
    if not re.search(r'^STATUS\s+string\s+true\s+write_bitstream Complete', props, re.M):
        raise AssertionError('Run status is not freshly complete')
    if not re.search(r'^NEEDS_REFRESH\s+bool\s+false\s+0\s*$', props, re.M):
        raise AssertionError('Run inputs marked stale')
    run = ROOT / 'vivado/v7_final/v7.runs/impl_1'
    launch = ET.parse(run / 'gen_run.xml').getroot()
    if launch.get('LaunchIncrCheckpoint'):
        raise AssertionError('Old incremental launch metadata remains')
    if not (run / '.write_bitstream.end.rst').is_file():
        raise AssertionError('Bitstream stage is not complete')
    if 'Bitgen Completed Successfully.' not in (run / 'runme.log').read_text(errors='replace'):
        raise AssertionError('Successful bit generation not recorded')
    artifacts = {name: sha(ROOT / 'deploy' / name) for name in ('cam_v7.bit', 'cam_v7.hwh')}
    if artifacts['cam_v7.bit'] != sha(run / 'system_wrapper.bit'):
        raise AssertionError('Exported image differs from final run')
    bit_time = (run / 'system_wrapper.bit').stat().st_mtime
    if any((REPORTS / name).stat().st_mtime < bit_time for name in REPORT_NAMES):
        raise AssertionError('A final report predates the final bitstream')
    result = dict(pass_=True, actual_hardware=False, production_signoff=False,
        acceptance_scope='fresh local implementation with positive STA margins; manual test candidate only',
        metrics=metrics, utilization=utilization, timing_coverage=checks, route=counts, cdc_safely_timed=True,
        bus_skew_constraints=False, vendor_reset_exception_rows=len(exception_rows),
        drc_warnings=drc, methodology_warnings=methodology,
        unresolved_release_findings=['vendor FIFO LUTAR-1/PDCN-1569 and RAMB36 reset-control warnings',
            'inherited PS7 DDR DQS parameter warnings; actual reset/DDR behavior untested',
            'original QDQ model drift remains failed; no calibrated authentication threshold'],
        artifacts_sha256=artifacts,
        reports_sha256={name: sha(REPORTS / name) for name in REPORT_NAMES},
        checkpoint_sha256=sha(run / 'system_wrapper_routed.dcp'))
    (REPORTS / 'implementation_acceptance.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
    print('V7_IMPLEMENTATION_AUDIT_PASS manual candidate; production signoff false; board untested')


if __name__ == '__main__':
    main()
