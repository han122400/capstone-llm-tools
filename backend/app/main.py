import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from pydantic import ValidationError
from .schemas import DatasetInput, ImportInput, RunInput, SettingsInput
from .store import Store, export_csv, parse_import
from .engine import Engine
from .core import CONFIGS, component_dependencies, POLICY_VERSION, PROMPT_VERSION, PREPROCESS_VERSION, common_input_limit
from .settings import load_settings, public_settings
from .prompts import prompt_details
from .core import ACTIVE_CONFIGS, LEGACY_CONFIG_IDS
from .core import input_budget, validate_input_budget

PROJECT_ROOT=Path(__file__).resolve().parents[2]
ORIGINS=['http://127.0.0.1:3001','http://localhost:3001','http://127.0.0.1:8001','http://localhost:8001','http://127.0.0.1:3101','http://localhost:3101']


def create_app(data_root=None):
    store=Store(data_root or os.environ.get('EVALUATOR_DATA_DIR') or PROJECT_ROOT/'runtime')
    def settings():
        values = {**load_settings(), **store.settings()}
        return {**values, 'input_budget':input_budget(values), 'max_input_bytes':common_input_limit(values)}
    engine=Engine(store,settings_loader=settings)

    @asynccontextmanager
    async def lifespan(app):
        await engine.start()
        yield
        await engine.stop()

    app=FastAPI(title='이메일 프롬프트 인젝션 모델 평가',version='0.1.0',lifespan=lifespan)
    app.state.store=store
    app.state.engine=engine
    app.add_middleware(CORSMiddleware,allow_origins=ORIGINS[:2]+ORIGINS[4:],allow_methods=['GET','POST','PUT','DELETE'],allow_headers=['Content-Type'])

    @app.middleware('http')
    async def local_write_guard(request:Request,call_next):
        origin=request.headers.get('origin')
        if request.method in ('POST','PUT','DELETE') and origin and origin not in ORIGINS:
            return JSONResponse(status_code=403,content={'detail':'로컬 프론트엔드에서만 변경할 수 있습니다'})
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Cache-Control']='no-store'
        return response

    @app.exception_handler(KeyError)
    async def not_found(request,exc):
        return JSONResponse(status_code=404,content={'detail':'기록을 찾을 수 없습니다'})

    @app.exception_handler(ValueError)
    async def invalid(request,exc):
        return JSONResponse(status_code=422,content={'detail':str(exc)[:600]})

    def resolve(identifier):
        for demo in (False,True):
            try: return store.get_run(identifier,demo)
            except KeyError: pass
        raise KeyError(identifier)

    @app.get('/api/health')
    def health(): return {'status':'ok','worker':'single-local','paid_test_calls':False}

    @app.get('/api/configs')
    def configs(): return list(ACTIVE_CONFIGS.values())

    @app.get('/api/settings')
    def get_settings():
        values=settings()
        return {**public_settings(values),'policy_version':POLICY_VERSION,'prompt_version':PROMPT_VERSION,'preprocess_version':PREPROCESS_VERSION,'input_limit_bytes':common_input_limit(values),'local_concurrency':1,'supported_modes':['reuse','live'],'live_call_strategy':'sequential','classification_prompt':prompt_details()}

    @app.put('/api/settings')
    def put_settings(payload:SettingsInput):
        updates = payload.model_dump(exclude_none=True)
        validate_input_budget({**settings(), **updates})
        store.save_settings(updates)
        return get_settings()

    @app.post('/api/preflight')
    async def check_connections():
        from .adapters import preflight
        return await preflight(settings())

    @app.get('/api/datasets')
    def datasets(): return store.list_datasets()

    @app.post('/api/datasets')
    def add_dataset(payload:DatasetInput): return store.save_dataset(payload.model_dump())

    @app.post('/api/datasets/smoke')
    def seed_smoke():
        source=json.loads((PROJECT_ROOT/'data'/'smoke.json').read_text(encoding='utf-8'))
        return store.save_dataset(source)

    @app.post('/api/datasets/import')
    def import_dataset(payload:ImportInput):
        metadata=json.loads(payload.content.lstrip('\ufeff')) if payload.format=='json' else {}
        metadata=metadata if isinstance(metadata,dict) else {}
        return store.save_dataset({'name':payload.name,'split':payload.split or metadata.get('split','development'),
            'manifest':metadata.get('manifest'),'samples':parse_import(payload.format,payload.content)})

    @app.get('/api/datasets/{identifier}')
    def dataset(identifier:str): return store.get_dataset(identifier)

    @app.put('/api/datasets/{identifier}')
    def edit_dataset(identifier:str,payload:DatasetInput): return store.save_dataset(payload.model_dump(),identifier)

    @app.delete('/api/datasets/{identifier}')
    def remove_dataset(identifier:str):
        store.delete_dataset(identifier)
        return {'deleted':identifier,'snapshots_preserved':True}

    @app.get('/api/datasets/{identifier}/export')
    def export_dataset(identifier:str,format:str=Query(default='json',pattern='^(json|csv)$')):
        data=store.get_dataset(identifier)
        if format=='json':
            content=json.dumps(data,ensure_ascii=False,indent=2)
            return Response(content,media_type='application/json',headers={'Content-Disposition':f'attachment; filename="dataset-{identifier}.json"'})
        return Response('\ufeff'+export_csv(data['samples']),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="dataset-{identifier}.csv"'})

    @app.get('/api/runs')
    def runs(demo:bool=False): return store.list_runs(demo)

    @app.get('/api/statistics')
    def statistics(demo:bool=False,dataset:str='',prompt:str='',mode:str=Query(default='',pattern='^(reuse|live)?$')):
        from .statistics import aggregate_statistics
        records=[store.get_run(r['id'],demo) for r in store.list_runs(demo)]
        return aggregate_statistics(records,dataset,prompt,mode)

    @app.post('/api/runs')
    async def start_run(payload:RunInput):
        values = settings()
        validate_input_budget(values)
        if not payload.demo and 'jev' in component_dependencies(payload.configs) and not payload.external_transfer_confirmed:
            raise HTTPException(422,'합성 이메일의 OpenRouter 전송 및 유료 호출 가능성을 확인해야 합니다')
        run=store.create_run(payload.model_dump(),values)
        await engine.enqueue(run['id'],run['demo'])
        return store.get_run(run['id'],run['demo'])

    @app.get('/api/runs/{identifier}')
    def get_run(identifier:str): return resolve(identifier)

    @app.post('/api/runs/{identifier}/cancel')
    def cancel_run(identifier:str):
        run=resolve(identifier)
        return store.cancel(identifier,run['demo'])

    @app.post('/api/runs/{identifier}/retry')
    async def retry_run(identifier:str):
        original=resolve(identifier)
        if any(c in LEGACY_CONFIG_IDS for c in original['selected_configs']):
            raise HTTPException(422,'기존 독립 결합은 이력 조회 전용입니다. 새 평가에서 로컬 → Jev 구성을 선택하세요.')
        if original['status'] in ('PENDING','RUNNING'):
            raise HTTPException(422,'진행 중인 실험은 재실행할 수 없습니다')
        failed=set()
        for sample in original['dataset_snapshot']['samples']:
            for config in original['selected_configs']:
                rows=[r for r in original['results'] if r['config_id']==config and r['sample_id']==sample['sample_id'] and not r.get('component_for') and not r.get('is_warmup')]
                if not rows or rows[-1]['status']!='SUCCESS': failed.add(sample['sample_id'])
        if not failed: raise HTTPException(422,'실패 또는 미완료 항목이 없습니다')
        retry_settings = {**settings(), **original['settings']}
        retry_settings['input_budget'] = validate_input_budget(retry_settings)
        retry_settings['max_input_bytes'] = common_input_limit(retry_settings)
        # Retry only failed/uncompleted samples; no previous inference result is borrowed.
        snapshot=original['dataset_snapshot']
        retry_ds=store.save_dataset({'name':snapshot['name']+' · 새 시도','split':snapshot['split'],'samples':[s for s in snapshot['samples'] if s['sample_id'] in failed]})
        options={**original['options'],'dataset_id':retry_ds['id'],'parent_run_id':identifier}
        run=store.create_run(options,retry_settings)
        await engine.enqueue(run['id'],run['demo'])
        return store.get_run(run['id'],run['demo'])

    @app.delete('/api/runs/{identifier}')
    def remove_run(identifier:str):
        run=resolve(identifier)
        store.delete_run(identifier,run['demo'])
        return {'deleted':identifier,'raw_responses_deleted':True}

    @app.get('/api/runs/{identifier}/export')
    def export_run(identifier:str,format:str=Query(default='json',pattern='^(json|csv)$')):
        run=resolve(identifier)
        if format=='json':
            return Response(json.dumps(run,ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="run-{identifier}.json"'})
        samples={s['sample_id']:s for s in run['dataset_snapshot']['samples']}
        rows=[{**r,'truth_label':samples.get(r['sample_id'],{}).get('label'),'sample_metadata':samples.get(r['sample_id'],{}),
            **{k:v for k,v in samples.get(r['sample_id'],{}).items() if k.startswith('source_') or k in ('pair_id','template_family','transformation_notes','transformation_version','synthetic')},
            'dataset_manifest':run['dataset_snapshot'].get('manifest'),'dataset_name':run['dataset_snapshot']['name'],'run_status':run['status'],'evaluation_mode':run['mode'],'settings':run['settings'],'environment':run['environment']} for r in run['results']]
        return Response('\ufeff'+export_csv(rows),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="run-{identifier}.csv"'})

    return app


app=create_app()
