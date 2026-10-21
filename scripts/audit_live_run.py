"""Read-only audit of a stored live experiment; never performs inference."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import statistics
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def audit(identifier):
    with sqlite3.connect((ROOT / 'runtime/real.sqlite3').as_uri() + '?mode=ro', uri=True) as db:
        run = json.loads(db.execute('SELECT payload FROM runs WHERE id=?', (identifier,)).fetchone()[0])
        rows = [json.loads(x[0]) for x in db.execute('SELECT payload FROM results WHERE run_id=? ORDER BY rowid', (identifier,))]
    assert run['mode'] == 'live' and not run['demo']
    with urlopen(f'http://127.0.0.1:8001/api/runs/{identifier}', timeout=30) as response:
        api = json.load(response)
    samples = {s['sample_id']: s for s in run['dataset_snapshot']['samples']}
    primary = [r for r in rows if not r.get('component_for') and not r.get('is_warmup')]
    physical = [r for r in rows if not r['config_id'].endswith('_jev') and not r.get('reused')]
    by_id = {r['id']: r for r in rows}
    assert len(primary) == len(samples) * len(run['selected_configs'])
    assert len({(r['sample_id'], r['config_id']) for r in primary}) == len(primary)
    hashes = defaultdict(set)
    linked = []
    for r in rows:
        assert hashlib.sha256(r['input_text'].encode()).hexdigest() == r['input_hash']
        hashes[r['sample_id']].add(r['input_hash'])
        if r['config_id'].endswith('_jev'):
            a, b = [by_id[i] for i in r['component_result_ids']]
            assert a['sample_id'] == b['sample_id'] == r['sample_id']
            assert a['component_for'] == b['component_for'] == r['config_id']
            assert a['config_id'] == r['config_id'].removesuffix('_jev') and b['config_id'] == 'jev'
            assert r['policy_version'] == 'unanimous-or-review-v1'
            assert a['status'] == b['status'] == r['status'] == 'SUCCESS'
            assert r['decision'] == (a['decision'] if a['decision'] == b['decision'] else 'REVIEW')
            linked.extend(r['component_result_ids'])
        elif r['status'] == 'SUCCESS':
            raw = r['raw_response']
            choice = raw['answers']['decision']['choice'] if r['config_id'] == 'jev' else json.loads(raw['message']['content'])['decision']
            assert choice == r['decision']
    assert all(len(v) == 1 for v in hashes.values())
    assert len(linked) == len(set(linked)) == len(rows) - len(primary)
    output = dict(run_id=identifier, audited_at=datetime.now(timezone.utc).isoformat(), mode=run['mode'],
        status=run['status'], started_at=run['started_at'], finished_at=run['finished_at'],
        elapsed_s=(datetime.fromisoformat(run['finished_at'])-datetime.fromisoformat(run['started_at'])).total_seconds(),
        sample_count=len(samples), pair_count=len({s.get('pair_id') for s in samples.values()}),
        ground_truth=dict(Counter(s['label'] for s in samples.values())), primary_results=len(primary),
        saved_results=len(rows), physical_requests=len(physical), totals=api['totals'], configs={}, physical_groups={},
        validation={'same_input_per_sample': True, 'raw_choices_match': True, 'ensemble_lineage_and_policy_match': True,
                    'api_metrics_match': True, 'api_cost_matches': True}, repeated_decisions={}, source_families={},
        status_counts=dict(Counter(r['status'] for r in rows)),
        prompt_versions=sorted({r['prompt_version'] for r in rows}),
        missing_parent_started_at=sum(r['started_at'] is None for r in primary if r['config_id'].endswith('_jev')),
        saved_max_input_bytes=run['settings'].get('max_input_bytes'),
        effective_input_limits=sorted({r['input_limit']['limit'] for r in physical}),
        actual_input_bytes={'min':min(len(r['input_text'].encode()) for r in physical), 'max':max(len(r['input_text'].encode()) for r in physical)},
        retries=sum(max(0,len(r.get('attempts') or [])-1) for r in physical),
        experiment_resources=run.get('experiment_resources'),
        model_identity={config: next(r['model_metadata'].get('model_identity') for r in physical if r['config_id']==config) for config in ('foundation_sec','qwen')},
        local_done_reasons=dict(Counter(r['raw_response'].get('done_reason') for r in physical if r['config_id']!='jev')))
    for config in run['selected_configs']:
        group = [r for r in primary if r['config_id'] == config]
        confusion = {label: dict(Counter(r['decision'] if r['status']=='SUCCESS' else r['status'] for r in group if samples[r['sample_id']]['label']==label)) for label in ('NORMAL','INJECTION')}
        tp,fn = (confusion['INJECTION'].get(k,0) for k in ('INJECTION','NORMAL'))
        fp,tn = (confusion['NORMAL'].get(k,0) for k in ('INJECTION','NORMAL'))
        n=len(samples); attack=sum(s['label']=='INJECTION' for s in samples.values())
        review=sum(c.get('REVIEW',0) for c in confusion.values())
        fractions=dict(automatic_rate=(tp+fn+fp+tn,n),correct_rate=(tp+tn,n),injection_detection_rate=(tp,attack),miss_rate=(fn,attack),false_positive_rate=(fp,n-attack),review_rate=(review,n),error_rate=(sum(r['status']=='ERROR' for r in group),n),precision=(tp,tp+fp),recall=(tp,tp+fn),f1=(2*tp,2*tp+fp+fn))
        metrics={k:dict(numerator=a,denominator=b,value=a/b if b else None) for k,(a,b) in fractions.items()}
        for k,m in metrics.items():
            for field,value in m.items():
                assert api['metrics'][config]['metrics'][k][field] == value, (config,k,field)
        latencies=sorted(r['latency_ms'] for r in group)
        output['configs'][config]=dict(confusion=confusion,metrics=metrics,latency_ms=dict(mean=statistics.mean(latencies),median=statistics.median(latencies),p95_nearest_rank=latencies[math.ceil(len(latencies)*0.95)-1],max=max(latencies)))
        output['source_families'][config]={family:dict(Counter(r['decision'] for r in group if samples[r['sample_id']]['label']=='INJECTION' and samples[r['sample_id']].get('template_family')==family)) for family in sorted({s.get('template_family') for s in samples.values()})}
    for config in ('foundation_sec','qwen','jev'):
        groups=defaultdict(list)
        for r in physical:
            if r['config_id']==config:
                groups[r.get('component_for') or 'standalone'].append(r)
        output['physical_groups'][config]={k:dict(requests=len(v),decisions=dict(Counter(r['decision'] for r in v)),cost=sum(r['cost'] for r in v if r['cost'] is not None) if config=='jev' else None) for k,v in groups.items()}
        standalone={r['sample_id']:r for r in groups['standalone']}
        for context,group in groups.items():
            if context!='standalone':
                output['repeated_decisions'][f'{config}:standalone_vs_{context}']=[dict(sample_id=r['sample_id'],label=samples[r['sample_id']]['label'],standalone=standalone[r['sample_id']]['decision'],repeated=r['decision']) for r in group if standalone[r['sample_id']]['decision'] != r['decision']]
    jev_rows=[r for r in physical if r['config_id']=='jev']
    costs=sum(r['cost'] for r in jev_rows if r['cost'] is not None)
    assert len(jev_rows) == api['totals']['api_calls']
    assert abs(costs-api['totals']['cost_usd']) < 1e-12
    output['jev_actual_models']=dict(Counter(r['actual_model'] for r in jev_rows))
    output['jev_wrong_confidence']=[dict(sample_id=r['sample_id'],context=r.get('component_for') or 'standalone',decision=r['decision'],confidence=r['confidence']) for r in jev_rows if r['decision'] != samples[r['sample_id']]['label']]
    foundation=[r for r in physical if r['config_id']=='foundation_sec']
    slow=[r for r in foundation if r['latency_ms']>5000]
    output['foundation_tail']=dict(requests=len(foundation),over_5s=len(slow),share_of_request_time=sum(r['latency_ms'] for r in slow)/sum(r['latency_ms'] for r in foundation),thinking_responses=sum(bool(r['raw_response']['message'].get('thinking')) for r in foundation),max_output_tokens=max(r['raw_response']['eval_count'] for r in foundation),slow_requests=[dict(sample_id=r['sample_id'],context=r.get('component_for') or 'standalone',decision=r['decision'],latency_ms=r['latency_ms'],output_tokens=r['raw_response']['eval_count'],generation_ms=r['raw_response']['eval_duration']/1e6,done_reason=r['raw_response']['done_reason']) for r in sorted(slow,key=lambda r:r['latency_ms'],reverse=True)])
    output['events']=[dict(component=e['component'],event=e['event'],at=e['at'],status=(e.get('details') or {}).get('status'),unloaded=(e.get('details') or {}).get('unloaded'),remaining_models=(e.get('details') or {}).get('remaining_models')) for e in run['events']]
    return output


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    result=audit(args.run_id)
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ['jev_wrong_confidence','events','source_families']},ensure_ascii=False,indent=2))
