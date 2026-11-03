"""Freeze current design inputs before physical synthesis. No generated cache pins."""
from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parents[1]
files=sorted({*R.glob('src/*'),*R.glob('rtl/*.v'),*R.glob('*.cfg'),*R.glob('*.tcl'),
              *R.glob('tests/tb_*.cpp'),R/'hls/pw/hls/impl/ip/component.xml',R/'hls/fcm/hls/impl/ip/component.xml'})
pins={p.relative_to(R).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()}
target=R/'reports/design_inputs.json'
if target.exists():
    old=json.loads(target.read_text())
    assert old==pins,'Design inputs changed; preserve previous build evidence and rebuild explicitly'
else:target.write_text(json.dumps(pins,indent=2))
print('V6_DESIGN_INPUTS_PINNED',len(pins))
