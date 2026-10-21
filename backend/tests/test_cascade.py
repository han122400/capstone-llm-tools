import asyncio
import json
import itertools
import httpx
import pytest
from app import core
from app.store import Store
from app.engine import Engine
from app.adapters import JevAdapter


def test_new_selection_and_legacy_registry():
    assert set(core.ACTIVE_CONFIGS) == {'foundation_sec','qwen','jev','foundation_sec_then_jev','qwen_then_jev'}
    assert 'foundation_sec_jev' in core.ALL_CONFIGS
    assert core.component_dependencies(['foundation_sec_then_jev','qwen_then_jev']) == ['foundation_sec','qwen','jev']


@pytest.mark.parametrize('local,final', itertools.product(['NORMAL','INJECTION','REVIEW'], repeat=2))
def test_final_jev_choice_not_forced_to_review(local, final):
    from app.cascade import cascade_result
    result = cascade_result({'status':'SUCCESS','decision':local}, {'status':'SUCCESS','decision':final})
    assert result['decision'] == final and result['status'] == 'SUCCESS'
    assert result['decision_changed'] == (local != final)


@pytest.mark.parametrize('status', ['ERROR','CANCELLED','PENDING','SKIPPED','RUNNING'])
def test_unfinished_local_never_produces_final(status):
    from app.cascade import cascade_result
    result = cascade_result({'status':status,'decision':None}, {'status':'SUCCESS','decision':'NORMAL'})
    assert result['status'] == status and result['decision'] is None and result['decision_changed'] is None


