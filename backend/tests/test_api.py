from fastapi.testclient import TestClient
from app.main import create_app


def test_dataset_crud_and_exports_and_secrets(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        assert client.get('/api/runs').json()==[]
        result=client.post('/api/datasets/smoke')
        assert result.status_code==200
        ds=result.json()
        assert len(ds['samples'])>=3
        assert client.get(f"/api/datasets/{ds['id']}/export?format=csv").status_code==200
        assert 'openrouter_api_key' not in client.get('/api/settings').json()
        assert client.put('/api/settings',json={'openrouter_api_key':'never-store'}).status_code==422
        assert client.put('/api/settings',json={'ollama_url':'http://example.com'}).status_code==422
        assert client.post('/api/runs',json={'dataset_id':ds['id'],'configs':['jev'],'demo':False}).status_code==422
        assert client.post('/api/datasets',json={'name':'bad','samples':[{'sample_id':'1','subject':'a','body':'b','label':'REVIEW'}]}).status_code==422


def test_mock_run_refresh_export_retry(tmp_path):
    import time
    with TestClient(create_app(tmp_path)) as client:
        ds=client.post('/api/datasets/smoke').json()
        run=client.post('/api/runs',json={'dataset_id':ds['id'],'configs':['foundation_sec','qwen','jev','foundation_sec_then_jev','qwen_then_jev'],'demo':True}).json()
        for _ in range(300):
            saved=client.get('/api/runs/'+run['id']).json()
            if saved['status']=='COMPLETED': break
            time.sleep(.02)
        assert saved['status']=='COMPLETED'
        assert saved['totals']['api_calls']==0  # DEMO performs no physical API requests.
        assert len(saved['metrics'])==5
        assert client.get('/api/runs').json()==[]
        assert len(client.get('/api/runs?demo=true').json())==1
        assert client.get('/api/runs/'+run['id']+'/export?format=json').json()['dataset_snapshot']['id']==ds['id']
        assert client.get('/api/runs/'+run['id']+'/export?format=csv').status_code==200
        assert client.post('/api/runs/'+run['id']+'/retry').status_code==422
        assert client.delete('/api/runs/'+run['id']).status_code==200
        assert client.get('/api/runs/'+run['id']).status_code==404


def test_hostile_origin_cannot_write(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        assert client.post('/api/datasets/smoke',headers={'Origin':'https://hostile.example'}).status_code==403
