"""Cross-check the final desktop-only V7 release evidence and package."""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'board_package/fpga_v7'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def transactions(path):
    text = Path(path).read_text(errors='replace')
    return [int(value) for value in re.findall(r'^transaction\s+\d+:\s+(\d+)', text, re.M)]


def main():
    acceptance = json.loads((ROOT / 'reports/implementation_acceptance.json').read_text())
    desktop = json.loads((ROOT / 'reports/desktop_workflow_validation.json').read_text())
    manifest = json.loads((PACKAGE / 'manifest.json').read_text())
    status = json.loads((PACKAGE / 'build_status.json').read_text())
    assert acceptance['pass_'] and not acceptance['actual_hardware']
    assert desktop['pass_'] and not desktop['actual_hardware'] and desktop['all_67_layers']
    for name, expected in manifest['files'].items():
        assert sha(PACKAGE / name) == expected, name
    for name, expected in manifest.get('mutable_files', {}).items():
        assert sha(PACKAGE / name) == expected, name
    for name, expected in manifest['source_sha256'].items():
        assert sha(ROOT / name) == expected, name
    for name in ('cam_v7.bit', 'cam_v7.hwh'):
        assert sha(ROOT / 'deploy' / name) == acceptance['artifacts_sha256'][name]
        assert sha(PACKAGE / 'hardware' / name) == acceptance['artifacts_sha256'][name]
    assert not any((PACKAGE / 'results').rglob('*.*'))
    pw_cycles = transactions(ROOT / 'hls/shared_pw/hls/sim/report/verilog/result.transaction.rpt')
    fcm_cycles = transactions(ROOT / 'hls/shared_fcm/hls/sim/report/verilog/result.transaction.rpt')
    assert pw_cycles == [21641, 23393, 33561]
    assert fcm_cycles == [198899, 118485, 100431, 232769, 33565, 99456, 7280, 192499]
    assert status['hls']['cosim_cycle_regression']['pointwise_after_total'] == sum(pw_cycles)
    assert status['hls']['cosim_cycle_regression']['fcm_after_total'] == sum(fcm_cycles)
    assert status['implementation']['utilization'] == acceptance['utilization']
    result = {
        'pass': True,
        'actual_hardware': False,
        'production_signoff': False,
        'manifest_sha256': sha(PACKAGE / 'manifest.json'),
        'bit_sha256': acceptance['artifacts_sha256']['cam_v7.bit'],
        'hwh_sha256': acceptance['artifacts_sha256']['cam_v7.hwh'],
        'pointwise_cosim_cycles': pw_cycles,
        'fcm_cosim_cycles': fcm_cycles,
        'desktop_full_recording_frames': [v[1] for v in desktop['full_recordings'].values()],
        'boundary': 'desktop implementation candidate; manual PYNQ-Z2 validation required',
    }
    (ROOT / 'reports/final_release_check.json').write_text(
        json.dumps(result, indent=2) + '\n', encoding='utf8')
    print('V7_FINAL_RELEASE_CHECK_PASS board untested', result['manifest_sha256'])


if __name__ == '__main__':
    main()
