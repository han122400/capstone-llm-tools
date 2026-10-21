import asyncio
import json
import pytest
from app.store import Store, export_csv, parse_import
from app.engine import Engine


def sample(sid='a', label='NORMAL', body='회의는 내일입니다.'):
    return dict(sample_id=sid, subject='테스트', body=body, label=label,
                language='ko', category='업무', synthetic=True)


def test_snapshot_and_demo_isolation(tmp_path):
    store = Store(tmp_path)
    ds = store.save_dataset(dict(name='첫 데이터', split='development', samples=[sample()]))
    run = store.create_run(dict(dataset_id=ds['id'], configs=['qwen'], demo=True, mode='reuse'), {})
    store.save_dataset(dict(name='수정', split='development', samples=[sample(body='changed')]), ds['id'])
    assert store.get_run(run['id'], True)['dataset_snapshot']['samples'][0]['body'] != 'changed'
    assert store.list_runs(False) == []
    assert len(store.list_runs(True)) == 1


def test_csv_formula_and_import_validation():
    text = export_csv([dict(subject='=1+1', body='\t@SUM(A1)', count=2)])
    assert "'=1+1" in text and "'\t@SUM(A1)" in text
    assert parse_import('json', json.dumps([sample()]))[0]['label'] == 'NORMAL'
    with pytest.raises(ValueError):
        parse_import('json', json.dumps([sample(label='REVIEW')]))


def test_restart_marks_interrupted(tmp_path):
    store = Store(tmp_path)
    ds = store.save_dataset(dict(name='d', samples=[sample()]))
    run = store.create_run(dict(dataset_id=ds['id'], configs=['qwen'], demo=False, mode='reuse'), {})
    Store(tmp_path).recover()
    assert store.get_run(run['id'], False)['status'] == 'INTERRUPTED'


def test_reuse_calls_and_cost_traces(tmp_path):
    async def scenario():
        store = Store(tmp_path)
        ds = store.save_dataset(dict(name='d', samples=[sample(), sample('b','INJECTION')]))
        calls=[]
        class Fake:
            async def prepare(self): return {'status':'SUCCESS'}
            async def release(self): return {'status':'SUCCESS'}
            async def predict(self, text):
                calls.append(text)
                return dict(status='SUCCESS',decision='NORMAL',cost=0.1,latency_ms=3,attempts=[{'status':'SUCCESS'}],provider='fake')
        engine=Engine(store, factory=lambda *args, **kwargs: Fake())
        run=store.create_run(dict(dataset_id=ds['id'],configs=['foundation_sec','qwen','jev','foundation_sec_jev','qwen_jev'],demo=True,mode='reuse'), {})
        await engine.execute(run['id'], True)
        result=store.get_run(run['id'], True)
        assert len(calls)==6
        assert len(result['results'])==10
        assert result['totals']['api_calls']==2
        assert result['totals']['cost_usd']==pytest.approx(0.2)
        combined=[r for r in result['results'] if r['config_id'].endswith('_jev')]
        assert all(len(r['component_result_ids'])==2 and r['latency_ms'] is None and r['reused'] for r in combined)
        assert result['status']=='COMPLETED'
        for metric in result['metrics'].values(): assert metric['N']==2
    asyncio.run(scenario())


def test_cancellation_has_no_decision(tmp_path):
    async def scenario():
        store=Store(tmp_path)
        ds=store.save_dataset(dict(name='d',samples=[sample(),sample('b')]))
        engine=Engine(store)
        run=store.create_run(dict(dataset_id=ds['id'],configs=['qwen_jev'],demo=True,mode='reuse'), {})
        store.cancel(run['id'],True)
        await engine.execute(run['id'],True)
        result=store.get_run(run['id'],True)
        assert result['status']=='CANCELLED'
        assert all(r['decision'] is None for r in result['results'])
    asyncio.run(scenario())
