#!/usr/bin/env python3
"""Golden-vector and evidence-level validator with machine-readable output."""
import argparse,csv,json,math,re
from pathlib import Path
LEVELS=("STATIC","SIMULATION","HLS","SYNTHESIS","IMPLEMENTATION","BOARD","END_TO_END")
def golden(actual,expected,atol,rtol):
    if len(actual)!=len(expected): return False,{"reason":"SHAPE_MISMATCH"}
    errs=[abs(float(a)-float(e)) for a,e in zip(actual,expected)]; ok=all(x<=atol+rtol*abs(float(e)) for x,e in zip(errs,expected))
    return ok,{"max_abs_error":max(errs,default=0.0),"count":len(errs)}
def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--actual"); p.add_argument("--expected"); p.add_argument("--atol",type=float,default=1e-6); p.add_argument("--rtol",type=float,default=1e-5); p.add_argument("--level",choices=LEVELS,default="STATIC"); p.add_argument("--board-evidence"); p.add_argument("--output",required=True); p.add_argument("--json",action="store_true"); a=p.parse_args()
    checks=[]
    if a.actual and a.expected:
        try:
            av=json.loads(Path(a.actual).read_text()); ev=json.loads(Path(a.expected).read_text()); ok,detail=golden(av,ev,a.atol,a.rtol); checks.append({"name":"golden","status":"PASS" if ok else "FAIL",**detail})
        except Exception as e: checks.append({"name":"golden","status":"FAIL","reason":str(e)})
    else: checks.append({"name":"golden","status":"FAIL","reason":"INPUTS_MISSING"})
    status="FAIL" if any(x["status"]=="FAIL" for x in checks) else "PASS"
    result={"status":status,"stage":a.level,"board_artifact":a.board_evidence,"checks":checks}
    out=Path(a.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,indent=2)+"\n"); print(json.dumps(result,indent=2)); return 0 if status=="PASS" else 2
if __name__=="__main__": raise SystemExit(main())
