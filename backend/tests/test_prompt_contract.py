"""Verify request and history contracts, not model classification accuracy."""
import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters import JevAdapter, OllamaAdapter
from app.core import CONFIGS, ACTIVE_CONFIGS, model_input
from app.engine import Engine
from app.store import Store
from app.main import create_app


def test_local_and_jev_requests_share_each_complete_decision_criterion(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'prompt-viewer-secret-do-not-expose')
    with TestClient(create_app(tmp_path)) as api:
        response = api.get('/api/settings')
        assert response.status_code == 200
        assert 'prompt-viewer-secret-do-not-expose' not in response.text
        displayed = response.json()['classification_prompt']
        assert displayed['version'] == 'email-injection-choice-v3'
        assert displayed['cascade_question_version'] == 'email-injection-jev-review-v2'

    async def scenario():
        captured = []

        def handler(request):
            payload = json.loads(request.content)
            captured.append(payload)
            if request.url.path == '/api/chat':
                return httpx.Response(200, json={
                    'message': {'content': '{"decision":"REVIEW"}'}, 'done': True,
                })
            return httpx.Response(200, json={
                'answers': {'decision': {'type': 'choice', 'choice': 'REVIEW'}},
            })

        settings = dict(ollama_url='http://localhost:11434',
                        foundation_sec_model='foundation:test', qwen_model='qwen:test',
                        jev_model='jev:test', openrouter_api_key='test-only',
                        context_length=4096, max_output_tokens=1024, max_attempts=1)
        sample = dict(subject='회의 확인', body='자동 회신도 괜찮습니다.',
                      label='NORMAL', source_dataset='DO_NOT_SEND_SOURCE',
                      source_context={'user_prompt': 'DO_NOT_SEND_CONTEXT'},
                      sample_id='DO_NOT_SEND_ID', notes='DO_NOT_SEND_NOTES')
        text = model_input(sample)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            for component in ('foundation_sec', 'qwen'):
                await OllamaAdapter(component, settings, client).predict(text)
            await JevAdapter(settings, client).predict(text)
            await JevAdapter(settings, client).predict_with_prior(text, 'NORMAL')

        assert len(captured) == 4
        question = captured[2]['questions']['decision']
        review = captured[3]['questions']['decision']
        assert displayed['jev_review_question'] == review
        assert review['criteria'] == question['criteria']
        assert displayed['instructions'] in review['instructions']
        assert json.loads(captured[3]['state']) == {'email': json.loads(text), 'prior_assessment': {'decision': 'NORMAL'}}
        assert displayed['jev_question'] == question
        assert displayed['criteria'] == question['criteria']
        assert displayed['instructions'] in question['instructions']
        assert set(question['criteria']) == {'NORMAL', 'INJECTION', 'REVIEW'}
        for local in captured[:2]:
            messages = local['messages']
            assert len(messages) == 2
            assert displayed['local_system_prompt'] == messages[0]['content']
            assert messages[1]['content'] == captured[2]['state'] == text
            for criterion in question['criteria'].values():
                assert criterion in messages[0]['content']
            assert local['format']['properties']['decision']['enum'] == ['NORMAL', 'INJECTION', 'REVIEW']
        assert 'DO_NOT_SEND' not in json.dumps(captured)
        assert 'messages' not in captured[2]
    asyncio.run(scenario())


@pytest.mark.parametrize('historical_version', ['email-injection-choice-v1', 'email-injection-choice-v2'])
def test_new_v3_run_keeps_completed_history_and_combination_policy(tmp_path, historical_version):
    async def scenario():
        store = Store(tmp_path)
        ds = store.save_dataset(dict(name='version check', samples=[
            dict(sample_id='one', subject='업무', body='회의 안내입니다.', label='NORMAL'),
        ]))
        options = dict(dataset_id=ds['id'], configs=list(CONFIGS), demo=True, mode='reuse')
        old = store.create_run(options, {})
        old.update(status='COMPLETED', environment={
            'system_prompt': 'historical prompt', 'prompt_version': historical_version,
        })
        store.update_run(old)
        store.save_result(dict(id='old-result', run_id=old['id'], sample_id='one',
                               config_id='qwen', status='SUCCESS', decision='NORMAL',
                               prompt_version=historical_version), True)
        before = store.get_run(old['id'], True)

        new = store.create_run(options, {})
        await Engine(store).execute(new['id'], True)
        result = store.get_run(new['id'], True)
        assert result['status'] == 'COMPLETED'
        assert len(result['results']) == 5
        assert {r['prompt_version'] for r in result['results']} == {'email-injection-choice-v3'}
        assert result['environment']['prompt_version'] == 'email-injection-choice-v3'
        assert set(result['environment']['decision_criteria']) == {'NORMAL', 'INJECTION', 'REVIEW'}
        for criterion in result['environment']['decision_criteria'].values():
            assert criterion in result['environment']['system_prompt']
        combined = [r for r in result['results'] if r['config_id'].endswith('_jev')]
        assert len(combined) == 2
        assert all(r['policy_version'] == 'unanimous-or-review-v1' for r in combined)
        assert all(len(r['component_result_ids']) == 2 for r in combined)
        assert store.get_run(old['id'], True) == before
    asyncio.run(scenario())


def test_v3_cascade_persists_review_version_without_rewriting_old_run(tmp_path):
    async def scenario():
        store = Store(tmp_path)
        ds = store.save_dataset(dict(name='cascade version check', samples=[
            dict(sample_id='one', subject='업무', body='회의 안내입니다.', label='NORMAL'),
        ]))
        options = dict(dataset_id=ds['id'], configs=list(ACTIVE_CONFIGS), demo=True, mode='reuse')
        old = store.create_run(options, {})
        old.update(status='COMPLETED', environment={'prompt_version':'email-injection-choice-v2',
                   'cascade_prompt_version':'email-injection-jev-review-v1','jev_review_question':{'instructions':'historical review'}})
        store.update_run(old)
        store.save_result(dict(id='old-cascade',run_id=old['id'],sample_id='one',config_id='qwen_then_jev',
                               status='SUCCESS',decision='NORMAL',prompt_version='email-injection-jev-review-v1',
                               policy_version='local-then-jev-final-v1'),True)
        before = store.get_run(old['id'],True)
        new = store.create_run(options, {'context_length':4096,'max_output_tokens':1024})
        await Engine(store).execute(new['id'],True)
        saved = store.get_run(new['id'],True)
        assert saved['status'] == 'COMPLETED'
        assert len(saved['results']) == 7
        assert saved['environment']['prompt_version'] == 'email-injection-choice-v3'
        assert saved['environment']['cascade_prompt_version'] == 'email-injection-jev-review-v2'
        for row in saved['results']:
            assert row['status'] == 'SUCCESS'
            review = row.get('stage') == 'jev_review' or row['config_id'].endswith('_then_jev')
            assert row['prompt_version'] == ('email-injection-jev-review-v2' if review else 'email-injection-choice-v3')
            if review:
                assert row['policy_version'] == 'local-then-jev-final-v1'
            if row.get('stage') == 'jev_review':
                assert row['request_question'] == saved['environment']['jev_review_question']
                assert row['request_question']['criteria'] == saved['environment']['decision_criteria']
        assert store.get_run(old['id'],True) == before
    asyncio.run(scenario())
