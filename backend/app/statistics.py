"""Read-only cumulative reporting. Repeated emails are separate evaluation attempts."""
import json
from collections import Counter

from .core import ALL_CONFIGS, CASCADE_CONFIGS, config_definitions, calculate_metrics


def prompt_version(run):
    version = run.get('environment', {}).get('prompt_version')
    if version:
        review=run.get('environment',{}).get('cascade_prompt_version')
        return version + (' / '+review if review and any(c in CASCADE_CONFIGS for c in run['selected_configs']) else '')
    versions = {r['prompt_version'] for r in run.get('results', []) if r.get('prompt_version')}
    return ', '.join(sorted(versions)) or '미기록'


def dataset_key(run):
    ds = run['dataset_snapshot']
    return json.dumps([ds.get('id'), ds.get('version'), ds.get('split')], ensure_ascii=False)


def aggregate_statistics(runs, dataset='', prompt='', mode=''):
    datasets = {dataset_key(r): {'value': dataset_key(r), 'label': f"{r['dataset_snapshot']['name']} · v{r['dataset_snapshot']['version']} · " + ('최종 평가' if r['dataset_snapshot'].get('split') == 'evaluation' else '개발')} for r in runs}
    selected = [r for r in runs if (not dataset or dataset_key(r) == dataset)
                and (not prompt or prompt_version(r) == prompt) and (not mode or r['mode'] == mode)]
    metrics = {}
    for config in ALL_CONFIGS:
        samples, results, costs = [], [], []
        for run in selected:
            if config not in run['selected_configs']:
                continue
            # A repeated sample in another run is another observation, never an overwrite.
            key = lambda sid: json.dumps([run['id'], str(sid)])
            samples.extend({**s, 'sample_id': key(s['sample_id'])} for s in run['dataset_snapshot']['samples'])
            results.extend({**r, 'sample_id': key(r['sample_id']),
                            'latency_ms': None if r.get('reused') and config.endswith('_jev') else r.get('latency_ms')}
                           for r in run['results'] if r['config_id'] == config
                           and not r.get('component_for') and not r.get('is_warmup'))
            costs.append(run['metrics'][config]['cost'])
        if not samples:
            continue
        metric = calculate_metrics(samples, results)
        known = [c['actual_usd'] for c in costs if c.get('actual_usd') is not None]
        metric['cost'] = {'actual_usd': sum(known) if known else None,
                          'api_calls': sum(c['api_calls'] for c in costs),
                          'unknown_calls': sum(c['unknown_calls'] for c in costs)}
        metrics[config] = metric
    class_counts = Counter(s['label'] for r in selected for s in r['dataset_snapshot']['samples'])
    costs = [r['totals']['cost_usd'] for r in selected if r['totals']['cost_usd'] is not None]
    elapsed = [r['totals']['elapsed_ms'] for r in selected if r['totals']['elapsed_ms'] is not None]
    conditions = {json.dumps({'settings': r.get('settings'), 'prompt': prompt_version(r),
                             'dataset': dataset_key(r), 'mode': r['mode']}, sort_keys=True) for r in selected}
    diagnostics={}
    for run in selected:
        for config,diag in run.get('cascade_diagnostics',{}).items():
            if config not in diagnostics:
                diagnostics[config]=json.loads(json.dumps(diag))
            else:
                total=diagnostics[config]
                for key in ('N','compared','changed','unavailable'): total[key]+=diag[key]
                for a,targets in diag['transitions'].items():
                    for b,count in targets.items(): total['transitions'][a][b]+=count
                for key,count in diag['baseline'].items(): total['baseline'][key]+=count
    return {'run_count': len(selected), 'run_ids': [r['id'] for r in selected],
            'config_definitions':config_definitions(metrics), 'cascade_diagnostics':diagnostics,
            'partial_run_count': sum(r['status'] != 'COMPLETED' for r in selected),
            'sample_count': sum(class_counts.values()), 'class_counts': dict(class_counts),
            'mixed_conditions': len(conditions) > 1, 'metrics': metrics,
            'totals': {'api_calls': sum(r['totals']['api_calls'] for r in selected),
                       'cost_usd': sum(costs) if costs else None,
                       'unknown_cost_calls': sum(r['totals']['unknown_cost_calls'] for r in selected),
                       'elapsed_ms': sum(elapsed) if elapsed else None},
            'options': {'datasets': list(datasets.values()),
                        'prompts': sorted({prompt_version(r) for r in runs})}}
