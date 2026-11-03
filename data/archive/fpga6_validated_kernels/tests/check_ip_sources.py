"""Prove the new Vivado project copied the currently packaged HLS RTL."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    generated = ROOT / 'vivado/v6/v6.gen/sources_1/bd/system/ipshared'
    matches = {}
    for kernel, top in (('pw', 'pointwise_v6'), ('fcm', 'fcm_v6')):
        export = ROOT / ('hls/' + kernel + '/hls/impl/ip/hdl/verilog')
        anchors = list(generated.rglob(top + '_store.v'))
        if len(anchors) != 1:
            raise ValueError('Expected one generated RTL source directory: ' + top)
        actual = anchors[0].parent
        files = [p for p in export.rglob('*') if p.is_file()]
        if not files:
            raise ValueError('Packaged RTL missing: ' + top)
        for source in files:
            relative = source.relative_to(export)
            target = actual / relative
            if not target.is_file() or digest(source) != digest(target):
                raise ValueError('Vivado uses stale/different HLS RTL: ' + str(relative))
            matches[target.relative_to(ROOT).as_posix()] = digest(target)
    result = dict(pass_=True, actual_hardware=False, matched_ip_hdl_files=len(matches), sha256=matches)
    (ROOT / 'reports/ip_source_audit.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
    print('V6_IP_SOURCE_AUDIT_PASS', len(matches), 'currently packaged HDL files')


if __name__ == '__main__':
    main()
