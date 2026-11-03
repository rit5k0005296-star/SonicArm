"""Desktop packaging of a four-way MANUAL board experiment. No board writes."""
from pathlib import Path
import ast
import copy
import hashlib
import json
import shutil
import sys
import zipfile
sys.dont_write_bytecode=True
WORK=Path(__file__).resolve().parent
ROOT=WORK.parents[1]
MODELS=ROOT.parents[1]
sys.path.insert(0,str(MODELS/'consistency-test/codex'))
from common import import_runtime,sha256
import_runtime('cpu')
import onnx
from onnx import helper as h


def cut(model,inputs,outputs):
    prod={o:n for n in model.graph.node for o in n.output}
    init={t.name:t for t in model.graph.initializer}
    visited=set();needed=set();weights=set();pending=list(outputs)
    while pending:
        name=pending.pop()
        if not name or name in visited:continue
        visited.add(name)
        if name in inputs:continue
        if name in init:weights.add(name);continue
        if name not in prod:raise ValueError('Unexpected graph dependency: '+name)
        n=prod[name];needed.add(n.name);pending.extend(n.input)
    result=copy.deepcopy(model)
    for field in ('node','initializer','input','output','value_info'):result.graph.ClearField(field)
    result.graph.node.extend(copy.deepcopy(n) for n in model.graph.node if n.name in needed)
    result.graph.initializer.extend(copy.deepcopy(t) for t in model.graph.initializer if t.name in weights)
    result.graph.input.extend(h.make_tensor_value_info(n,ty,shape) for n,(ty,shape) in inputs.items())
    meta={v.name:v for v in [*model.graph.output,*model.graph.value_info,*model.graph.input]}
    for n in outputs:
        if n in meta:result.graph.output.append(copy.deepcopy(meta[n]))
        else:raise ValueError('Missing output metadata: '+n)
    onnx.checker.check_model(result)
    return result


def assets():
    dest=WORK/'assets';dest.mkdir(parents=True,exist_ok=True)
    plan=json.loads((ROOT/'bundle/plans/all55/plan.json').read_text())
    first=ROOT/'bundle/plans/all55'/plan['ops'][0]['file']
    original=onnx.load(first)
    xq='/head/Unsqueeze_output_0_QuantizeLinear_Output'
    yq='/head/Reshape_output_0_QuantizeLinear_Output'
    original.graph.value_info.extend([h.make_tensor_value_info(xq,onnx.TensorProto.INT8,[1,1,80,'T']),
                                      h.make_tensor_value_info(yq,onnx.TensorProto.INT8,[1,320,'T'])])
    feat=('features',(onnx.TensorProto.FLOAT,[1,'T',80]))
    onnx.save(cut(original,dict([feat]),[xq]),dest/'fcm_input.onnx')
    onnx.save(cut(original,dict([feat]),[yq]),dest/'fcm_original.onnx')
    onnx.save(cut(original,dict([feat,(yq,(onnx.TensorProto.INT8,[1,320,'T']))]),plan['ops'][0]['outputs']),dest/'cpu000_after_fcm.onnx')
    fp32_path=MODELS/'consistency-test/codex/artifacts/camplus_fp32.onnx'
    fp32=onnx.load(fp32_path);changed=[]
    for n in fp32.graph.node:
        at={v.name:h.get_attribute_value(v) for v in n.attribute}
        if n.op_type=='AveragePool' and at.get('ceil_mode')==1 and at.get('count_include_pad')==1 and not any(at.get('pads',[])):
            for a in n.attribute:
                if a.name=='count_include_pad':a.i=0
            changed.append(n.name)
    if len(changed)!=52:raise ValueError('Expected the same52 pooling compatibility edits in FP32')
    onnx.checker.check_model(fp32);onnx.save(fp32,dest/'camplus_fp32_pool_compatible.onnx')
    report=dict(original_fp32_sha256=sha256(fp32_path),fp32_pool_compatibility_nodes=changed,
        original_qdq_sha256=sha256(ROOT/'bundle/camplus_int8_qdq.onnx'),
        first_cpu_file=first.relative_to(ROOT).as_posix(),first_cpu_sha256=sha256(first),
        xq=xq,yq=yq,graph_cut_scope='Only replace FCM; original remaining CPU ops, QDQ boundaries, all55 order and constants unchanged')
    (dest/'provenance.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    hardware=WORK/'hardware_v4';hardware.mkdir(exist_ok=True)
    source=MODELS/'FPGA-4/fcm_engine/deploy'
    manifest=json.loads((source/'upload_manifest.json').read_text())
    for name in [*manifest['files'],'upload_manifest.json']:
        dst=hardware/name;dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source/name,dst)
    print('ASSETS_READY FCM cut graphs + FP32 compatible graph + exact V4 hardware package',flush=True)


