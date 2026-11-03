"""Negative control for NEW cross-tile carry logic; original sources untouched."""
from pathlib import Path
import hashlib,json,os,subprocess
R=Path(__file__).resolve().parents[1]
src=R/'src/fcm.cpp'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
before=sha(src)
text=src.read_text()
anchor='uint64_t carry=tb ? carries[o*4+row] :'
assert anchor in text
fixture=R/'tool_temp/fcm_mutation'
fixture.mkdir(parents=True,exist_ok=True)
mutated=fixture/'fcm.cpp'
mutated.write_text(text.replace(anchor,'uint64_t carry=tb ? UINT64_C(0) :'))
env={**os.environ,'PATH':'D:/msys64/ucrt64/bin;'+os.environ['PATH']}
exe=fixture/'reject.exe'
command=['D:/msys64/ucrt64/bin/g++.exe','-O2','-std=c++14','-DV6_PORTABLE','-I'+str(R/'src'),'-I'+str(R/'tests'),str(R/'tests/tb_fcm.cpp'),str(mutated),'-o',str(exe)]
build=subprocess.run(command,env=env,capture_output=True,text=True,timeout=60)
build.check_returncode()
run=subprocess.run([str(exe),str(R/'tests/fcm_cases')],env=env,capture_output=True,text=True,timeout=90)
assert run.returncode==1 and 'Kernel mismatch' in run.stderr,(run.returncode,run.stdout,run.stderr)
assert before==sha(src)
report=dict(pass_=True,actual_hardware=False,source_sha256=before,mutation='drop cross-tile row carry in isolated fixture',exit_code=run.returncode,diagnostic=run.stderr.strip())
(R/'reports/fcm_mutation.json').write_text(json.dumps(report,indent=2))
(R/'logs/fcm_mutation.log').write_text(build.stdout+build.stderr+run.stdout+run.stderr)
mutated.write_text(text)
exe.unlink()
print('V6_NEW_FCM_CARRY_MUTATION_REJECT_PASS')
