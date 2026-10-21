"""Read-only comparison of two stored real runs; never performs inference."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import statistics
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
RUN_SQL = 'SELECT payload FROM runs WHERE id=?'
RESULT_SQL = 'SELECT payload FROM results WHERE run_id=? ORDER BY rowid'


def read_run(db, identifier):
    run = json.loads(db.execute(RUN_SQL, (identifier,)).fetchone()[0])
    rows = [json.loads(r[0]) for r in db.execute(RESULT_SQL, (identifier,))]
    return run, rows


def summarize(run, rows):
    samples = {s['sample_id']: s for s in run['dataset_snapshot']['samples']}
    assert run['mode'] == 'reuse', 'This comparison expects reuse-mode runs.'
    result_configs = list(dict.fromkeys(run['selected_configs'] + run['dependencies']))
    assert len(rows) == len(samples) * len(result_configs)
    assert len({(r['sample_id'], r['config_id']) for r in rows}) == len(rows)
    by_id = {r['id']: r for r in rows}
    for r in rows:
        assert hashlib.sha256(r['input_text'].encode()).hexdigest() == r['input_hash']
        if r['config_id'].endswith('_jev'):
            a, b = [by_id[i] for i in r['component_result_ids']]
            assert a['sample_id'] == b['sample_id'] == r['sample_id']
            assert a['input_hash'] == b['input_hash'] == r['input_hash']
            assert r['policy_version'] == 'unanimous-or-review-v1'
            if a['status'] == b['status'] == 'SUCCESS':
                expected = a['decision'] if a['decision'] == b['decision'] else 'REVIEW'
                assert r['status'] == 'SUCCESS' and r['decision'] == expected
            else:
                assert r['status'] == 'ERROR' and r['decision'] is None
        elif r['status'] == 'SUCCESS':
            raw = r['raw_response']
            choice = raw['answers']['decision']['choice'] if r['config_id'] == 'jev' else json.loads(raw['message']['content'])['decision']
            assert r['decision'] == choice

    with urlopen(f"http://127.0.0.1:8001/api/runs/{run['id']}", timeout=10) as response:
        api = json.load(response)
    output = dict(id=run['id'], status=run['status'], started_at=run['started_at'],
                  finished_at=run['finished_at'], elapsed_s=(datetime.fromisoformat(run['finished_at'])-datetime.fromisoformat(run['started_at'])).total_seconds(),
                  selected_configs=run['selected_configs'], dependencies=run['dependencies'],
                  configs={}, errors=[], events=[], totals=api['totals'])
    for config in result_configs:
        group = [r for r in rows if r['config_id'] == config]
        confusion = {label: dict(Counter((r['decision'] if r['status']=='SUCCESS' else r['status'])
                                        for r in group if samples[r['sample_id']]['label']==label))
                     for label in ('NORMAL', 'INJECTION')}
        n = len(samples)
        attacks = sum(s['label']=='INJECTION' for s in samples.values())
        normal = n-attacks
        tp, fn = (confusion['INJECTION'].get(k,0) for k in ('INJECTION','NORMAL'))
        fp, tn = (confusion['NORMAL'].get(k,0) for k in ('INJECTION','NORMAL'))
        review = sum(confusion[k].get('REVIEW',0) for k in confusion)
        errors = sum(r['status']=='ERROR' for r in group)
        fractions = dict(automatic_rate=(tp+fn+fp+tn,n), correct_rate=(tp+tn,n),
                         injection_detection_rate=(tp,attacks), miss_rate=(fn,attacks),
                         false_positive_rate=(fp,normal),review_rate=(review,n),error_rate=(errors,n),
                         precision=(tp,tp+fp),recall=(tp,tp+fn),f1=(2*tp,2*tp+fp+fn))
        metrics = {k:dict(numerator=a,denominator=b,value=a/b if b else None) for k,(a,b) in fractions.items()}
        if config in api['metrics']:
            for k,m in metrics.items():
                for field,value in m.items(): assert api['metrics'][config]['metrics'][k][field] == value
        times = {status:[r['latency_ms'] for r in group if r['status']==status and r.get('latency_ms') is not None] for status in ('SUCCESS','ERROR')}
        metadata = group[0].get('model_metadata') or {}
        output['configs'][config] = dict(confusion=confusion,metrics=metrics,
            status_counts=dict(Counter(r['status'] for r in group)),
            latency={k:dict(n=len(v),mean_ms=statistics.mean(v) if v else None,median_ms=statistics.median(v) if v else None) for k,v in times.items()},
            attempts=sum(len(r.get('attempts') or []) for r in group),
            retries=sum(max(0,len(r.get('attempts') or [])-1) for r in group),
            actual_models=sorted({r['actual_model'] for r in group if r.get('actual_model')}),
            prompt_versions=sorted({r['prompt_version'] for r in group}),
            digest=metadata.get('digest'),thinking_applied=metadata.get('thinking_applied'),
            prompt_tokens=[r['raw_response'].get('prompt_eval_count') for r in group if isinstance(r.get('raw_response'),dict) and 'prompt_eval_count' in r['raw_response']])
    for r in rows:
        if r['status']=='ERROR':
            raw=r.get('raw_response') or {}
            output['errors'].append(dict(config=r['config_id'],sample_id=r['sample_id'],label=samples[r['sample_id']]['label'],
                error=r.get('error'),done_reason=raw.get('done_reason'),output_tokens=raw.get('eval_count'),
                final_content_empty=not (raw.get('message') or {}).get('content'),
                thinking_present=bool((raw.get('message') or {}).get('thinking')),latency_ms=r.get('latency_ms'),
                component_result_ids=r.get('component_result_ids')))
    for e in run['events']:
        d=e.get('details') or {}; m=d.get('metadata') or {}
        output['events'].append(dict(component=e['component'],event=e['event'],at=e['at'],
            status=d.get('status'),unloaded=d.get('unloaded'),remaining_models=d.get('remaining_models'),
            load_ms=m.get('load_ms'),ps_before=m.get('ps_before'),
            ps_after_names=[x.get('name') for x in m.get('ps_after',[])],warnings=d.get('warnings')))
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline'); parser.add_argument('current'); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    with sqlite3.connect((ROOT/'runtime/real.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
        old,old_rows=read_run(db,args.baseline); new,new_rows=read_run(db,args.current)
    assert old['dataset_snapshot']==new['dataset_snapshot']
    old_map={(r['config_id'],r['sample_id']):r for r in old_rows}
    changes=[]
    for r in new_rows:
        previous=old_map[(r['config_id'],r['sample_id'])]
        assert r['input_text']==previous['input_text'] and r['input_hash']==previous['input_hash']
        assert r['preprocess_version']==previous['preprocess_version']
        if (previous['status'],previous['decision'])!=(r['status'],r['decision']):
            changes.append(dict(config=r['config_id'],sample_id=r['sample_id'],
                                before=[previous['status'],previous['decision']],after=[r['status'],r['decision']]))
    report=dict(captured_at=datetime.now(timezone.utc).isoformat(),dataset_snapshot_identical=True,
        all_inputs_and_hashes_identical=True,dataset=old['dataset_snapshot']['name'],
        dataset_id=old['dataset_snapshot']['id'],dataset_version=old['dataset_snapshot']['version'],
        class_counts=dict(Counter(s['label'] for s in old['dataset_snapshot']['samples'])),
        settings_changes={k:[old['settings'].get(k),new['settings'].get(k)] for k in old['settings'].keys()|new['settings'].keys() if old['settings'].get(k)!=new['settings'].get(k)},
        baseline=summarize(old,old_rows),current=summarize(new,new_rows),changes=changes,
        verification='Independent metric counts agree with dashboard API; raw choices, hashes and ensemble lineage checked.',
        queries=[RUN_SQL,RESULT_SQL])
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['dataset_snapshot_identical','all_inputs_and_hashes_identical','class_counts','settings_changes','changes','verification']},ensure_ascii=False,indent=2))


if __name__=='__main__': main()
