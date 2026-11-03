#!/usr/bin/env python3
import datetime,hashlib,json,platform,subprocess,sys
from pathlib import Path
root=Path(__file__).parents[1]; out=root/"evals/results"; out.mkdir(parents=True,exist_ok=True)
cmd=[sys.executable,"-m","unittest","discover","-s",str(root/"tests"),"-v"]
p=subprocess.run(cmd,text=True,capture_output=True)
r={"timestamp":datetime.datetime.now(datetime.timezone.utc).isoformat(),"python":sys.version,"platform":platform.platform(),"command":cmd,"returncode":p.returncode,"stdout":p.stdout,"stderr":p.stderr}
path=out/"regression_test_run.json"; path.write_text(json.dumps(r,indent=2)); print(json.dumps({"status":"PASS" if p.returncode==0 else "FAIL","result":str(path)})); raise SystemExit(p.returncode)
