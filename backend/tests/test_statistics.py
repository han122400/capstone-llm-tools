from fastapi.testclient import TestClient
from app.main import create_app
from app.statistics import aggregate_statistics, dataset_key


def seed(store, demo=False, version='v2', mode='reuse', decisions=('NORMAL', 'INJECTION'), status='COMPLETED'):
    ds = store.save_dataset({'name': '통계 검증', 'samples': [
        {'sample_id': str(i), 'label': 'NORMAL' if i == 0 else 'INJECTION', 'subject': 'test', 'body': 'test'}
        for i in range(len(decisions))]})
    run = store.create_run({'dataset_id': ds['id'], 'configs': ['jev', 'qwen_jev'], 'demo': demo, 'mode': mode}, {})
    run.update(status=status, environment={'prompt_version': version})
    store.update_run(run)
    for i, decision in enumerate(decisions):
        for config in ('jev', 'qwen_jev'):
            store.save_result({'id': f"{run['id']}-{config}-{i}", 'run_id': run['id'], 'config_id': config,
                               'sample_id': str(i), 'status': 'SUCCESS' if decision else 'ERROR', 'decision': decision,
                               'latency_ms': 10+i, 'reused': config.endswith('_jev'),
                               'cost': .1 if config == 'jev' else None,
                               'attempts': [{'cost': .1}] if config == 'jev' else []}, demo)
    # Warmup and internal rows must never replace the final decision or increase N.
    for suffix, extra in [('warm', {'is_warmup': True}), ('child', {'component_for': 'qwen_jev'})]:
        store.save_result({'id': run['id']+suffix, 'run_id': run['id'], 'config_id': 'qwen', 'sample_id': '0',
                           'status': 'SUCCESS', 'decision': 'INJECTION', **extra}, demo)
    return store.get_run(run['id'], demo)


def test_cumulative_counts_are_weighted_and_repeated_ids_are_preserved(tmp_path):
    app = create_app(tmp_path)
    first = seed(app.state.store, decisions=('NORMAL', 'INJECTION'))
    second = seed(app.state.store, decisions=('INJECTION', 'NORMAL', 'REVIEW', None))
    stats = aggregate_statistics([first, second])
    m = stats['metrics']['jev']
    assert stats['sample_count'] == 6 and stats['run_count'] == 2
    assert m['N'] == 6 and m['metrics']['correct_rate']['value'] == 2/6
    assert m['confusion']['NORMAL'] == {'NORMAL': 1, 'INJECTION': 1, 'REVIEW': 0}
    assert m['confusion']['INJECTION'] == {'NORMAL': 1, 'INJECTION': 1, 'REVIEW': 1}
    assert m['counts']['ERROR'] == 1
    assert m['latency']['success']['max_ms'] == 12
    assert stats['metrics']['qwen_jev']['latency']['success']['count'] == 0
    assert stats['totals']['api_calls'] == 6
    assert abs(stats['totals']['cost_usd']-.6) < 1e-9
    assert stats['metrics']['qwen_jev']['cost']['api_calls'] == 0
    assert 'qwen' not in stats['metrics']


def test_statistics_filters_empty_and_partial(tmp_path):
    store = create_app(tmp_path).state.store
    first = seed(store, version='v1')
    second = seed(store, version='v2', mode='live', status='CANCELLED')
    assert aggregate_statistics([first, second], prompt='v1')['run_ids'] == [first['id']]
    assert aggregate_statistics([first, second], dataset=dataset_key(second), mode='live')['partial_run_count'] == 1
    assert aggregate_statistics([first, second])['mixed_conditions']
    empty = aggregate_statistics([first], prompt='nonexistent')
    assert empty['metrics'] == {} and empty['sample_count'] == 0
    assert empty['totals']['cost_usd'] is None
    assert aggregate_statistics([])['options'] == {'datasets': [], 'prompts': []}


def test_statistics_api_separates_demo_and_real_without_inference(tmp_path):
    app = create_app(tmp_path)
    real = seed(app.state.store)
    demo = seed(app.state.store, demo=True, version='v1')
    with TestClient(app) as client:
        assert client.get('/api/statistics').json()['run_ids'] == [real['id']]
        assert client.get('/api/statistics?demo=true').json()['run_ids'] == [demo['id']]
        assert client.get('/api/statistics?prompt=v1').json()['sample_count'] == 0
        assert client.get('/api/statistics?mode=invalid').status_code == 422
        assert 'raw_response' not in client.get('/api/statistics').text
