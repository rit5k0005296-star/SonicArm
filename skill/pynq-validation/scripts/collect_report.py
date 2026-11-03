#!/usr/bin/env python3
"""Collect golden, benchmark, timing, and utilization artifacts into JSON/Markdown."""
import argparse, json, re, statistics
from pathlib import Path


def _number(pattern, text):
    match = re.search(pattern, text, re.I | re.M)
    return float(match.group(1)) if match else None


def parse_timing(path):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    return {"wns_ns": _number(r"WNS\s*\(ns\).*?\n\s*(-?\d+(?:\.\d+)?)", text),
            "tns_ns": _number(r"TNS\s*\(ns\).*?\n\s*-?\d+(?:\.\d+)?\s+(-?\d+(?:\.\d+)?)", text)}


def parse_utilization(path):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    names = {"lut": "Slice LUTs", "ff": "Slice Registers", "bram": "Block RAM Tile", "dsp": "DSPs"}
    result = {}
    for key, label in names.items():
        match = re.search(r"\|\s*" + re.escape(label) + r"\s*\|\s*([0-9.]+)\s*\|\s*([0-9.]+)", text, re.I)
        if match:
            result[key] = {"used": float(match.group(1)), "available": float(match.group(2))}
    return result


def benchmark_stats(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    values = data.get("latency_ms", data) if isinstance(data, dict) else data
    values = [float(v) for v in values]
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, max(0, int((len(ordered) - 1) * 0.95 + 0.5)))]
    return {"count": len(values), "mean_ms": statistics.fmean(values), "median_ms": statistics.median(values), "p95_ms": p95}


def collect(timing=None, utilization=None, benchmark=None):
    result = {"status": "PASS", "artifacts": {}}
    if timing: result["artifacts"]["timing"] = parse_timing(timing)
    if utilization: result["artifacts"]["utilization"] = parse_utilization(utilization)
    if benchmark: result["artifacts"]["benchmark"] = benchmark_stats(benchmark)
    if not result["artifacts"]: result = {"status": "FAIL", "artifacts": {}, "issues": ["NO_INPUT_ARTIFACTS"]}
    return result


def markdown(result):
    lines = ["# Validation Summary", "", f"Status: **{result['status']}**", ""]
    for name, values in result.get("artifacts", {}).items():
        lines += [f"## {name.title()}", "", "```json", json.dumps(values, indent=2), "```", ""]
    return "\n".join(lines)


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--timing"); p.add_argument("--utilization"); p.add_argument("--benchmark"); p.add_argument("--output-json",required=True); p.add_argument("--output-md",required=True); a=p.parse_args()
    result=collect(a.timing,a.utilization,a.benchmark)
    Path(a.output_json).write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    Path(a.output_md).write_text(markdown(result),encoding="utf-8")
    print(json.dumps(result,indent=2)); return 0 if result["status"]=="PASS" else 2
if __name__=="__main__": raise SystemExit(main())
