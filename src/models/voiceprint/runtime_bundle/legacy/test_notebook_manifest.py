"""Validate notebook save tolerance without weakening code/model integrity."""
import json
from unittest.mock import patch
import runtime_core as core


def main():
    root=core.HERE/'desktop_validation/notebook_manifest_test'
    root.mkdir(parents=True,exist_ok=True)
    notebook=root/'example.ipynb';model=root/'model.bin'
    doc={'cells':[{'cell_type':'code','source':['x = 1\n'],'execution_count':None,'outputs':[],
                   'metadata':{}}],'metadata':{}}
    notebook.write_text(json.dumps(doc),encoding='utf-8');model.write_bytes(b'original model')
    manifest={'version_id':'test-version','files':{'example.ipynb':core.digest(notebook),'model.bin':core.digest(model)},
              'notebook_sources':{'example.ipynb':core.notebook_source_digest(notebook)},
              'notebook_cells':{'example.ipynb':['x = 1\n']}}
    (root/'upload_manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    with patch.object(core,'HERE',root):
        assert core.verify_manifest()=='test-version'
        doc['cells'][0].update(execution_count=7,outputs=[{'output_type':'stream','name':'stdout','text':'output'}])
        doc['metadata']['trusted']=True
        notebook.write_text(json.dumps(doc),encoding='utf-8')
        assert core.verify_manifest()=='test-version'
        doc['cells'].append({'cell_type':'code','source':['print("user operation history")\n']})
        notebook.write_text(json.dumps(doc),encoding='utf-8')
        assert core.verify_manifest()=='test-version'
        doc['cells'][0]['source']=['x = 2\n']
        notebook.write_text(json.dumps(doc),encoding='utf-8')
        try:
            core.verify_manifest()
        except ValueError:
            pass
        else:
            raise AssertionError('Changed code was accepted')
        doc['cells'][0]['source']=['x = 1\n'];notebook.write_text(json.dumps(doc),encoding='utf-8')
        model.write_bytes(b'changed model')
        try:
            core.verify_manifest()
        except ValueError:
            pass
        else:
            raise AssertionError('Changed model was accepted')
    core.save(core.HERE/'desktop_validation/notebook_manifest_fix.json',{
        'pass':True,'saved_outputs_allowed':True,'appended_operation_history_allowed':True,
        'changed_code_rejected':True,'changed_model_rejected':True})
    print('Notebook manifest regression PASS')


if __name__=='__main__':
    main()
