"""Prove the packed-byte checker rejects an off-by-one byte-enable defect.

Only isolated fixture copies are mutated. The kernel/IP/RTL sources stay intact.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    original = ROOT / 'src/packed.h'
    before = digest(original)
    fixture = ROOT / 'tool_temp/packed_mutation'
    fixture.mkdir(parents=True, exist_ok=True)
    header = original.read_text(encoding='utf8')
    test = (ROOT / 'tests/test_packed.cpp').read_text(encoding='utf8')
    # Keep the same checks, using a deterministic failure exit rather than a
    # Windows abort dialog. Never define NDEBUG for either fixture build.
    test = test.replace('#include <cassert>', '#include <cstdlib>\n'
                        '#define CHECK(c) do { if (!(c)) { std::cerr << '
                        '"CHECK_REJECT line=" << __LINE__ << "\\n"; '
                        'std::exit(17); } } while (0)')
    test = test.replace('assert(', 'CHECK(')
    (fixture / 'test.cpp').write_text(test, encoding='utf8')
    environment = {**os.environ, 'PATH': 'D:/msys64/ucrt64/bin;' + os.environ['PATH']}
    compiler = 'D:/msys64/ucrt64/bin/g++.exe'
    logs, observed = [], {}
    for name, text in [('baseline', header),
                       ('mutated', header.replace('if(lane<count)', 'if(lane<=count)'))]:
        if name == 'mutated' and text == header:
            raise RuntimeError('Mutation anchor no longer exists')
        (fixture / 'packed.h').write_text(text, encoding='utf8')
        executable = fixture / (name + '.exe')
        compile_result = subprocess.run([compiler, '-O2', '-std=c++14', '-DV5_PORTABLE',
            '-I' + str(fixture), str(fixture / 'test.cpp'), '-o', str(executable)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=environment, timeout=60)
        logs.append(name + ' compile:\n' + compile_result.stdout)
        compile_result.check_returncode()
        result = subprocess.run([str(executable)], text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, env=environment, timeout=30)
        logs.append(name + ' run:\n' + result.stdout + 'exit=' + str(result.returncode))
        observed[name] = dict(exit_code=result.returncode, output=result.stdout)
    if observed['baseline']['exit_code'] != 0 or 'V5_PACKED_BYTE_MASK_PASS 1152' not in observed['baseline']['output']:
        raise AssertionError('Unmodified fixture failed')
    if observed['mutated']['exit_code'] != 17 or 'CHECK_REJECT' not in observed['mutated']['output']:
        raise AssertionError('Broken byte enable was not rejected by the checker')
    if digest(original) != before:
        raise AssertionError('Production source changed during isolated mutation check')
    (fixture / 'packed.h').write_text(header, encoding='utf8')
    (fixture / 'mutated.exe').unlink()
    (ROOT / 'logs/packed_mutation.log').write_text('\n'.join(logs) + '\n', encoding='utf8')
    report = dict(pass_=True, source_sha256=before, original_source_unchanged=True,
                  mutation='isolated copy only: lane<count changed to lane<=count',
                  outcomes=observed, actual_hardware=False)
    (ROOT / 'reports/packed_mutation.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print('V5_PACKED_MUTATION_REJECT_PASS production source unchanged')


if __name__ == '__main__':
    main()
