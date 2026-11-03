"""Read-only ONNX inspection of interfaces implicated by board profile."""
from pathlib import Path
from collections import Counter
import json
import sys

sys.dont_write_bytecode = True
WORK = Path(__file__).resolve().parents[1]
ROOT = WORK.parents[1]
sys.path.insert(0, str(ROOT.parents[1] / 'consistency-test/codex'))
from common import import_runtime
import_runtime('cpu')
import onnx


def main():
    original = onnx.load(ROOT / 'bundle/camplus_int8_qdq.onnx')
    static = {v.name for v in original.graph.initializer}
    producers = {out:n for n in original.graph.node for out in n.output}
    for n in original.graph.node:
        if n.op_type == 'Constant' or (n.input and all(v in static for v in n.input if v) and
                                      n.op_type not in ('RandomNormal', 'RandomUniform', 'RandomNormalLike', 'RandomUniformLike', 'Dropout')):
            static.update(n.output)
    paths = ['bundle/plans/all55/cpu_000.onnx', 'evaluation/benchmark_compare/assets/cpu000_after_fcm.onnx',
             'compatible_all55_assets/graph_36.onnx', 'compatible_all55_assets/graph_37.onnx',
             'compatible_all55_assets/graph_53.onnx', 'compatible_all55_assets/graph_54.onnx']
    rows = []
    for path in paths:
        g = onnx.load(ROOT / path).graph
        inputs = [v.name for v in g.input]
        init = {v.name for v in g.initializer}
        dynamic_quantization_parameters = []
        for n in g.node:
            if n.op_type in ('QuantizeLinear', 'DequantizeLinear'):
                for i in n.input[1:3]:
                    if i in inputs:
                        dynamic_quantization_parameters.append(i)
        r = dict(path=path, nodes=len(g.node), operators=dict(Counter(n.op_type for n in g.node)),
                 graph_inputs=len(inputs), static_inputs=[v for v in inputs if v in static],
                 dynamic_inputs=[v for v in inputs if v not in static],
                 initializer_count=len(init), outputs=len(g.output),
                 static_outputs=sum(v.name in static for v in g.output),
                 quantization_parameters_as_graph_inputs=sorted(set(dynamic_quantization_parameters)),
                 convs=[dict(name=n.name, inputs=list(n.input), attributes={a.name:onnx.helper.get_attribute_value(a) for a in n.attribute})
                        for n in g.node if n.op_type == 'Conv'])
        rows.append(r)
    output = WORK/'diagnostics/board_run_2348265b8eca4b48917ec3050039f912/graph_inspection.json'
    output.write_text(json.dumps(rows, indent=2, ensure_ascii=False)+'\n', encoding='utf8')
    print(json.dumps(rows, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
