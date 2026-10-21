"""One local worker; independent messages; immutable request/result provenance."""
import asyncio
import contextlib
import platform
import sys
from time import perf_counter
from .core import CONFIGS, PROMPT_VERSION, POLICY_VERSION, PREPROCESS_VERSION, SYSTEM_PROMPT, component_dependencies, model_input, input_hash, combine_results, common_input_limit
from .store import now, uid
from .email_input import input_quality, EMAIL_PREPROCESS_VERSION
from .prompts import CRITERIA, CASCADE_PROMPT_VERSION, CASCADE_POLICY_VERSION, jev_review_question
from .core import CASCADE_CONFIGS, LEGACY_CONFIG_IDS, input_budget
from .cascade import review_input, cascade_result


class Engine:
    def __init__(self, store, factory=None, settings_loader=None):
        self.store=store
        self.factory=factory
        self.settings_loader=settings_loader or (lambda: {})
        self.queue=asyncio.Queue()
        self.worker=None
        self.active=None
        self.execution_lock=asyncio.Lock()

    async def start(self):
        self.store.recover()
        self.worker=asyncio.create_task(self._work())

    async def stop(self):
        if self.active:
            self.store.cancel(*self.active)
        if self.worker:
            self.worker.cancel()
            with contextlib.suppress(asyncio.CancelledError): await self.worker

    async def enqueue(self, identifier, demo):
        await self.queue.put((identifier,demo))

    async def _work(self):
        while True:
            identifier,demo=await self.queue.get()
            self.active=(identifier,demo)
            try:
                await self.execute(identifier,demo)
            except asyncio.CancelledError:
                raise
            except Exception:
                # Never place raw network errors (possibly headers) into logs or UI.
                run=self.store.get_run(identifier,demo)
                run.update(status='INTERRUPTED',finished_at=now(),error={'type':'worker_failure','message':'작업자 오류. 저장된 부분 결과를 보존했습니다.'})
                self.store.update_run(run)
            finally:
                self.active=None
                self.queue.task_done()

    def cancelled(self, identifier, demo):
        return self.store.run_metadata(identifier,demo)['cancel_requested']

    async def execute(self, identifier, demo=False):
        async with self.execution_lock:
            from .telemetry import ResourceMonitor
            experiment_monitor=ResourceMonitor()
            experiment_monitor.start()
            try:
                await self._execute(identifier,demo)
            finally:
                resources=experiment_monitor.stop()
                run=self.store.run_metadata(identifier,demo)
                run['experiment_resources']={**resources,'scope':'실험 전체: 로딩·워밍업·모든 모델 요청·해제 포함. 구성별 요청 피크와 별도이며 합산하지 않음.'}
                self.store.update_run(run)

    async def _execute(self, identifier, demo):
        from .adapters import make_adapter
        from .telemetry import ResourceMonitor
        factory=self.factory or make_adapter
        run=self.store.get_run(identifier,demo)
        if run['status'] not in ('PENDING','RUNNING'): return
        settings={**self.settings_loader(), **run['settings']}
        settings['explanations']=run['options'].get('explanations',False)
        run.update(status='RUNNING',started_at=now(),environment={'python':sys.version.split()[0],'platform':platform.platform(),'local_concurrency':1,'context_length':settings.get('context_length',4096),'input_budget':input_budget(settings),'live_call_strategy':'sequential','external_server_warm_state':None,'hardware_claim':'사용자 제공 사양; 실측 가능한 자원은 요청별 기록 참조','system_prompt':SYSTEM_PROMPT,'prompt_version':PROMPT_VERSION,'decision_criteria':dict(CRITERIA)})
        run['environment'].update(cascade_prompt_version=CASCADE_PROMPT_VERSION,cascade_policy_version=CASCADE_POLICY_VERSION,jev_review_question=jev_review_question())
        self.store.update_run(run)
        samples=run['dataset_snapshot']['samples']
        selected=run['selected_configs']
        components=component_dependencies(selected)
        rows={}
        ordinary=components if run['mode']=='reuse' else [c for c in selected if c in ('foundation_sec','qwen','jev')]
        if run['mode']=='reuse' and 'jev' not in selected and not any(c in LEGACY_CONFIG_IDS for c in selected):
            ordinary=[c for c in ordinary if c!='jev']
        for config in ordinary + [c for c in selected if c in LEGACY_CONFIG_IDS or c in CASCADE_CONFIGS]:
            for sample in samples:
                row=self._row(run,config,sample)
                rows[(config,sample['sample_id'])]=row
                self.store.save_result(row,demo)
        run['progress']={'completed':0,'total':len(rows),'current':None}
        self.store.update_run(run)
        component_results={}
        unload_failed=False

        def progress(current=None):
            latest=self.store.run_metadata(identifier,demo)
            run['cancel_requested']=latest['cancel_requested']
            run['progress']={'completed':sum(r['status'] not in ('PENDING','RUNNING') for r in rows.values()),'total':len(rows),'current':current}
            self.store.update_run(run)

        def fail_rows(config, error, status='ERROR'):
            for sample in samples:
                row=rows[(config,sample['sample_id'])]
                row.update(status=status,decision=None,error=error,finished_at=now())
                self.store.save_result(row,demo)
                component_results[(config,sample['sample_id'])]=row

        async def prepare(config):
            nonlocal unload_failed
            adapter=factory(config,settings,mock=demo)
            if config!='jev' and unload_failed:
                return adapter, {'status':'ERROR','error':{'type':'unload_unverified','message':'이전 로컬 모델 해제를 확인하지 못해 다음 모델을 로드하지 않습니다.'}}
            try:
                meta=await adapter.prepare()
            except asyncio.CancelledError: raise
            except Exception:
                meta={'status':'ERROR','error':{'type':'prepare_failed','message':'모델 사전 준비 실패'}}
            run['events'].append({'component':config,'event':'prepare','at':now(),'details':meta})
            self.store.update_run(run)
            return adapter,meta

        async def release(config,adapter):
            nonlocal unload_failed
            try: meta=await adapter.release()
            except Exception: meta={'status':'ERROR','error':{'type':'release_failed','message':'모델 해제 확인 실패'}}
            if config!='jev' and (meta.get('status')=='ERROR' or meta.get('unloaded') is False): unload_failed=True
            run['events'].append({'component':config,'event':'release','at':now(),'details':meta})
            self.store.update_run(run)

        for config in ordinary:
            if self.cancelled(identifier,demo): break
            adapter,meta=await prepare(config)
            if meta.get('status')=='ERROR' or meta.get('ready') is False:
                fail_rows(config,meta.get('error') or {'type':'not_ready','message':'모델 연결 또는 설치 필요'})
                if meta.get('error',{}).get('type') in ('MODEL_LOAD_FAILED','MODEL_LOAD_UNVERIFIED'):
                    await release(config,adapter)
                progress()
                continue
            try:
                if config!='jev' and run['options'].get('warmup'):
                    warm=self._row(run,config,{'sample_id':'__warmup__','subject':'준비 확인','body':'내일 회의 일정입니다.'})
                    warm['is_warmup']=True
                    await self._request(adapter,warm,model_input({'subject':'준비 확인','body':'내일 회의 일정입니다.'}),demo,meta,ResourceMonitor)
                for index,sample in enumerate(samples):
                    if self.cancelled(identifier,demo): break
                    progress({'config_id':config,'sample_id':sample['sample_id']})
                    row=rows[(config,sample['sample_id'])]
                    row['cold_warm']='external_unknown' if config=='jev' else ('warm' if index or run['options'].get('warmup') else 'first_after_load')
                    await self._request(adapter,row,model_input(sample),demo,meta,ResourceMonitor)
                    component_results[(config,sample['sample_id'])]=row
                    progress()
            finally:
                await release(config,adapter)

        # New cascades: the second Jev request receives the original email + local choice.
        # A baseline Jev response is never borrowed, even if two local choices agree.
        for config in selected:
            if config not in CASCADE_CONFIGS or self.cancelled(identifier,demo): continue
            local=CASCADE_CONFIGS[config]['components'][0]
            local_adapter=local_meta=None
            if run['mode']=='live':
                local_adapter,local_meta=await prepare(local)
            jev,jev_meta=await prepare('jev')
            try:
                if local_adapter and run['options'].get('warmup') and local_meta.get('status')!='ERROR' and local_meta.get('ready') is not False:
                    warm=self._row(run,local,{'sample_id':'__warmup__','subject':'준비 확인','body':'내일 회의 일정입니다.'})
                    warm.update(is_warmup=True,component_for=config)
                    await self._request(local_adapter,warm,warm['input_text'],demo,local_meta,ResourceMonitor)
                for index,sample in enumerate(samples):
                    if self.cancelled(identifier,demo): break
                    progress({'config_id':config,'sample_id':sample['sample_id']})
                    row=rows[(config,sample['sample_id'])]
                    row.update(status='RUNNING',started_at=now())
                    self.store.save_result(row,demo)
                    start=perf_counter()
                    if run['mode']=='reuse':
                        first=component_results.get((local,sample['sample_id']))
                        if first is None: continue
                    else:
                        first=self._row(run,local,sample)
                        first.update(component_for=config,cold_warm='warm' if index or run['options'].get('warmup') else 'first_after_load')
                        if local_meta.get('status')=='ERROR' or local_meta.get('ready') is False:
                            first.update(status='ERROR',error=local_meta.get('error') or {'type':'not_ready','message':'로컬 모델 준비 실패'},finished_at=now())
                            self.store.save_result(first,demo)
                        else:
                            await self._request(local_adapter,first,model_input(sample),demo,local_meta,ResourceMonitor)
                    second=self._row(run,'jev',sample)
                    second.update(component_for=config,stage='jev_review',cold_warm='external_unknown',
                                  prompt_version=CASCADE_PROMPT_VERSION,question_version=CASCADE_PROMPT_VERSION,
                                  email_input_hash=second['input_hash'],prior_result_id=first['id'],
                                  policy_version=CASCADE_POLICY_VERSION,request_question=jev_review_question())
                    if first['status']!='SUCCESS':
                        second.update(status='SKIPPED',error={'type':'upstream_failure','message':'로컬 1차 판정이 없어 Jev를 호출하지 않았습니다.'},finished_at=now())
                        self.store.save_result(second,demo)
                    elif self.cancelled(identifier,demo):
                        second.update(status='CANCELLED',finished_at=now());self.store.save_result(second,demo)
                    else:
                        state=review_input(model_input(sample),first['decision'])
                        second.update(input_text=state,input_hash=input_hash(state),request_state_bytes=len(state.encode('utf-8')),
                                      remote_context_limit=None)
                        if jev_meta.get('status')=='ERROR' or jev_meta.get('ready') is False:
                            second.update(status='ERROR',error=jev_meta.get('error') or {'type':'not_ready','message':'Jev 연결 필요'},finished_at=now())
                            self.store.save_result(second,demo)
                        else:
                            await self._request(jev,second,model_input(sample),demo,{**jev_meta,'question':jev_review_question(),'prompt_version':CASCADE_PROMPT_VERSION},ResourceMonitor,prior_decision=first['decision'])
                    outcome=cascade_result(first,second)
                    row.update(outcome,component_result_ids=[first['id'],second['id']],
                               local_result_reused=run['mode']=='reuse',reused=run['mode']=='reuse',
                               local_latency_ms=first.get('latency_ms'),jev_latency_ms=second.get('latency_ms'),
                               latency_ms=(perf_counter()-start)*1000 if run['mode']=='live' else None,
                               call_strategy='local_then_jev',finished_at=now(),
                               latency_note='로컬 결과 재사용: 전체 실측 시간 N/A; Jev 2차는 신규 요청' if run['mode']=='reuse' else '로컬 시작부터 Jev 최종 판정까지 직접 측정',
                               probabilities=second.get('probabilities'),confidence=second.get('confidence'),
                               raw_response=second.get('raw_response'),actual_model=second.get('actual_model'),provider=second.get('provider'))
                    self.store.save_result(row,demo)
                    progress()
            finally:
                if local_adapter: await release(local,local_adapter)
                await release('jev',jev)

        if run['mode']=='reuse':
            for config in selected:
                if config not in LEGACY_CONFIG_IDS: continue
                for sample in samples:
                    if self.cancelled(identifier,demo): break
                    row=rows[(config,sample['sample_id'])]
                    left=component_results.get((config.removesuffix('_jev'),sample['sample_id']))
                    right=component_results.get(('jev',sample['sample_id']))
                    if left is None or right is None: continue
                    start=perf_counter()
                    outcome=combine_results(left,right)
                    row.update(outcome,component_result_ids=[left['id'],right['id']],reused=True,policy_version=POLICY_VERSION,combination_ms=(perf_counter()-start)*1000,latency_ms=None,cost=None,finished_at=now(),latency_note='결과 재사용 평가: 전체 결합 시스템 실측 처리 시간 N/A')
                    self.store.save_result(row,demo)
                    progress()
        else:
            # Both ensemble systems use the same directly timed sequential strategy.
            for config in selected:
                if config not in LEGACY_CONFIG_IDS or self.cancelled(identifier,demo): continue
                local=config.removesuffix('_jev')
                adapter,meta=await prepare(local)
                jev,jev_meta=await prepare('jev')
                try:
                    if run['options'].get('warmup') and meta.get('status')!='ERROR' and meta.get('ready') is not False:
                        warm=self._row(run,local,{'sample_id':'__warmup__','subject':'준비 확인','body':'내일 회의 일정입니다.'})
                        warm.update(is_warmup=True,component_for=config)
                        await self._request(adapter,warm,warm['input_text'],demo,meta,ResourceMonitor)
                    for index,sample in enumerate(samples):
                        if self.cancelled(identifier,demo): break
                        progress({'config_id':config,'sample_id':sample['sample_id']})
                        row=rows[(config,sample['sample_id'])]
                        start=perf_counter()
                        ids=[]
                        components_for_sample=[]
                        for component,model,model_meta in ((local,adapter,meta),('jev',jev,jev_meta)):
                            sub=self._row(run,component,sample)
                            sub['component_for']=config
                            sub['cold_warm']='external_unknown' if component=='jev' else ('warm' if index or run['options'].get('warmup') else 'first_after_load')
                            if model_meta.get('status')=='ERROR' or model_meta.get('ready') is False:
                                sub.update(status='ERROR',error=model_meta.get('error') or {'type':'not_ready','message':'연결 필요'})
                                self.store.save_result(sub,demo)
                            elif self.cancelled(identifier,demo):
                                sub.update(status='CANCELLED',decision=None)
                                self.store.save_result(sub,demo)
                            else:
                                await self._request(model,sub,model_input(sample),demo,model_meta,ResourceMonitor)
                            ids.append(sub['id'])
                            components_for_sample.append(sub)
                        outcome=combine_results(*components_for_sample)
                        row.update(outcome,component_result_ids=ids,reused=False,policy_version=POLICY_VERSION,latency_ms=(perf_counter()-start)*1000,call_strategy='sequential',finished_at=now(),latency_note='두 독립 요청 시작부터 결합까지 직접 측정. 모델 초기 로딩은 이벤트에 별도 기록.')
                        self.store.save_result(row,demo)
                        progress()
                finally:
                    await release(local,adapter)
                    await release('jev',jev)

        cancelled=self.cancelled(identifier,demo)
        for row in rows.values():
            if row['status'] in ('PENDING','RUNNING'):
                row.update(status='CANCELLED' if cancelled else 'SKIPPED',decision=None,finished_at=now())
                self.store.save_result(row,demo)
        run.update(status='CANCELLED' if cancelled else 'COMPLETED',finished_at=now(),cancel_requested=cancelled)
        progress()

    def _row(self,run,config,sample):
        text=model_input(sample)
        return dict(id=uid(),run_id=run['id'],config_id=config,sample_id=sample['sample_id'],dataset_version=run['dataset_snapshot']['version'],status='PENDING',decision=None,input_text=text,input_hash=input_hash(text),preprocess_version=EMAIL_PREPROCESS_VERSION if sample.get('email') else PREPROCESS_VERSION,input_quality=input_quality(sample),prompt_version=CASCADE_PROMPT_VERSION if config in CASCADE_CONFIGS else PROMPT_VERSION,policy_version=CASCADE_POLICY_VERSION if config in CASCADE_CONFIGS else POLICY_VERSION if config in LEGACY_CONFIG_IDS else None,requested_model=run['settings'].get({'foundation_sec':'foundation_sec_model','qwen':'qwen_model','jev':'jev_model'}.get(config,'')),actual_model=None,provider=None,probabilities=None,confidence=None,raw_response=None,latency_ms=None,cost=None,usage=None,error=None,attempts=[],component_result_ids=[],reused=False,demo=run['demo'],created_at=now(),started_at=None,finished_at=None,resources=None,explanation_generated=False,explanation_latency_ms=None,unavailable_reasons={'gpu_memory':'신뢰할 수 있는 GPU 수집기를 구성하지 않았습니다.','external_model_resources':'외부 서버 자원은 제공되지 않습니다.'})

    async def _request(self,adapter,row,text,demo,meta,monitor_class,prior_decision=None):
        row.update(status='RUNNING',started_at=now(),model_metadata=meta)
        self.store.save_result(row,demo)
        limit=common_input_limit(self.store.run_metadata(row['run_id'],demo)['settings'])
        row['input_limit']={'method':'conservative UTF-8 byte budget with shared system/output/template reserve; not exact tokenization','limit':limit,'actual':len(text.encode('utf-8')),'truncated':False}
        if prior_decision is not None:
            row['input_limit'].update(scope='original email; review envelope recorded separately',request_state_bytes=row.get('request_state_bytes'),remote_limit_verified=False)
        if len(text.encode('utf-8'))>limit:
            row.update(status='ERROR',decision=None,error={'type':'input_limit','message':f'공통 보수적 UTF-8 입력 한도 {limit}바이트 초과. 자동 절단하지 않았습니다.'},finished_at=now())
            self.store.save_result(row,demo)
            return
        if row['input_quality']['errors']:
            row.update(status='ERROR',decision=None,error={'type':'incomplete_input','message':'수집 불완전 또는 분석 본문 누락. 입력 범위 정보를 확인하세요.'},finished_at=now())
            self.store.save_result(row,demo)
            return
        monitor=monitor_class()
        monitor.start()
        start=perf_counter()
        task=asyncio.create_task(adapter.predict_with_prior(text,prior_decision) if prior_decision is not None else adapter.predict(text))
        try:
            while not task.done():
                if self.cancelled(row['run_id'],demo):
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        partial=await task
                        if isinstance(partial,dict): row.update(partial)
                    row.update(status='CANCELLED',decision=None,latency_ms=(perf_counter()-start)*1000,error={'type':'cancelled','message':'사용자 취소. 외부 요청이 이미 전달된 경우 비용이 발생했을 수 있으나 확인하지 못했습니다.'})
                    break
                await asyncio.wait({task},timeout=0.1)
            else:
                row.update(task.result())
        except asyncio.CancelledError:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                partial=await task
                if isinstance(partial,dict): row.update(partial)
            row.update(status='CANCELLED',decision=None,error={'type':'server_stopped','message':'서버 종료로 요청 중단'},latency_ms=(perf_counter()-start)*1000)
            raise
        except Exception:
            row.update(status='ERROR',decision=None,error={'type':'adapter_error','message':'어댑터 처리 실패'},latency_ms=(perf_counter()-start)*1000)
        finally:
            row.update(resources=monitor.stop(),finished_at=now())
            self.store.save_result(row,demo)
