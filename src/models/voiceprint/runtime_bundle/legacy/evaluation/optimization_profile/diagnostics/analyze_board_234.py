"""Read only the copied board logs; never accesses or runs board hardware."""
from pathlib import Path
from collections import defaultdict
import json
import statistics as s
import hashlib

D = Path(__file__).resolve().parent / 'board_run_2348265b8eca4b48917ec3050039f912'


def read(name):
    return json.loads((D / name).read_text(encoding='utf8'))


def main():
    perf, raw, profile, correct = [read(n) for n in ('performance.json', 'raw_samples.json', 'profile_raw.json', 'correctness.json')]
    assert perf['completed'] and perf['actual_hardware'] and not perf['profile_enabled']
    assert perf['raw_samples'] == raw
    assert hashlib.sha256((D/'correctness.json').read_bytes()).hexdigest() == perf['correctness_sha256']
    assert perf['identity'] == correct['identity'] == read('setup.json')['identity']
    groups = defaultdict(list)
    for r in raw:
        groups[r['audio'], r['mode']].append(r)
    components = []
    for (audio, mode), rows in groups.items():
        summary = next(r for r in perf['summary'] if r['audio'] == audio and r['mode'] == mode)
        assert len(rows) == summary['n'] == 10
        assert abs(s.median(r['model_l2_score_ms'] for r in rows) - summary['median_ms']) < 1e-8
        assert {r['block'] for r in rows} == {0, 1}
        if mode != 'cpu_int8':
            assert all(r['pointwise_chunks'] == 55 and r['fcm_chunks'] == (12 if mode.startswith('v4') else 0) for r in rows)
        fields = ('model_ms', 'model_l2_score_ms', 'CPU_remaining_ms', 'layer_callback_ms', 'fpga_start_done_ms',
                  'parameter_address_size_switch_ms', 'input_ddr_copy_flush_ms', 'output_invalidate_copy_ms', 'output_concat_ms')
        med = {k: s.median(r[k] for r in rows) for k in fields}
        mean = {k: s.mean(r[k] for r in rows) for k in fields}
        mean['host_other_ms'] = mean['model_ms'] - mean['CPU_remaining_ms'] - mean['layer_callback_ms']
        mean['explicit_copy_config_concat_ms'] = sum(mean[k] for k in fields[-4:])
        components.append(dict(audio=audio, mode=mode, median=med, mean=mean))
    pg = defaultdict(list)
    for record in profile:
        assert len(record['cpu_sessions']) == (1 if record['mode'] == 'cpu_int8' else (57 if record['mode'].startswith('v4') else 56))
        assert len(record['fpga_layers']) == (0 if record['mode'] == 'cpu_int8' else (67 if record['mode'].startswith('v4') else 55))
        for row in record['cpu_sessions'] + record['fpga_layers']:
            pg[record['audio'], record['mode'], row['component'], row['name']].append(row)
    layer_rows = []
    for (audio, mode, component, name), rows in pg.items():
        assert len(rows) == 3
        key = 'cpu_session_ms' if component == 'CPU' else 'callback_ms'
        r = dict(audio=audio, mode=mode, component=component, name=name, median_ms=s.median(v[key] for v in rows))
        if component == 'CPU':
            r.update(input_count=rows[0]['inputs']['count'], output_count=rows[0]['outputs']['count'],
                     input_bytes=rows[0]['inputs']['bytes'], output_bytes=rows[0]['outputs']['bytes'],
                     largest_inputs=rows[0]['inputs']['largest'], largest_outputs=rows[0]['outputs']['largest'])
        else:
            r.update(input_shape=rows[0]['input_shape'], output_shape=rows[0]['output_shape'],
                     fpga_start_done_ms=s.median(v.get('fpga_start_done_ms', 0) for v in rows))
        layer_rows.append(r)
    ranking = []
    for audio, mode in groups:
        mine = [r for r in layer_rows if r['audio'] == audio and r['mode'] == mode]
        sums = {c: sum(r['median_ms'] for r in mine if r['component'] == c) for c in ('CPU', 'pointwise', 'FCM')}
        tops = {c: sorted([r for r in mine if r['component'] == c], key=lambda r:r['median_ms'], reverse=True)[:8]
                for c in sums}
        ranking.append(dict(audio=audio, mode=mode, sum_layer_medians_ms=sums, top=tops))
    init = read('initialization.json')
    all_audits = correct['hardware_audits']
    assert len(all_audits) == 12 and all(a['integer_embedding_exact'] for a in all_audits)
    assert all(r.get('integer_exact') for a in all_audits for r in a['layers'])
    reference = read('reference_self_check.json')
    assert len(reference) == 5 and all(r['INT8_exact'] and r['INT32_exact'] for r in reference)
    report = dict(evidence_consistent=True, actual_hardware=True, formal_samples=len(raw), profile_records=len(profile),
                  hardware_audit_cases=len(all_audits), components=components, profile_ranking=ranking,
                  initialization=[dict(mode=r['mode'], block=r['block'], initialization_ms=r['initialization_ms']) for r in init],
                  ratios=perf['ratios'], optimization_drift_gate=correct['optimization_drift_gate'],
                  original_QDQ_drift_gate=correct['original_QDQ_drift_gate'], scores=correct['scores'])
    (D/'analysis.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    print(json.dumps(dict(evidence_consistent=True, formal_samples=len(raw), profile_records=len(profile),
                          components=[dict(audio=r['audio'], mode=r['mode'], **{k:round(v,2) for k,v in r['mean'].items()}) for r in components],
                          ranking=[dict(audio=r['audio'], mode=r['mode'], sums=r['sum_layer_medians_ms'],
                                        top_CPU=[dict(name=v['name'], ms=round(v['median_ms'],2), inputs=v['input_count'], outputs=v['output_count']) for v in r['top']['CPU'][:4]],
                                        top_FCM=[dict(name=v['name'], ms=round(v['median_ms'],2)) for v in r['top']['FCM'][:3]],
                                        top_PW=[dict(name=v['name'], ms=round(v['median_ms'],2)) for v in r['top']['pointwise'][:3]]) for r in ranking]), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
