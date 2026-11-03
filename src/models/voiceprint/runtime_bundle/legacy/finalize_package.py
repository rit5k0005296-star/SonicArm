"""Desktop: create hash manifest and upload zip, only inside this directory."""
from pathlib import Path
import hashlib
import json
import sys
import zipfile
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent


def main():
    files={};notebook_sources={};notebook_cells={}
    for path in sorted(HERE.rglob('*')):
        name=path.relative_to(HERE).as_posix()
        if not path.is_file() or any(x in path.parts for x in ('test_results','desktop_validation','__pycache__','_board_deps','dependency_results','updates')) or name in ('upload_manifest.json','full_model_test.zip'):
            continue
        if path.suffix=='.pyc':
            continue
        files[name]=hashlib.sha256(path.read_bytes()).hexdigest()
        if path.suffix=='.ipynb':
            doc=json.loads(path.read_text(encoding='utf-8'))
            sources=[''.join(c.get('source',[])) for c in doc['cells'] if c['cell_type']=='code']
            notebook_sources[name]=hashlib.sha256(json.dumps(sources,ensure_ascii=False).encode('utf-8')).hexdigest()
            notebook_cells[name]=sources
    version=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
    manifest={'version_id':version,'files':files,'notebook_sources':notebook_sources,'notebook_cells':notebook_cells,'scope':'portable full-model package; no desktop runtimes bundled',
              'board_execution':'manual only','threshold':None}
    (HERE/'upload_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with zipfile.ZipFile(HERE/'full_model_test.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name in [*files,'upload_manifest.json']:
            archive.write(HERE/name,'full_model_test/'+name)
    print('VERSION',version,'files',len(files),'zip bytes',(HERE/'full_model_test.zip').stat().st_size)


if __name__=='__main__':
    main()
