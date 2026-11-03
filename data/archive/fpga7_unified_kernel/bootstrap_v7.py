"""Create an isolated V7 source tree from the verified V6 source baseline.

Generated HLS/Vivado products, caches, logs, DCP, BIT and HWH files are never
imported.  Test vectors are copied because they are the functional reference.
The script refuses to overwrite any destination file.
"""
from pathlib import Path
import hashlib
import json
import shutil


ROOT = Path(__file__).resolve().parent
V6 = ROOT.parent / "FPGA-6"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def rewrite(text: str) -> str:
    return (
        text.replace("FPGA-6", "FPGA-7")
        .replace("fpga_v6", "fpga_v7")
        .replace("V6", "V7")
        .replace("v6", "v7")
        .replace("PW6", "PW7")
        .replace("FCM6", "FCM7")
        .replace("V:/", "U:/")
        .replace("V:\\", "U:\\")
        .replace("V:", "U:")
        .replace("56365046", "56375046")
    )


TEXT_FILES = [
    "src/pointwise.cpp",
    "src/pointwise.h",
    "src/fcm.cpp",
    "src/fcm.h",
    "src/packed.h",
    "tests/tb_pointwise.cpp",
    "tests/tb_fcm.cpp",
    "tests/abi_adapters.h",
    "tests/test_packed.cpp",
    "tests/native_exports.cpp",
    "tests/check_packed_mutation.py",
    "tests/desktop_workflow_check.py",
    "run_hls.ps1",
    "run_native.ps1",
    "pw.cfg",
    "fcm.cfg",
]


def main() -> None:
    if not V6.is_dir():
        raise RuntimeError(f"Missing V6 baseline: {V6}")

    pins = {}
    for relative in TEXT_FILES:
        source = V6 / relative
        target = ROOT / rewrite(relative)
        if target.exists():
            raise RuntimeError(f"Refusing to overwrite {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rewrite(source.read_text(encoding="utf-8")), encoding="utf-8")
        pins[f"FPGA-6/{relative}"] = sha256(source)

    for kind in ("pw", "fcm"):
        source = V6 / "tests" / f"{kind}_cases"
        target = ROOT / "tests" / f"{kind}_cases"
        if target.exists():
            raise RuntimeError(f"Refusing to overwrite {target}")
        shutil.copytree(source, target)
        for path in target.rglob("*"):
            if path.is_file():
                pins[path.relative_to(ROOT).as_posix()] = sha256(path)

    for directory in ("hls", "logs", "reports", "tool_temp"):
        (ROOT / directory).mkdir(exist_ok=True)

    baseline = {
        "source": "FPGA-6 verified desktop and board baseline",
        "device": "xc7z020clg400-1",
        "tool": "Vivado/Vitis 2025.2",
        "clock_mhz": 100,
        "v6_run": "run_ecddaa97a20f4d0caf60427bf327e120",
        "v6_resources": {
            "lut": 46328,
            "slice": 13093,
            "bram_tile": 112.5,
            "dsp": 211,
            "wns_ns": 0.062,
            "whs_ns": 0.008,
        },
        "pins": pins,
    }
    (ROOT / "reports" / "v6_baseline_pins.json").write_text(
        json.dumps(baseline, indent=2), encoding="utf-8"
    )
    print(f"V7_ISOLATED_IMPORT text_files={len(TEXT_FILES)} pinned_files={len(pins)}")


if __name__ == "__main__":
    main()
