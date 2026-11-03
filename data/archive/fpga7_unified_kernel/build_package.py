"""Create the V7 manual-board package manifest on the desktop.

Runtime dependencies are immutable.  The Jupyter notebook is shipped with a
release hash for ZIP auditing, but it is intentionally mutable after install
because Jupyter saves outputs, execution counts and metadata into the file.
"""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parent
PACKAGE = ROOT / 'board_package/fpga_v7'
V6_PACKAGE = ROOT.parent / 'FPGA-6/board_package/fpga_v6'
V6_RUN_NAME = 'run_ecddaa97a20f4d0caf60427bf327e120'
V6_RESULT = ROOT.parent / 'FPGA-6/analysis' / V6_RUN_NAME

IMMUTABLE_FILES = (
    'BUILD_STATUS.md',
    'README.md',
    'build_status.json',
    'hardware/cam_v7.bit',
    'hardware/cam_v7.hwh',
    'implementation_acceptance.json',
    'run_v7.py',
    'v7_runtime.py',
)

MUTABLE_FILES = (
    '01_v7_validation_and_benchmark.ipynb',
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    v6_manifest = json.loads((V6_PACKAGE / 'manifest.json').read_text(encoding='utf8'))
    acceptance = json.loads((PACKAGE / 'implementation_acceptance.json').read_text(encoding='utf8'))
    if not acceptance['pass_'] or acceptance['actual_hardware'] or acceptance['production_signoff']:
        raise AssertionError('Expected a desktop-only accepted implementation candidate')
    if acceptance['artifacts_sha256'] != {
        'cam_v7.bit': sha(PACKAGE / 'hardware/cam_v7.bit'),
        'cam_v7.hwh': sha(PACKAGE / 'hardware/cam_v7.hwh'),
    }:
        raise AssertionError('Packaged hardware differs from implementation acceptance')
    manifest = {
        'version': 7,
        'actual_hardware_validated': False,
        'production_signoff': False,
        'clock_mhz': 100,
        'part': 'xc7z020clg400-1',
        'v6_manifest_sha256': sha(V6_PACKAGE / 'manifest.json'),
        'test1_manifest_sha256': v6_manifest['test1_manifest_sha256'],
        'v6_result_receipt': {
            'run': V6_RUN_NAME,
            'files': {name: sha(V6_RESULT / name) for name in
                      ('setup.json', 'hardware_correctness.json', 'performance.json')},
        },
        'source_sha256': {name: sha(ROOT / name) for name in
                          ('src/unified.cpp', 'src/unified.h', 'src/pointwise.cpp',
                           'src/pointwise.h', 'src/fcm.cpp', 'src/fcm.h', 'src/packed.h')},
        'implementation_acceptance_sha256': sha(PACKAGE / 'implementation_acceptance.json'),
        # Runtime verifies these files before programming the Overlay.
        'files': {name: sha(PACKAGE / name) for name in IMMUTABLE_FILES},
        # Release tools verify the pristine copy. Runtime only requires these
        # files to exist, since interactive tools legitimately rewrite them.
        'mutable_files': {name: sha(PACKAGE / name) for name in MUTABLE_FILES},
    }
    (PACKAGE / 'manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print('V7_PACKAGE_MANIFEST_READY', sha(PACKAGE / 'manifest.json'))


if __name__ == '__main__':
    main()

