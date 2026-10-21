"""Read-only comparison of stored Qwen thinking experiments; no inference."""
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


def read_run(db, identifier):
    run = json.loads(db.execute('SELECT payload FROM runs WHERE id=?', (identifier,)).fetchone()[0])
    rows = [json.loads(x[0]) for x in db.execute('SELECT payload FROM results WHERE run_id=? ORDER BY rowid', (identifier,))]
    return run, rows


def analyze(run, rows):
    samples = {s['sample_id']:s for s in run['dataset_snapshot']['samples']}
    with urlopen(f"http://127.0.0.1:8001/api/runs/{run['id']}", timeout=15) as response:
        api = json.load(response)
    by_id = {r['id']:r for r in rows}
    for r in rows:
        assert hashlib.sha256(r['input_text'].encode()).hexdigest() == r['input_hash']
        if r['status']!='SUCCESS':
            assert r['decision'] is None
        elif not r['config_id'].endswith('_then_jev'):
            raw=r['raw_response']
            choice=raw['answers']['decision']['choice'] if r['config_id']=='jev' else json.loads(raw['message']['content'])['decision']
            assert r['decision']==choice
        if r['config_id'].endswith('_then_jev'):
            first,last=[by_id[i] for i in r['component_result_ids']]
            assert first['sample_id']==last['sample_id']==r['sample_id']
            if first['status']=='ERROR':
                assert last['status']=='SKIPPED' and not last['attempts']
                assert r['status']=='ERROR' and r['decision'] is None
            else:
                assert r['status']==last['status'] and r['decision']==last['decision']
    out={'id':run['id'],'created_at':run['created_at'],'started_at':run['started_at'],'finished_at':run['finished_at'],
         'mode':run['mode'],'selected_configs':run['selected_configs'],'configs':{},'totals':api['totals'],
         'prompt':run['environment']['prompt_version'],'review_prompt':run['environment']['cascade_prompt_version'],
         'snapshot_samples':len(samples),'labels':dict(Counter(s['label'] for s in samples.values()))}
    for config in run['selected_configs']:
        group=[r for r in rows if r['config_id']==config and not r.get('component_for')]
        assert len(group)==len(samples)
        assert len({r['sample_id'] for r in group})==len(samples)
        confusion={label:dict(Counter(r['decision'] if r['status']=='SUCCESS' else r['status'] for r in group if samples[r['sample_id']]['label']==label)) for label in ('NORMAL','INJECTION')}
        tp,fn=(confusion['INJECTION'].get(k,0) for k in ('INJECTION','NORMAL'))
        fp,tn=(confusion['NORMAL'].get(k,0) for k in ('INJECTION','NORMAL'))
        n=len(samples); attacks=sum(s['label']=='INJECTION' for s in samples.values())
        fractions=dict(automatic_rate=(tp+fn+fp+tn,n),correct_rate=(tp+tn,n),injection_detection_rate=(tp,attacks),miss_rate=(fn,attacks),false_positive_rate=(fp,n-attacks),review_rate=(sum(v.get('REVIEW',0) for v in confusion.values()),n),error_rate=(sum(r['status']=='ERROR' for r in group),n),precision=(tp,tp+fp),recall=(tp,tp+fn),f1=(2*tp,2*tp+fp+fn))
        metrics={k:dict(numerator=a,denominator=b,value=a/b if b else None) for k,(a,b) in fractions.items()}
        for key,m in metrics.items():
            for field,value in m.items(): assert api['metrics'][config]['metrics'][key][field]==value
        latency={}
        for status in ('SUCCESS','ERROR','ALL'):
            times=[r['latency_ms'] for r in group if r.get('latency_ms') is not None and (status=='ALL' or r['status']==status)]
            latency[status]=dict(n=len(times),mean_ms=statistics.mean(times) if times else None,median_ms=statistics.median(times) if times else None,max_ms=max(times) if times else None)
        out['configs'][config]=dict(confusion=confusion,metrics=metrics,latency=latency)
    qwen=[r for r in rows if r['config_id']=='qwen' and not r.get('component_for')]
    out['qwen_requests']=[dict(sample_id=r['sample_id'],label=samples[r['sample_id']]['label'],status=r['status'],decision=r['decision'],error=r.get('error'),latency_ms=r['latency_ms'],
        output_tokens=r['raw_response'].get('eval_count'),input_tokens=r['raw_response'].get('prompt_eval_count'),done_reason=r['raw_response'].get('done_reason'),
        final_content_empty=not r['raw_response']['message'].get('content'),thinking_present=bool(r['raw_response']['message'].get('thinking')),
        think_sent=r['request_options'].get('think'),think_applied=r['model_metadata'].get('thinking_applied'),
        generation_ms=r['raw_response'].get('eval_duration',0)/1e6,input_ms=r['raw_response'].get('prompt_eval_duration',0)/1e6,
        attempts=len(r.get('attempts') or [])) for r in qwen]
    out['qwen_identity']=qwen[0]['model_metadata'].get('model_identity')
    out['qwen_digest']=qwen[0]['model_metadata'].get('digest')
    out['qwen_total_generation_ms']=sum(r['generation_ms'] for r in out['qwen_requests'])
    out['qwen_total_latency_ms']=sum(r['latency_ms'] for r in out['qwen_requests'])
    jev=[r for r in rows if r['config_id']=='jev' and r['attempts']]
    out['jev_attempted_rows']=len(jev)
    out['jev_skipped']=sum(r['config_id']=='jev' and r['status']=='SKIPPED' for r in rows)
    assert len(jev)==api['totals']['api_calls']
    assert abs(sum(r['cost'] for r in jev)-api['totals']['cost_usd'])<1e-12
    out['jev_models']=dict(Counter(r.get('actual_model') for r in jev))
    return out


