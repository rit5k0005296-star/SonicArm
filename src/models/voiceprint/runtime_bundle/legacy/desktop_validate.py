"""Use verified Windows runtime; never use this bootstrap on ARM Linux."""
from pathlib import Path
import platform
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
if platform.system()!='Windows':
    raise RuntimeError('Desktop-only bootstrap; board uses run_full_model.py directly')
sys.path.insert(0,str(HERE.parents[1]/'consistency-test/codex'))
from common import import_runtime
import_runtime('cpu')
import torch
torch.set_num_threads(1)
from run_full_model import main


if __name__=='__main__':
    main()
