#!/usr/bin/env python3
"""Validate an IP contract and generate a mock-testable PYNQ MMIO driver."""
import argparse, json, keyword, re, sys
from pathlib import Path

def validate(c):
    errors=[]
    for k in ("name","base_address","address_range","registers"):
        if k not in c: errors.append(f"missing:{k}")
    regs=c.get("registers",[]); seen=set()
    for r in regs:
        for k in ("name","offset","width","access"):
            if k not in r: errors.append(f"register_missing:{k}")
        n=r.get("name","")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*",n) or keyword.iskeyword(n): errors.append(f"invalid_register_name:{n}")
        try: off=int(r.get("offset",-1),0) if isinstance(r.get("offset"),str) else int(r.get("offset",-1))
        except Exception: off=-1
        if off<0 or off%4: errors.append(f"invalid_offset:{n}")
        if off in seen: errors.append(f"duplicate_offset:{off}")
        seen.add(off)
        if r.get("width") not in (8,16,32,64): errors.append(f"invalid_width:{n}")
        if r.get("access") not in ("ro","rw","wo"): errors.append(f"invalid_access:{n}")
    return errors

TEMPLATE='''"""Generated from {contract}; do not infer undocumented algorithm semantics."""\ntry:\n    from pynq import MMIO as _PynqMMIO\nexcept ImportError:\n    _PynqMMIO = None\n\nclass {class_name}:\n    REGISTERS = {registers!r}\n    def __init__(self, base_address={base}, address_range={span}, mmio=None):\n        if mmio is None:\n            if _PynqMMIO is None: raise RuntimeError("PYNQ unavailable; inject a mock MMIO")\n            mmio=_PynqMMIO(base_address,address_range)\n        self.mmio=mmio\n    def read(self,name):\n        r=self.REGISTERS[name]\n        if r[1] == "wo": raise PermissionError(name)\n        return self.mmio.read(r[0])\n    def write(self,name,value):\n        r=self.REGISTERS[name]\n        if r[1] == "ro": raise PermissionError(name)\n        if value < 0 or value >= (1 << r[2]): raise ValueError("value out of range")\n        self.mmio.write(r[0],value)\n'''
MOCK='''class MockMMIO:\n    def __init__(self): self.mem={{}}\n    def read(self,offset): return self.mem.get(offset,0)\n    def write(self,offset,value): self.mem[offset]=value\n'''
def generate(c,source):
    errors=validate(c)
    if errors: return None,errors
    regs={r["name"]:(int(r["offset"],0) if isinstance(r["offset"],str) else r["offset"],r["access"],r["width"]) for r in c["registers"]}
    cls="".join(x.title() for x in re.split(r"[^A-Za-z0-9]+",c["name"]))+"Driver"
    safe_source=source.replace("\\","/")
    return TEMPLATE.format(contract=safe_source,class_name=cls,registers=regs,base=int(c["base_address"],0) if isinstance(c["base_address"],str) else c["base_address"],span=int(c["address_range"],0) if isinstance(c["address_range"],str) else c["address_range"])+"\n"+MOCK,[]
def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--contract",required=True); p.add_argument("--output-dir",required=True); p.add_argument("--json",action="store_true"); a=p.parse_args()
    try: c=json.loads(Path(a.contract).read_text(encoding="utf-8"))
    except Exception as e: print(json.dumps({"status":"FAIL","errors":[str(e)]})); return 2
    code,errors=generate(c,a.contract)
    if errors: print(json.dumps({"status":"FAIL","errors":errors},indent=2)); return 2
    out=Path(a.output_dir); out.mkdir(parents=True,exist_ok=False); target=out/(c["name"]+"_driver.py"); target.write_text(code,encoding="utf-8")
    result={"status":"PASS","generated":[str(target)],"unverified_semantics":c.get("unverified_semantics",[])}; print(json.dumps(result,indent=2)); return 0
if __name__=="__main__": raise SystemExit(main())