def package():
    def cell(kind,s):
        c=dict(cell_type=kind,metadata={},source=s.splitlines(True))
        if kind=='code':ast.parse(s);c.update(execution_count=None,outputs=[])
        return c
    cells=[cell('markdown','''# CPU FP32 / CPU INT8 / FPGA-3 / FPGA-4 整网对照

在电脑解压，把整个 `benchmark_compare` 文件夹放入现有 `full_model_test/evaluation/`。由你手动运行，不安装依赖、不改原模型或旧结果。
计算范围：同一板卡、1线程、同一完整原始Fbank→完整CAM++→L2→已注册余弦评分。包含CPU剩余运算、参数地址切换、DDR复制/缓存同步，排除采集/读音频/Fbank/逐层参考/首次加载。初始化单独记录；运行库已预先载入。
FP32及INT8完整CPU基线都开启ORT图优化；第三/四版沿用已验证的CPU分段图及原优化策略。四版都使用相同零显式padding AveragePool兼容语义。

先关闭其他正在使用FPGA的Notebook。本Notebook直接在持久kernel运行，禁止另开并行推理。若IP超时/运行中中断，保持kernel直到板卡断电重启，之后再重新开始。
'''),cell('code','''from pathlib import Path
import sys, uuid
sys.dont_write_bytecode=True
WORK=Path.cwd().resolve()
assert WORK.name=='benchmark_compare' and (WORK/'compare_benchmark.py').is_file(), '请从full_model_test/evaluation/benchmark_compare打开'
sys.path.insert(0,str(WORK))
from compare_benchmark import setup, hardware_check, integration_check, benchmark
RUN=WORK/'results'/('run_'+uuid.uuid4().hex)
INCLUDE_FP32=True
REPEATS=20
WARMUP=3
setup(RUN)
print('结果目录：',RUN)
'''),cell('markdown','## 1. 第四版独立硬件门控\n\n会加载新双IP Overlay，运行冒烟和完整FCM；已有本包同指纹PASS记录时可以复用。必须出现V4_HARDWARE_READY。\n'),
      cell('code','hardware_report=hardware_check(RUN)\n'),
      cell('markdown','## 2. 整网接入验证（不计时）\n\n检查CPU分图重建、FPGA逐层INT8/INT32，以及三段完整音频的CPU/V3/V4向量和分数。原QDQ漂移不自动改判通过；只有硬件逐点一致及分图重建通过才允许工程时延测试。出现INTEGRATION_READY后继续。\n'),
      cell('code','integration_report=integration_check(RUN, include_fp32=INCLUDE_FP32)\n'),
      cell('markdown','## 3. 正式模型测速\n\n每种模式、每条查询预热后测20次，分两轮反序执行；一次只保留一个运行时。逐层整数参考、调试输出和审计均关闭。全部模型推理及主机调用开销仍在计时内。\n'),
      cell('code','performance_report=benchmark(RUN, repeats=REPEATS, warmup=WARMUP, include_fp32=INCLUDE_FP32)\n'),
      cell('markdown','返回最后的MODEL_LATENCY、SPEEDUP_COMPARE、COMPARE_BENCHMARK_COMPLETED，以及本次results/run编号。summary.csv/summary.md可直接看中位数、P95和倍率；raw_samples.json保留全部样本。倍率小于1即更慢，按实测报告。精度/评分漂移单独报告，不输出未经校准的身份通过或拒绝，也不将模型时延写成音频端到端时延。\n')]
    nb=dict(nbformat=4,nbformat_minor=4,metadata=dict(kernelspec=dict(name='python3',display_name='Python 3 (ipykernel)',language='python')),cells=cells)
    (WORK/'06_cpu_v3_v4_compare.ipynb').write_text(json.dumps(nb,ensure_ascii=False,indent=2),encoding='utf8')
    files={}
    for p in sorted(WORK.rglob('*')):
        rel=p.relative_to(WORK)
        if not p.is_file() or any(k in rel.parts for k in ('results','diagnostics','__pycache__')) or p.name in ('manifest.json','prepare_compare.py','test_desktop.py') or rel.parts[0]=='hardware_v4':continue
        if p.suffix=='.ipynb':
            code=[''.join(c['source']) for c in json.loads(p.read_text(encoding='utf8'))['cells'] if c['cell_type']=='code']
            files[rel.as_posix()]=hashlib.sha256(json.dumps(code,ensure_ascii=False).encode()).hexdigest()
        else:files[rel.as_posix()]=sha256(p)
    manifest=dict(version='four_way_model_latency_1',files=files,hardware_manifest_sha256=sha256(WORK/'hardware_v4/upload_manifest.json'),
        root_manifest_sha256=sha256(ROOT/'upload_manifest.json'),actual_board_tested=False)
    (WORK/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
    output=ROOT/'updates/cpu_v3_v4_compare.zip'
    hw=json.loads((WORK/'hardware_v4/upload_manifest.json').read_text())
    names=[*files,'manifest.json',*('hardware_v4/'+x for x in [*hw['files'],'upload_manifest.json'])]
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for name in names:z.write(WORK/name,'benchmark_compare/'+name)
    print('COMPARE_PACKAGE_READY',output,output.stat().st_size,sha256(output),flush=True)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--package',action='store_true');args=parser.parse_args()
    package() if args.package else assets()
