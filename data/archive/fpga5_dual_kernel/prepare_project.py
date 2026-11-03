"""Create isolated test inputs and pin the unmodified V3/V4 source baseline."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT=Path(__file__).resolve().parent
MODELS=ROOT.parent
V3=MODELS/'FPGA-3/pointwise_engine'
V4=MODELS/'FPGA-4/fcm_engine'
for d in ('tests','reports','logs','deploy','rtl'):
    (ROOT/d).mkdir(exist_ok=True)
pins={}
for label,source,names in [('v3',V3,['pointwise.cpp','pointwise.h','tb_pointwise.cpp']),
                           ('v4',V4,['fcm.cpp','fcm.h','tb_fcm.cpp','ps7_config.tcl'])]:
    for name in names:
        path=source/name
        pins[f'{label}/{name}']=hashlib.sha256(path.read_bytes()).hexdigest()
    text=(source/('tb_pointwise.cpp' if label=='v3' else 'tb_fcm.cpp')).read_text(encoding='utf8')
    # Pad native buffers to 64-bit AXI co-simulation depths; numerical oracle unchanged.
    text=text.replace('32768','131072').replace('16384','131072')
    header='pointwise.h' if label=='v3' else 'fcm.h'
    text=text.replace('#include "'+header+'"','#include "'+header+'"\n#include "abi_adapters.h"',1)
    (ROOT/'tests'/('tb_pointwise.cpp' if label=='v3' else 'tb_fcm.cpp')).write_text(text,encoding='utf8')
    target=ROOT/'tests'/('pw_cases' if label=='v3' else 'fcm_cases')
    if not target.exists():
        shutil.copytree(source/'deploy/cases',target)
    for path in target.rglob('*'):
        if path.is_file():pins[str(path.relative_to(ROOT)).replace('\\','/')]=hashlib.sha256(path.read_bytes()).hexdigest()
shutil.copyfile(V4/'ps7_config.tcl',ROOT/'ps7_config.tcl')
(ROOT/'reports/baseline_pins.json').write_text(json.dumps(pins,indent=2),encoding='utf8')
for name,top in [('pw','pointwise_v5'),('fcm','fcm_v5')]:
    source='pointwise' if name=='pw' else 'fcm'
    argv=f'W:/tests/{name}_cases'+(' --all' if name=='pw' else '')
    cfg=f'''part=xc7z020clg400-1
[hls]
flow_target=vivado
syn.top={top}
syn.file=W:/src/{source}.cpp
syn.cflags=-IW:/src
tb.file=W:/tests/tb_{source}.cpp
tb.cflags=-IW:/src
clock=10ns
csim.argv={argv}
cosim.argv=W:/tests/{name}_cases --rtl
cosim.rtl=verilog
cosim.tool=xsim
cosim.trace_level=none
package.output.format=ip_catalog
package.output.syn=false
'''
    (ROOT/f'{name}.cfg').write_text(cfg,encoding='utf8')
print('V5 sources/test adapters isolated; baseline hashes pinned; case files copied only locally.')
