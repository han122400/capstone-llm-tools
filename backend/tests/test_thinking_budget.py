"""Budget regressions use isolated databases and mocked HTTP, never inference."""
import asyncio
import json

import httpx
from fastapi.testclient import TestClient

from app.adapters import OllamaAdapter
from app.core import common_input_limit
from app.main import create_app


def test_settings_accept_joint_budget_reject_invalid_partial_update_and_preserve_snapshot(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        response = client.put('/api/settings', json={
            'context_length':8192, 'max_output_tokens':4096,
            'qwen_thinking':True, 'timeout_seconds':480})
        assert response.status_code == 200
        settings = response.json()
        assert settings['input_limit_bytes'] > 1500
        assert settings['input_budget']['output_reserved_tokens'] == 4096
        ds = client.post('/api/datasets/smoke').json()
        run = client.app.state.store.create_run(
            {'dataset_id':ds['id'],'configs':['qwen'],'demo':True}, settings)
        # Partial updates must be validated against the already persisted counterpart.
        assert client.put('/api/settings',json={'context_length':4096}).status_code == 422
        assert client.get('/api/settings').json()['context_length'] == 8192
        assert client.put('/api/settings',json={'max_output_tokens':8192}).status_code == 422
        assert client.put('/api/settings',json={'qwen_thinking':False}).status_code == 200
        saved = client.get('/api/runs/'+run['id']).json()
        assert saved['settings']['qwen_thinking'] is True
        assert saved['settings']['context_length'] == 8192
        assert saved['settings']['max_output_tokens'] == 4096
    with TestClient(create_app(tmp_path)) as client:
        assert client.get('/api/settings').json()['max_output_tokens'] == 4096


def test_settings_reject_starved_input_before_persisting(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        before = client.get('/api/settings').json()
        response = client.put('/api/settings',json={'context_length':4096,'max_output_tokens':2048})
        assert response.status_code == 422
        assert client.get('/api/settings').json() == before


def test_run_rejects_invalid_legacy_settings_without_enqueuing(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        client.app.state.store.save_settings({'context_length':4096,'max_output_tokens':2048})
        ds = client.post('/api/datasets/smoke').json()
        response = client.post('/api/runs',json={'dataset_id':ds['id'],'configs':['qwen'],'demo':True})
        assert response.status_code == 422
        assert client.get('/api/runs?demo=true').json() == []


def test_thinking_budget_reaches_transport_and_output_exhaustion_is_not_parse_error():
    async def scenario():
        calls = []
        def handler(request):
            payload = json.loads(request.content)
            calls.append(payload)
            assert payload['options']['num_ctx'] == 8192
            assert payload['options']['num_predict'] == 4096
            assert payload['think'] is True
            return httpx.Response(200,json={'model':'qwen3.5:9b','done':True,
                'done_reason':'length','eval_count':4096,
                'message':{'content':'','thinking':'unfinished reasoning'}})
        settings = dict(ollama_url='http://localhost:11434',qwen_model='qwen3.5:9b',
            context_length=8192,max_output_tokens=4096,max_attempts=3,timeout_seconds=480)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = OllamaAdapter('qwen', settings, client)
            adapter.think = True  # Option support is separately verified by inspect tests.
            result = await adapter.predict('{"body":"' + 'x'*1400 + '"}')
            assert result['status'] == 'ERROR' and result['decision'] is None
            assert result['error']['type'] == 'OUTPUT_LIMIT'
            assert result['raw_response']['eval_count'] == 4096
            assert len(calls) == 1  # Retrying the same exhausted budget is not useful.
            assert result['input_budget']['context_length'] == 8192
    asyncio.run(scenario())


def test_common_limit_boundary_is_accepted_by_local_budget_without_truncation():
    async def scenario():
        calls = []
        def handler(request):
            calls.append(json.loads(request.content))
            return httpx.Response(200,json={'message':{'content':'{"decision":"NORMAL"}'},'done_reason':'stop'})
        settings = dict(ollama_url='http://localhost:11434',qwen_model='qwen3.5:9b',
            context_length=8192,max_output_tokens=4096,max_attempts=1,timeout_seconds=1)
        text = 'x' * common_input_limit(settings)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await OllamaAdapter('qwen',settings,client).predict(text)
        assert result['status'] == 'SUCCESS'
        assert calls[0]['messages'][1]['content'] == text
    asyncio.run(scenario())


def test_engine_records_configured_context_instead_of_fixed_4096(tmp_path):
    import time
    with TestClient(create_app(tmp_path)) as client:
        assert client.put('/api/settings',json={'context_length':8192,'max_output_tokens':4096}).status_code == 200
        ds = client.post('/api/datasets/smoke').json()
        run = client.post('/api/runs',json={'dataset_id':ds['id'],'configs':['qwen'],'demo':True}).json()
        for _ in range(200):
            saved = client.get('/api/runs/'+run['id']).json()
            if saved['status'] == 'COMPLETED':
                break
            time.sleep(.02)
        assert saved['status'] == 'COMPLETED'
        assert saved['environment']['context_length'] == 8192
        assert saved['environment']['input_budget']['output_reserved_tokens'] == 4096
        assert saved['totals']['api_calls'] == 0
