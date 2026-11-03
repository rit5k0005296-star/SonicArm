#!/usr/bin/env python3
"""Contract checks for AXI DMA, HLS m_axi, AXI-Stream, or VDMA paths."""
import argparse,json,time
from pathlib import Path
VALID={"axi_dma","hls_m_axi","axis","axi_vdma"}
def check(c,simulate_timeout=False):
    issues=[]; kind=c.get("kind")
    if kind not in VALID: issues.append("UNKNOWN_PATH_KIND")
    length=c.get("length_bytes"); alignment=c.get("alignment_bytes",1)
    if not isinstance(length,int) or length<=0: issues.append("INVALID_LENGTH")
    if not isinstance(alignment,int) or alignment<=0 or alignment&(alignment-1): issues.append("INVALID_ALIGNMENT")
    elif isinstance(length,int) and length%alignment: issues.append("LENGTH_NOT_ALIGNED")
    if kind in ("axi_dma","axi_vdma") and not c.get("cache_policy"): issues.append("CACHE_POLICY_UNSPECIFIED")
    if kind=="hls_m_axi" and c.get("dma_channel"): issues.append("HLS_M_AXI_IS_NOT_AXI_DMA")
    if simulate_timeout: issues.append("TRANSFER_TIMEOUT")
    return {"status":"FAIL" if issues else "PASS","issues":issues,"kind":kind}
def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--config",required=True); p.add_argument("--simulate-timeout",action="store_true"); p.add_argument("--json",action="store_true"); p.add_argument("--output"); a=p.parse_args()
    try: c=json.loads(Path(a.config).read_text(encoding="utf-8")); r=check(c,a.simulate_timeout)
    except Exception as e: r={"status":"FAIL","issues":[str(e)]}
    text=json.dumps(r,indent=2); print(text)
    if a.output: Path(a.output).write_text(text+"\n",encoding="utf-8")
    return 0 if r["status"]=="PASS" else 2
if __name__=="__main__": raise SystemExit(main())