def compare(off_id,on_id):
    with sqlite3.connect((ROOT/'runtime/real.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
        off,off_rows=read_run(db,off_id);on,on_rows=read_run(db,on_id)
    assert off['dataset_snapshot']==on['dataset_snapshot']
    assert off['mode']==on['mode']=='reuse'
    assert off['environment']['system_prompt']==on['environment']['system_prompt']
    assert off['environment']['jev_review_question']==on['environment']['jev_review_question']
    changes={k:{'off':off['settings'].get(k),'on':on['settings'].get(k)} for k in off['settings'].keys()|on['settings'].keys() if off['settings'].get(k)!=on['settings'].get(k)}
    assert changes=={'qwen_thinking':{'off':False,'on':True}}
    old={r['sample_id']:r for r in off_rows if r['config_id']=='qwen'}
    for row in [r for r in on_rows if r['config_id']=='qwen']:
        before=old[row['sample_id']]
        for key in ('input_text','input_hash','preprocess_version','prompt_version'): assert before[key]==row[key]
        for key in ('digest','effective_options'): assert before['model_metadata'][key]==row['model_metadata'][key]
    before=analyze(off,off_rows);after=analyze(on,on_rows)
    old_final={r['sample_id']:r for r in off_rows if r['config_id']=='qwen_then_jev'}
    blocked_previous_detections=[r['sample_id'] for r in on_rows if r['config_id']=='qwen_then_jev' and r['status']=='ERROR' and old_final[r['sample_id']]['decision']=='INJECTION']
    surviving_changes=[r['sample_id'] for r in on_rows if r['config_id']=='qwen_then_jev' and r['status']=='SUCCESS' and r['decision']!=old_final[r['sample_id']]['decision']]
    return dict(audited_at=datetime.now(timezone.utc).isoformat(),off=before,on=after,settings_changes=changes,
        validation={'same_dataset_snapshot':True,'same_qwen_inputs_digest_options_prompt':True,'same_jev_review_question':True,'api_metrics_and_cost_match':True,'raw_final_choices_match':True,'lineage_and_upstream_skips_match':True},
        previous_cascade_detections_now_blocked_by_local_error=blocked_previous_detections,surviving_cascade_decision_changes=surviving_changes,
        limitations=['Single paired development set, 10 NORMAL and 10 INJECTION; no causal generalization across hardware/server state.',
                    'Selected configurations differ; do not compare whole-run duration as Qwen speed.',
                    'Errors are not NORMAL/REVIEW or successful detections; survivor-only accuracy omits 14 failures.'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('off');p.add_argument('on');p.add_argument('--output',required=True);args=p.parse_args()
    result=compare(args.off,args.on)
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    for name in ('off','on'):
        r=result[name]
        print(json.dumps({'run':name,'id':r['id'],'configs':r['configs'],'totals':r['totals'],'qwen_generation_share':r['qwen_total_generation_ms']/r['qwen_total_latency_ms'],'jev_attempted_rows':r['jev_attempted_rows'],'jev_skipped':r['jev_skipped'],'identity':r['qwen_identity']},ensure_ascii=False))
    print(json.dumps({k:v for k,v in result.items() if k not in ('off','on')},ensure_ascii=False))
