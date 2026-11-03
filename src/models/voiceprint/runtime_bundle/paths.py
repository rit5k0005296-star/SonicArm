"""Self-contained runtime paths for the submitted FPGA-10 package."""
from pathlib import Path
import sys

WORK = Path(__file__).resolve().parent
LEGACY = WORK / "legacy"
if not (LEGACY / "runtime_core.py").is_file():
    raise RuntimeError("Submitted voiceprint runtime bundle is incomplete")
COMPARE = LEGACY / "evaluation" / "benchmark_compare"
OPT = LEGACY / "evaluation" / "optimization_profile"
for path in (LEGACY, COMPARE, OPT):
    sys.path.insert(0, str(path))
