"""Read-only desktop audit of the exact deployment archive and HWH contract."""
import ast
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import zipfile


ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / 'board_package/fpga_v5'
sys.dont_write_bytecode = True
sys.path.insert(0, str(BOARD))
import v5_runtime as v5


def main():
    manifest = v5.verify()
    archive = ROOT / 'deploy/fpga_v5_manual_tests.zip'
    notebook_name = '01_v5_validation_and_benchmark.ipynb'
    expected = {'fpga_v5/' + name for name in
                [*manifest['files'], 'manifest.json', notebook_name]}
    with zipfile.ZipFile(archive) as z:
        if set(z.namelist()) != expected or len(z.namelist()) != len(expected):
            raise AssertionError('Unexpected or duplicate archive members')
        for name in z.namelist():
            if any(part in ('results', '__pycache__', '..') for part in Path(name).parts):
                raise AssertionError('Test output or unsafe path in archive: ' + name)
            relative = name.removeprefix('fpga_v5/')
            data = z.read(name)
            if data != (BOARD / relative).read_bytes():
                raise AssertionError('Archive differs from verified directory: ' + name)
            if relative in manifest['files']:
                if hashlib.sha256(data).hexdigest() != manifest['files'][relative]:
                    raise AssertionError('Archive hash mismatch: ' + name)
        notebook = json.loads(z.read('fpga_v5/' + notebook_name))
        for i, cell in enumerate(notebook['cells']):
            if cell['cell_type'] == 'code':
                if cell['outputs'] or cell['execution_count'] is not None:
                    raise AssertionError('Executed notebook shipped')
                ast.parse(''.join(cell['source']), filename=f'notebook_cell_{i}')
    tree = ET.parse(BOARD / 'hardware/cam_v5.hwh').getroot()
    maps = {}
    for instance, top, pointers, scalars in (
        ('pointwise_0', 'pointwise_v5', v5.pc.POINTERS, v5.pc.SCALARS),
        ('fcm_0', 'fcm_v5', v5.sr.old.fcm.POINTERS, v5.sr.old.fcm.SCALARS),
    ):
        maps[instance] = v5.register_map(tree, instance, 'xilinx.com:hls:' + top + ':1.0', pointers, scalars)
    monitor = next(m for m in tree.iter('MODULE') if m.get('INSTANCE') == 'perf_0')
    if monitor.get('VLNV') != 'sonicarm.org:user:axi_perf_monitor:1.1':
        raise AssertionError('Wrong monitor in deployed HWH')
    for name in ('cam_v5.bit', 'cam_v5.hwh'):
        if (ROOT / 'deploy' / name).read_bytes() != (BOARD / 'hardware' / name).read_bytes():
            raise AssertionError('Deployment pair changed while packaging')
    report = dict(pass_=True, actual_hardware=False, members=len(expected),
                  archive_sha256=v5.digest(archive), hwh_register_maps=maps,
                  note='Offline archive/hash/AST/HWH audit; no Overlay or board execution.')
    (ROOT / 'reports/manual_package_audit.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print('V5_MANUAL_PACKAGE_AUDIT_PASS', len(expected), 'members; no board execution')


if __name__ == '__main__':
    main()
