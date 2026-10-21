"""Qwen thinking controls: mocked transport only, no real inference."""
import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters import OllamaAdapter
from app.main import create_app
from app.settings import load_settings


def configuration(**overrides):
    return dict(ollama_url='http://localhost:11434', qwen_model='qwen3.5:9b',
                foundation_sec_model='foundation-sec:test', context_length=4096,
                max_output_tokens=64, max_attempts=1, timeout_seconds=1,
                **overrides)


@pytest.mark.parametrize('enabled', [True, False])
def test_qwen_toggle_reaches_request_and_applied_metadata(enabled):
    requests = []

    def handler(request):
        if request.url.path == '/api/tags':
            return httpx.Response(200, json={'models': [{'name':'qwen3.5:9b','digest':'test'}]})
        if request.url.path == '/api/show':
            return httpx.Response(200, json={
                'details': {'quantization_level':'Q4_K_M','parameter_size':'9.0B'},
                'model_info': {'qwen35.context_length':32768,'general.name':'Qwen3.5-9B'},
                'thinking': {'values':[False,True], 'default':True},
            })
        assert request.url.path == '/api/chat'
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={'model':'qwen3.5:9b','done':True,
            'message':{'content':'{"decision":"NORMAL"}'}})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = OllamaAdapter('qwen', configuration(qwen_thinking=enabled), client)
            inspected = await adapter.inspect()
            assert inspected['ready'] is True
            result = await adapter.predict('{"body":"Meeting update"}')
            assert result['status'] == 'SUCCESS'
            assert inspected['metadata']['thinking_requested'] is enabled
            assert inspected['metadata']['thinking_applied'] is enabled
            assert result['request_options']['think_sent'] is True
            assert result['request_options']['think'] is enabled

    asyncio.run(scenario())
    assert len(requests) == 1 and requests[0]['think'] is enabled


def test_qwen_on_requires_verified_option_support():
    paths = []

    def handler(request):
        paths.append(request.url.path)
        if request.url.path == '/api/tags':
            return httpx.Response(200, json={'models':[{'name':'qwen3.5:9b'}]})
        assert request.url.path == '/api/show'
        return httpx.Response(200, json={
            'details':{'quantization_level':'Q4_K_M','parameter_size':'9.0B'},
            'model_info':{'qwen35.context_length':32768},
            'thinking':{'values':[False]},
        })

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await OllamaAdapter('qwen', configuration(qwen_thinking=True), client).inspect()
            assert result['ready'] is False
            assert result['error']['type'] == 'UNSUPPORTED_THINKING_OPTION'

    asyncio.run(scenario())
    assert paths == ['/api/tags','/api/show']


def test_qwen_toggle_does_not_change_foundation_option():
    def handler(request):
        if request.url.path == '/api/tags':
            return httpx.Response(200, json={'models':[{'name':'foundation-sec:test'}]})
        assert request.url.path == '/api/show'
        return httpx.Response(200, json={
            'details':{'quantization_level':'Q4_K_M','parameter_size':'8.03B'},
            'model_info':{'llama.context_length':32768},
        })

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await OllamaAdapter('foundation_sec', configuration(qwen_thinking=True), client).inspect()
            assert result['ready'] is True
            assert result['metadata']['thinking_requested'] is None
            assert result['metadata']['thinking_option_sent'] is False

    asyncio.run(scenario())


def test_default_off_settings_persistence_and_immutable_run_snapshot(tmp_path):
    assert load_settings()['qwen_thinking'] is False
    with TestClient(create_app(tmp_path)) as client:
        assert client.get('/api/settings').json()['qwen_thinking'] is False
        enabled = client.put('/api/settings',json={'qwen_thinking':True})
        assert enabled.status_code == 200 and enabled.json()['qwen_thinking'] is True
        dataset = client.post('/api/datasets/smoke').json()
        # Save a snapshot without enqueuing or requesting any inference.
        saved = client.app.state.store.create_run(dict(dataset_id=dataset['id'],
            configs=['qwen','qwen_then_jev'],demo=True,mode='reuse'), enabled.json())
        assert client.put('/api/settings',json={'qwen_thinking':False}).status_code == 200
        assert client.get('/api/settings').json()['qwen_thinking'] is False
        assert client.get('/api/runs/'+saved['id']).json()['settings']['qwen_thinking'] is True
        assert client.put('/api/settings',json={'qwen_thinking':'true'}).status_code == 422
    with TestClient(create_app(tmp_path)) as client:
        assert client.get('/api/settings').json()['qwen_thinking'] is False