def test_jev_review_wire_input_and_criteria_without_metadata():
    from app.prompts import CRITERIA, CASCADE_PROMPT_VERSION, jev_review_question
    async def scenario():
        captured=[]
        def handler(request):
            captured.append(json.loads(request.content))
            return httpx.Response(200,json={'answers':{'decision':{'type':'choice','choice':'INJECTION'}}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter=JevAdapter({'openrouter_api_key':'test-only','max_attempts':1},client)
            text=core.model_input({'subject':'업무','body':'검토','label':'INJECTION','notes':'SECRET_NOTE','sample_id':'SECRET_ID'})
            response=await adapter.predict_with_prior(text,'NORMAL')
            payload=captured[0]
            assert json.loads(payload['state']) == {'email':json.loads(text),'prior_assessment':{'decision':'NORMAL'}}
            assert 'SECRET' not in json.dumps(payload)
            assert payload['questions']['decision'] == jev_review_question()
            assert payload['questions']['decision']['criteria'] == CRITERIA
            assert response['question_version'] == CASCADE_PROMPT_VERSION
            assert response['decision']=='INJECTION'
    asyncio.run(scenario())


@pytest.mark.parametrize('mode', ['reuse','live'])
@pytest.mark.parametrize('failure', ['local_error','cancel_after_local','jev_error'])
def test_failure_and_cancellation_no_normal_fallback_or_extra_calls(tmp_path,mode,failure):
    async def scenario():
        store=Store(tmp_path);calls=[]
        ds=store.save_dataset({'name':'test','samples':[{'sample_id':'a','subject':'s','body':'b','label':'INJECTION'}]})
        run=store.create_run({'dataset_id':ds['id'],'configs':['qwen_then_jev'],'demo':True,'mode':mode},{})
        class Adapter:
            async def prepare(self):return {'status':'SUCCESS'}
            async def release(self):return {'status':'SUCCESS','unloaded':True}
            async def predict(self,text):
                calls.append('local')
                if failure=='cancel_after_local':store.cancel(run['id'],True)
                return {'status':'ERROR' if failure=='local_error' else 'SUCCESS','decision':None if failure=='local_error' else 'NORMAL','error':{'type':'test_failure'} if failure=='local_error' else None}
            async def predict_with_prior(self,text,decision):
                calls.append('jev');return {'status':'ERROR','decision':None,'error':{'type':'timeout'},'attempts':[{'status':'ERROR'}]}
        await Engine(store,factory=lambda *a,**k:Adapter()).execute(run['id'],True)
        saved=store.get_run(run['id'],True)
        final=next(r for r in saved['results'] if r['config_id']=='qwen_then_jev')
        assert final['decision'] is None and final['status'] in ('ERROR','CANCELLED')
        assert final.get('decision_changed') is None
        assert calls==(['local','jev'] if failure=='jev_error' else ['local'])
        assert saved['cascade_diagnostics']['qwen_then_jev']['baseline']['unavailable']==1
    asyncio.run(scenario())


def test_diagnostics_distinguishes_corrections_deferrals_and_missing_baseline():
    from app.cascade import cascade_diagnostics
    samples=[{'sample_id':str(i),'label':'INJECTION'} for i in range(5)]
    rows=[]
    for i,(before,after) in enumerate([('NORMAL','INJECTION'),('INJECTION','NORMAL'),('INJECTION','REVIEW'),('REVIEW','INJECTION'),('NORMAL','NORMAL')]):
        rows.extend([
            {'config_id':'jev','sample_id':str(i),'status':'SUCCESS','decision':before,'input_hash':'h'},
            {'config_id':'qwen_then_jev','sample_id':str(i),'status':'SUCCESS','decision':after,'input_hash':'different' if i==4 else 'h','local_decision':'NORMAL','jev_decision':after}])
    result=cascade_diagnostics(samples,rows,['qwen_then_jev'])['qwen_then_jev']
    assert result['changed']==3 and result['compared']==5
    assert result['baseline']=={'compared':4,'improved':1,'worsened':1,'correct_to_review':1,'review_to_correct':1,'final_review':1,'unavailable':1}


def test_new_api_rejects_legacy_selection_but_preserves_history(tmp_path):
    from fastapi.testclient import TestClient
    from app.main import create_app
    app=create_app(tmp_path);store=app.state.store
    ds=store.save_dataset({'name':'old','samples':[{'sample_id':'a','subject':'s','body':'b','label':'NORMAL'}]})
    old=store.create_run({'dataset_id':ds['id'],'configs':['qwen_jev'],'demo':True},{})
    old.update(status='COMPLETED');store.update_run(old)
    before=store.run_metadata(old['id'],True)
    with TestClient(app) as client:
        assert {c['id'] for c in client.get('/api/configs').json()}==set(core.ACTIVE_CONFIGS)
        assert client.post('/api/runs',json={'dataset_id':ds['id'],'configs':['qwen_jev'],'demo':True}).status_code==422
        assert client.get('/api/runs/'+old['id']).json()['selected_configs']==['qwen_jev']
        assert client.post('/api/runs/'+old['id']+'/retry').status_code==422
        assert store.run_metadata(old['id'],True)==before


@pytest.mark.parametrize('mode,expected_local,expected_jev', [('reuse',2,3),('live',4,3)])
def test_cascade_execution_calls_lineage_cost_and_baseline(tmp_path,mode,expected_local,expected_jev):
    async def scenario():
        store=Store(tmp_path);calls=[];active=set()
        class Adapter:
            def __init__(self,c): self.c=c
            async def prepare(self):
                if self.c!='jev':
                    assert not active;active.add(self.c)
                return {'status':'SUCCESS'}
            async def release(self):
                active.discard(self.c);return {'status':'SUCCESS','unloaded':True}
            async def predict(self,text):
                calls.append((self.c,text,None))
                return {'status':'SUCCESS','decision':'NORMAL','latency_ms':1,'cost':.1 if self.c=='jev' else None,'attempts':[{'status':'SUCCESS'}]}
            async def predict_with_prior(self,text,decision):
                assert self.c=='jev';calls.append((self.c,text,decision))
                return {'status':'SUCCESS','decision':'INJECTION','latency_ms':2,'cost':.1,'attempts':[{'status':'SUCCESS'}]}
        ds=store.save_dataset({'name':'test','samples':[{'sample_id':'same','subject':'email','body':'body','label':'INJECTION'}]})
        run=store.create_run({'dataset_id':ds['id'],'configs':list(core.ACTIVE_CONFIGS),'demo':True,'mode':mode},{})
        await Engine(store,factory=lambda c,*a,**k:Adapter(c)).execute(run['id'],True)
        saved=store.get_run(run['id'],True)
        assert saved['status']=='COMPLETED' and not active
        assert sum(c[0]!='jev' for c in calls)==expected_local
        assert sum(c[0]=='jev' for c in calls)==expected_jev
        assert len({c[1] for c in calls})==1
        assert saved['totals']['cost_usd']==pytest.approx(.3)
        assert saved['totals']['api_calls']==3
        for config in ('foundation_sec_then_jev','qwen_then_jev'):
            row=next(r for r in saved['results'] if r['config_id']==config)
            assert row['decision']=='INJECTION' and row['local_decision']=='NORMAL' and row['decision_changed']
            assert len(row['component_result_ids'])==2
            assert row['local_result_reused']==(mode=='reuse')
            assert (row['latency_ms'] is None)==(mode=='reuse')
            parts=[r for r in saved['results'] if r['id'] in row['component_result_ids']]
            second=next(r for r in parts if r['config_id']=='jev')
            assert second['email_input_hash']==row['input_hash']
            assert second['input_hash']!=row['input_hash']
            assert json.loads(second['input_text'])['prior_assessment']['decision']=='NORMAL'
            diagnostic=saved['cascade_diagnostics'][config]
            assert diagnostic['changed']==1 and diagnostic['baseline']['improved']==1
        from app.statistics import aggregate_statistics
        # Accumulation must preserve transitions without merging historical ensembles.
        duplicate={**saved,'id':'another-attempt'}
        aggregate=aggregate_statistics([saved,duplicate])
        assert 'qwen_jev' not in aggregate['metrics']
        assert aggregate['metrics']['qwen_then_jev']['N']==2
        assert aggregate['cascade_diagnostics']['qwen_then_jev']['changed']==2
        assert aggregate['cascade_diagnostics']['qwen_then_jev']['baseline']['improved']==2
        assert aggregate['totals']['api_calls']==6
        from app.store import export_csv
        exported=export_csv(saved['results'])
        assert 'local_decision' in exported and 'jev_decision' in exported and 'decision_changed' in exported
    asyncio.run(scenario())


@pytest.mark.parametrize('mode',['reuse','live'])
def test_cascade_only_does_not_infer_jev_baseline(tmp_path,mode):
    async def scenario():
        store=Store(tmp_path)
        ds=store.save_dataset({'name':'only','samples':[{'sample_id':'a','subject':'s','body':'b','label':'NORMAL'}]})
        run=store.create_run({'dataset_id':ds['id'],'configs':['qwen_then_jev'],'demo':True,'mode':mode},{})
        await Engine(store).execute(run['id'],True)
        saved=store.get_run(run['id'],True)
        jev=[r for r in saved['results'] if r['config_id']=='jev']
        assert len(jev)==1 and jev[0]['component_for']=='qwen_then_jev'
        assert jev[0]['status']=='SUCCESS' and jev[0]['is_mock']
        assert saved['totals']['api_calls']==0  # Mock responses do not claim real HTTP calls.
        assert saved['cascade_diagnostics']['qwen_then_jev']['baseline']['compared']==0
        assert saved['cascade_diagnostics']['qwen_then_jev']['baseline']['unavailable']==1
    asyncio.run(scenario())
