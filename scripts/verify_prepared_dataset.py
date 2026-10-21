"""Offline, temporary-DB validation of prepared data with DEMO adapters only."""
import argparse
import asyncio
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.schemas import DatasetInput
from app.core import CONFIGS, model_input, input_hash
from app.store import Store, parse_import, export_csv
from app.engine import Engine
from app.adapters import MockAdapter


async def verify(bundle):
    datasets={split:DatasetInput.model_validate(json.loads((bundle/f'{split}.json').read_text(encoding='utf-8'))).model_dump() for split in ('evaluation','development')}
    raw=json.loads((ROOT/'data/raw/prompt_injections_so_back/defense_evaluation/paired_emails_dataset.json').read_text(encoding='utf-8'))
    counts={}
    for split,data in datasets.items():
        counts[split]=dict(Counter(s['label'] for s in data['samples']))
        expected={c['sample_id']:c for c in data['manifest']['input_checks']}
        pairs={}
        for sample in data['samples']:
            original=raw[sample['source_record_index']]
            branch='benign' if sample['label']=='NORMAL' else 'attack'
            assert original['pair'][branch]['external_content']==sample['body']
            assert input_hash(model_input(sample))==expected[sample['sample_id']]['input_hash']
            assert set(json.loads(model_input(sample)))=={'body'}
            assert sample['email']['content']['id'] is None
            assert sample['email']['content']['truncated'] is None
            pairs.setdefault(sample['pair_id'],set()).add(sample['label'])
        assert all(labels=={'NORMAL','INJECTION'} for labels in pairs.values())
        assert parse_import('csv',export_csv(data['samples']))==data['samples']
    for field in ('pair_id','template_family'):
        assert {s[field] for s in datasets['evaluation']['samples']}.isdisjoint(s[field] for s in datasets['development']['samples'])
    assert {s['source_context']['scenario'] for s in datasets['evaluation']['samples']}.isdisjoint(s['source_context']['scenario'] for s in datasets['development']['samples'])
    calls=[]
    class CountingMock(MockAdapter):
        async def predict(self,text):
            calls.append((self.component,input_hash(text)))
            return await super().predict(text)
    with tempfile.TemporaryDirectory(prefix='email-public-mock-') as temporary:
        store=Store(temporary)
        ds=store.save_dataset(datasets['evaluation'])
        run=store.create_run({'dataset_id':ds['id'],'configs':list(CONFIGS),'mode':'reuse','demo':True}, {})
        engine=Engine(store,factory=lambda component,settings,**kwargs:CountingMock(component,settings))
        await engine.execute(run['id'],True)
        saved=store.get_run(run['id'],True)
        n=len(ds['samples'])
        assert len(saved['results'])==5*n
        assert all(r['status']=='SUCCESS' for r in saved['results'])
        assert len(calls)==3*n and len(set(calls))==3*n
        assert saved['totals']['api_calls']==0
        assert store.list_runs(False)==[]
        changed={**datasets['evaluation'],'name':'changed after snapshot'}
        store.save_dataset(changed,ds['id'])
        assert store.get_run(run['id'],True)['dataset_snapshot']==saved['dataset_snapshot']
        return dict(verification='PASS',data_counts=counts,source_version=ds['manifest']['source_version'],
            source_file_sha256=ds['manifest']['source_file_sha256'],selected_configs=list(CONFIGS),
            mock_component_calls=len(calls),mock_results=len(saved['results']),physical_api_calls=0,
            real_models_called=False,user_catalog_runs_created=0,
            checks=['original body equality','pair/family/scenario split isolation','input hash','content allowlist',
                'CSV roundtrip','five configurations','Jev once per sample','immutable snapshot','DEMO isolation'],
            limits='Does not validate actual inference, GPU, Gmail OAuth, MIME parsing, semantic gold-label correctness or upstream license permission.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--report',type=Path,default=ROOT/'docs/PUBLIC_DATA_GMAIL_VERIFICATION.json')
    args=parser.parse_args()
    report=asyncio.run(verify(args.bundle))
    args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
