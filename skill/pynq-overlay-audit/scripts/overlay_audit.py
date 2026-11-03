#!/usr/bin/env python3
"""Read-only PYNQ HWH/bit/manifest auditor. Standard-library only."""
import argparse, hashlib, json, os, sys, xml.etree.ElementTree as ET
from pathlib import Path

def sha256(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""): h.update(block)
    return h.hexdigest()

def audit(hwh, bit=None, manifest=None, required=()):
    issues=[]; evidence={}; ips=[]; status="PASS"
    hwh=Path(hwh)
    if not hwh.is_file(): return {"status":"FAIL","issues":["HWH_MISSING"],"evidence":{}}
    evidence["hwh"]={"path":str(hwh),"sha256":sha256(hwh)}
    try: root=ET.parse(hwh).getroot()
    except ET.ParseError as e: return {"status":"FAIL","issues":[f"HWH_XML_INVALID:{e}"],"evidence":evidence}
    for node in root.iter():
        a={k.lower():v for k,v in node.attrib.items()}
        name=a.get("instance") or a.get("name") or a.get("fullname")
        base=a.get("basevalue") or a.get("baseaddr") or a.get("base_address")
        high=a.get("highvalue") or a.get("highaddr") or a.get("high_address")
        if name and base:
            try:
                start=int(base,0); end=int(high,0) if high else start
                if end < start: issues.append(f"INVALID_RANGE:{name}")
                ips.append({"name":name,"base":start,"high":end})
            except ValueError: issues.append(f"INVALID_ADDRESS:{name}")
    unique={(i["name"],i["base"],i["high"]):i for i in ips}; ips=list(unique.values())
    by_addr=sorted(ips,key=lambda x:(x["base"],x["high"]))
    for a,b in zip(by_addr,by_addr[1:]):
        if b["name"] != a["name"] and b["base"] <= a["high"] and (a["base"],a["high"]) != (b["base"],b["high"]):
            issues.append(f"ADDRESS_OVERLAP:{a['name']}:{b['name']}")
    names={i["name"] for i in ips}
    for name in required:
        if name not in names: issues.append(f"REQUIRED_IP_MISSING:{name}")
    if bit:
        bit=Path(bit)
        if not bit.is_file(): issues.append("BIT_MISSING")
        else: evidence["bit"]={"path":str(bit),"sha256":sha256(bit)}
    if manifest:
        try:
            m=json.loads(Path(manifest).read_text(encoding="utf-8"))
            for key in ("hwh","bit"):
                if key in m and key in evidence and m[key].get("sha256") != evidence[key]["sha256"]: issues.append(f"HASH_MISMATCH:{key}")
            evidence["identity"]="MANIFEST_MATCH" if not any(x.startswith("HASH_MISMATCH") for x in issues) else "MANIFEST_MISMATCH"
        except (OSError,json.JSONDecodeError,AttributeError) as e: issues.append(f"MANIFEST_INVALID:{e}")
    elif bit and Path(bit).is_file():
        evidence["identity"]="NO_MANIFEST"
    if issues: status="FAIL"
    return {"status":status,"issues":issues,"ip_count":len(ips),"ips":ips,"evidence":evidence}

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--hwh",required=True); p.add_argument("--bit"); p.add_argument("--manifest"); p.add_argument("--require-ip",action="append",default=[]); p.add_argument("--json",action="store_true"); p.add_argument("--output")
    a=p.parse_args(); result=audit(a.hwh,a.bit,a.manifest,a.require_ip); text=json.dumps(result,indent=2,ensure_ascii=False)
    if a.output:
        out=Path(a.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(text+"\n",encoding="utf-8")
    print(text); return 0 if result["status"]=="PASS" else 2
if __name__=="__main__": raise SystemExit(main())
