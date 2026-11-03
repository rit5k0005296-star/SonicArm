"""Regression: real board blank-line edit, supported tuning, reject code edits."""
from pathlib import Path
import ast
import json
import shutil
import sys

sys.dont_write_bytecode = True
WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[1]
sys.path.insert(0, str(ROOT.parents[1] / 'consistency-test/codex'))
from common import import_runtime
import_runtime('cpu')
sys.path.insert(0, str(WORK))
import optimization_profile as tests


def main():
    tests.validate_files()
    m = json.loads((WORK / 'manifest.json').read_text(encoding='utf8'))
    name = '07_cpu_graph_optimization_profile.ipynb'
    original = m['notebook_cells'][name]
    wanted = tests.notebook_program(original)
    observed = tests.core.notebook_sources(WORK / 'diagnostics/board_notebook_hash_error.ipynb')
    if tests.core.notebook_source_digest(WORK / 'diagnostics/board_notebook_hash_error.ipynb') == m['files'][name]:
        raise AssertionError('Board reproduction did not differ in raw text')
    if tests.notebook_program(observed) != wanted:
        raise AssertionError('Actual board whitespace regression not fixed')
    variant = list(original)
    variant[0] = variant[0].replace('PROFILE_REPEATS=3', 'PROFILE_REPEATS = 1').replace('REPEATS=10', 'REPEATS = 20').replace('WARMUP=2', 'WARMUP = 1')
    variant[1] = '# user comment\n' + variant[1] + '\n\n'
    variant += ['', '\n# empty comment cell\n']
    if tests.notebook_program(variant) != wanted:
        raise AssertionError('Documented tuning/formatting rejected')
    for edit in ('REPEATS=3', 'REPEATS=True', 'REPEATS=0', 'REPEATS=int(20)'):
        bad = [s.replace('REPEATS=10', edit) for s in original]
        try:
            tests.notebook_program(bad)
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid configuration was accepted: ' + edit)
    variants = [original + ['print("unexpected execution")\n'],
                [s.replace('baseline_only=True', 'baseline_only=False') for s in original],
                [s.replace('correctness(RUN)', 'benchmark(RUN)') for s in original],
                [s.replace('repeats=REPEATS', 'repeats=2') for s in original]]
    for bad in variants:
        if tests.notebook_program(bad) == wanted:
            raise AssertionError('Changed executable statement was accepted')
    for cell in original:
        ast.parse(cell)
    # Exercise the actual manifest validator with the captured board Notebook,
    # including its outputs and autosaved formatting, in an isolated local copy.
    fixture = WORK / 'diagnostics/validation_fixture'
    fixture.mkdir(parents=True, exist_ok=True)
    for file in ('optimization_profile.py', 'README.md', 'manifest.json'):
        shutil.copy2(WORK / file, fixture / file)
    board_notebook = json.loads((WORK / 'diagnostics/board_notebook_hash_error.ipynb').read_text(encoding='utf8'))
    (fixture / name).write_text(json.dumps(board_notebook, ensure_ascii=False), encoding='utf8')
    old_work = tests.WORK
    tests.WORK = fixture
    try:
        tests.validate_files()
        board_notebook['cells'].append(dict(cell_type='code', metadata={}, execution_count=None,
                                            outputs=[], source=['print("unexpected")\n']))
        (fixture / name).write_text(json.dumps(board_notebook, ensure_ascii=False), encoding='utf8')
        try:
            tests.validate_files()
        except ValueError as error:
            if 'Notebook executable statements changed' not in str(error):
                raise
        else:
            raise AssertionError('Manifest validator accepted changed execution')
    finally:
        tests.WORK = old_work
    tests.save(WORK / 'diagnostics/notebook_validation.json', dict(pass_=True, actual_hardware=False,
               reproduced_board_blank_line_error=True, formatting_and_numeric_tuning_accepted=True,
               changed_execution_rejected=True, invalid_configuration_rejected=True,
               source_sha256=tests.core.digest(WORK / 'optimization_profile.py'),
               package_sha256=tests.core.digest(ROOT / 'updates/cpu_optimization_profile.zip')))
    print('NOTEBOOK_VALIDATION_REGRESSION_PASS', flush=True)


if __name__ == '__main__':
    main()
