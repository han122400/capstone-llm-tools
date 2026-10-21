import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]


def converter():
    script=ROOT/'scripts'/'prepare_public_dataset.py'
    assert script.exists(), '재현 가능한 추출 스크립트가 필요합니다'
    spec=importlib.util.spec_from_file_location('public_converter',script)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def record(i, technique='fabricated_policy', scenario=None):
    return dict(id=str(i),scenario=scenario or f'scenario_{i}',category='work',pair={
        'attack':dict(external_content=f'Email {i}. policy preapproved assistant {i}',user_prompt='summarize',expected_action='summarize_only',injection_technique=technique),
        'benign':dict(external_content=f'Email {i}. ordinary business request {i}',user_prompt='reply',expected_action='send_reply')})


def test_pair_mapping_keeps_context_outside_model_and_no_invented_headers():
    module=converter()
    samples=module.convert_pair(record(1),version='abc',file_hash='hash',index=0,line=2)
    assert [s['label'] for s in samples]==['NORMAL','INJECTION']
    assert samples[0]['pair_id']==samples[1]['pair_id']
    for s in samples:
        assert s['subject']=='' and s['email']['content']['sender'] is None
        assert s['email']['content']['warnings'] is None and s['email']['content']['truncated'] is None
        assert s['created_at'] is None
        assert s['source_version']=='abc' and s['source_record_index']==0
        assert s['source_context']['user_prompt']
        assert s['body_hash'] != s['input_hash'] if 'input_hash' in s else s['body_hash']


def test_selection_is_seeded_pair_and_family_disjoint_quarantines_invalid():
    module=converter()
    records=[record(i,technique='fabricated_policy' if i<10 else 'peer_precedent') for i in range(20)]
    for i,r in enumerate(records):
        unique=['alpha','bravo','charlie','delta','echo','foxtrot','golf','hotel','india','juliet','kilo','lima','mike','november','oscar','papa','quebec','romeo','sierra','tango'][i]
        for b in ('attack','benign'): r['pair'][b]['external_content'] += ' '+unique+' unique scenario material'
    records.append(record(30,technique='unknown'))
    first=module.select_pairs(records,seed=42,evaluation_pairs=2,development_pairs=2,similarity_threshold=1.0)
    second=module.select_pairs(records,seed=42,evaluation_pairs=2,development_pairs=2,similarity_threshold=1.0)
    assert first==second
    evaluation,development,audit=first
    assert len(evaluation)==len(development)==2
    assert {r['id'] for r in evaluation}.isdisjoint(r['id'] for r in development)
    assert {r['pair']['attack']['injection_technique'] for r in evaluation}.isdisjoint(r['pair']['attack']['injection_technique'] for r in development)
    assert audit['quarantined'][0]['source_sample_id']=='30'


def test_identical_conflicting_pair_is_never_silently_relabelled():
    module=converter(); broken=record(1)
    broken['pair']['benign']['external_content']=broken['pair']['attack']['external_content']
    evaluation,development,audit=module.select_pairs([broken],seed=1,evaluation_pairs=50,development_pairs=10)
    assert evaluation==development==[]
    assert audit['quarantined'][0]['reason']=='identical_attack_benign'
