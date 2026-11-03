"""Desktop-only checks for the V7 HWH, mode adapter and board package."""
from pathlib import Path
import importlib
import json
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'board_package/fpga_v7'
sys.path.insert(0, str(PACKAGE))
v7 = importlib.import_module('v7_runtime')


class FakeIP:
    def __init__(self):
        self.registers = {}
        self.writes = []

    def write(self, address, value):
        self.registers[address] = value
        self.writes.append((address, value))

    def read(self, address):
        return self.registers.get(address, 0)


def main():
    manifest = v7.verify()
    tree = ET.parse(PACKAGE / 'hardware/cam_v7.hwh').getroot()
    offsets = v7.register_map(tree)
    modules = [m for m in tree.iter('MODULE') if m.get('VLNV', '').startswith('xilinx.com:hls:')]
    if [(m.get('INSTANCE'), m.get('VLNV')) for m in modules] != [
            ('unified_0', 'xilinx.com:hls:unified_v7:1.0')]:
        raise AssertionError('Expected exactly one V7 HLS IP')

    owner = object.__new__(v7.Engine)
    owner.offsets = offsets
    owner.ip = FakeIP()
    owner.poisoned = False
    owner.current_mode = None
    owner.calls = {'pointwise': 0, 'FCM': 0}
    owner.ip.registers[offsets['output_r_1']] = 0x12345678
    owner.ip.registers[offsets['output_r_2']] = 0
    pw = v7.ModeIP(owner, v7.MODE_POINTWISE)
    pw.write(offsets['CTRL'], 1)
    if owner.ip.registers[offsets['mode']] != 0:
        raise AssertionError('Pointwise mode was not selected')
    if any(owner.ip.registers[offsets[name]] != 1 for name in ('freq', 'kernel', 'stride_f')):
        raise AssertionError('Pointwise compatibility scalars were not completed')
    if owner.ip.registers[offsets['residual_1']] != 0x12345678:
        raise AssertionError('Pointwise residual dummy was not mapped')
    if owner.calls != {'pointwise': 1, 'FCM': 0} or owner.ip.writes[-1] != (offsets['CTRL'], 1):
        raise AssertionError('Pointwise start ordering/count mismatch')
    before = len(owner.ip.writes)
    pw.write(offsets['CTRL'], 1)
    if owner.ip.writes[before:] != [(offsets['CTRL'], 1)]:
        raise AssertionError('Repeated pointwise launch rewrote static mode registers')

    fcm = v7.ModeIP(owner, v7.MODE_FCM)
    fcm.write(offsets['CTRL'], 1)
    if owner.ip.registers[offsets['mode']] != 1 or owner.calls != {'pointwise': 2, 'FCM': 1}:
        raise AssertionError('FCM mode/count mismatch')

    notebook = json.loads((PACKAGE / '01_v7_validation_and_benchmark.ipynb').read_text(encoding='utf8'))
    code = '\n'.join(''.join(cell.get('source', [])) for cell in notebook['cells'] if cell['cell_type'] == 'code')
    compile(code, str(PACKAGE / '01_v7_validation_and_benchmark.ipynb'), 'exec')

    # A normal Jupyter save must not invalidate the runtime package, while a
    # modified execution dependency must still be rejected.
    original_here = v7.HERE
    (ROOT / 'tool_temp').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / 'tool_temp') as temporary:
        installed = Path(temporary) / 'fpga_v7'
        shutil.copytree(PACKAGE, installed)
        changed = json.loads((installed / '01_v7_validation_and_benchmark.ipynb').read_text(encoding='utf8'))
        changed.setdefault('metadata', {})['v7_mutability_regression'] = True
        (installed / '01_v7_validation_and_benchmark.ipynb').write_text(
            json.dumps(changed, ensure_ascii=False, indent=1) + '\n', encoding='utf8')
        try:
            v7.HERE = installed
            v7.verify()
            with (installed / 'v7_runtime.py').open('a', encoding='utf8') as stream:
                stream.write('\n# deliberate integrity mutation\n')
            try:
                v7.verify()
            except ValueError as error:
                if 'v7_runtime.py' not in str(error):
                    raise
            else:
                raise AssertionError('Runtime source mutation was not rejected')
        finally:
            v7.HERE = original_here
    status = json.loads((PACKAGE / 'build_status.json').read_text(encoding='utf8'))
    if status['actual_hardware_validated'] or status['implementation']['routing_errors']:
        raise AssertionError('Invalid desktop release boundary')
    if manifest['part'] != 'xc7z020clg400-1' or manifest['clock_mhz'] != 100:
        raise AssertionError('Wrong package target')
    print('V7_DESKTOP_PACKAGE_CHECK_PASS mutable notebook accepted; runtime mutation rejected; board untested')


if __name__ == '__main__':
    main()

