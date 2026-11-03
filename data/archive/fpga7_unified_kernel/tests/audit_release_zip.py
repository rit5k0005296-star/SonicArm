"""Verify every manifest-listed file inside the V7 manual-test ZIP."""
from pathlib import Path
import hashlib
import io
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'deploy/fpga_v7_manual_tests.zip'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    with zipfile.ZipFile(ARCHIVE) as bundle:
        names = set(bundle.namelist())
        manifest_name = 'fpga_v7/manifest.json'
        if manifest_name not in names:
            raise AssertionError('ZIP has no fpga_v7/manifest.json')
        manifest = json.load(io.TextIOWrapper(bundle.open(manifest_name), encoding='utf8'))
        release_files = {**manifest['files'], **manifest.get('mutable_files', {})}
        for name, expected in release_files.items():
            member = 'fpga_v7/' + name
            if member not in names or digest(bundle.read(member)) != expected:
                raise AssertionError('ZIP member mismatch: ' + member)
        forbidden = [name for name in names if '/results/' in name and not name.endswith('/')]
        if forbidden:
            raise AssertionError('Desktop or historical results leaked into ZIP')
    report = {
        'pass': True,
        'actual_hardware': False,
        'zip_sha256': digest(ARCHIVE.read_bytes()),
        'manifest_sha256': digest((ROOT / 'board_package/fpga_v7/manifest.json').read_bytes()),
        'runtime_verified_file_count': len(manifest['files']),
        'release_verified_mutable_file_count': len(manifest.get('mutable_files', {})),
        'verified_file_count': len(release_files),
    }
    (ROOT / 'reports/package_zip_check.json').write_text(
        json.dumps(report, indent=2) + '\n', encoding='utf8')
    print('V7_RELEASE_ZIP_CHECK_PASS', report['zip_sha256'])


if __name__ == '__main__':
    main()
