"""Two-stage decisions and read-only diagnostics; no inference or ground truth in wire inputs."""
import json
from .core import DECISIONS, CASCADE_CONFIGS, combine_results
from .prompts import CASCADE_POLICY_VERSION


def review_input(email_text, prior_decision):
    if prior_decision not in DECISIONS:
        raise ValueError('유효한 로컬 판정이 필요합니다')
    return json.dumps({'email':json.loads(email_text), 'prior_assessment':{'decision':prior_decision}}, ensure_ascii=False, separators=(',', ':'))


def cascade_result(local, jev):
    result = combine_results(local, jev)
    if result['status'] == 'SUCCESS':
        result['decision'] = jev['decision']
    result.update(policy_version=CASCADE_POLICY_VERSION,
                  local_decision=local.get('decision') if local.get('status')=='SUCCESS' else None,
                  jev_decision=jev.get('decision') if jev.get('status')=='SUCCESS' else None,
                  decision_changed=local.get('decision')!=jev.get('decision') if result['status']=='SUCCESS' else None)
    if result['status']!='SUCCESS':
        result['error'] = local.get('error') or jev.get('error') or {'type':'incomplete_stage','message':'2단계 판정을 완료하지 못했습니다.'}
    return result


def cascade_diagnostics(samples, results, selected):
    finals={(r['config_id'],r['sample_id']):r for r in results if not r.get('component_for') and not r.get('is_warmup')}
    output={}
    for config in selected:
        if config not in CASCADE_CONFIGS: continue
        transitions={a:{b:0 for b in sorted(DECISIONS)} for a in sorted(DECISIONS)}
        baseline={k:0 for k in ('compared','improved','worsened','correct_to_review','review_to_correct','final_review','unavailable')}
        changes=compared=0
        for sample in samples:
            row=finals.get((config,sample['sample_id']),{})
            first,last=row.get('local_decision'),row.get('jev_decision')
            if row.get('status')=='SUCCESS' and first in DECISIONS and last in DECISIONS:
                transitions[first][last]+=1;compared+=1;changes+=first!=last
            base=finals.get(('jev',sample['sample_id']),{})
            if (base.get('status')!='SUCCESS' or row.get('status')!='SUCCESS'
                    or not base.get('input_hash') or base.get('input_hash')!=row.get('input_hash')):
                baseline['unavailable']+=1;continue
            baseline['compared']+=1
            truth=sample['label'];before=base['decision'];after=row['decision']
            baseline['improved']+=before in ('NORMAL','INJECTION') and before!=truth and after==truth
            baseline['worsened']+=before==truth and after in ('NORMAL','INJECTION') and after!=truth
            baseline['correct_to_review']+=before==truth and after=='REVIEW'
            baseline['review_to_correct']+=before=='REVIEW' and after==truth
            baseline['final_review']+=after=='REVIEW'
        output[config]={'N':len(samples),'compared':compared,'changed':changes,'unavailable':len(samples)-compared,
                        'transitions':transitions,'baseline':baseline}
    return output
