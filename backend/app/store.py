"""SQLite records; experiments always own an immutable dataset/settings snapshot."""
import csv
import io
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager
from .schemas import DatasetInput, Sample


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return uuid.uuid4().hex


def dump(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def export_csv(rows):
    if not rows:
        return ''
    encoding_column = '__csv_text_encoding'
    columns = list(dict.fromkeys(key for row in rows for key in row if key != encoding_column)) + [encoding_column]
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        clean = {}
        for key, value in row.items():
            if isinstance(value, (dict, list)):
                value = dump(value)
            if value is None:
                value = ''
            if isinstance(value, str) and (value.startswith("'") or value.lstrip(' \t\r\n').startswith(('=', '+', '-', '@'))):
                value = "'" + value
            clean[key] = value
        clean[encoding_column] = 'spreadsheet-safe-v1'
        writer.writerow(clean)
    return output.getvalue()


def parse_import(fmt, content):
    if fmt == 'json':
        data = json.loads(content.lstrip('\ufeff'))
        if isinstance(data, dict):
            data = data.get('samples')
        if not isinstance(data, list):
            raise ValueError('JSON은 샘플 배열 또는 samples 객체여야 합니다')
    elif fmt == 'csv':
        data = list(csv.DictReader(io.StringIO(content.lstrip('\ufeff'))))
        for row in data:
            encoded = row.pop('__csv_text_encoding', None) == 'spreadsheet-safe-v1'
            for key, value in row.items():
                # Decode only explicitly marked exports; preserve literal apostrophes.
                if encoded and isinstance(value, str) and value.startswith("'") and (value.startswith("''") or value[1:].lstrip(' \t\r\n').startswith(('=', '+', '-', '@'))):
                    row[key] = value[1:]
            if 'synthetic' in row:
                if row['synthetic'] == '': row['synthetic'] = None
                elif row['synthetic'].lower() not in ('true','false','1','0'):
                    raise ValueError('synthetic은 true/false여야 합니다')
                else: row['synthetic'] = row['synthetic'].lower() in ('true','1')
            for key, value in list(row.items()):
                if key in ('email', 'source_context'):
                    row[key] = json.loads(value) if value else None
                elif key in ('source_record_index', 'source_line'):
                    row[key] = int(value) if value else None
                elif value == '' and key not in ('subject','body','notes','template_family','language','category'):
                    row[key] = None
    else:
        raise ValueError('지원하지 않는 가져오기 형식')
    return [Sample.model_validate(row).model_dump() for row in data]


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        with self.connection('catalog') as db:
            db.execute('CREATE TABLE IF NOT EXISTS datasets (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)')
        for mode in ('real','demo'):
            with self.connection(mode) as db:
                db.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
                db.execute('CREATE TABLE IF NOT EXISTS results (id TEXT PRIMARY KEY, run_id TEXT NOT NULL, payload TEXT NOT NULL)')
                db.execute('CREATE INDEX IF NOT EXISTS result_run ON results(run_id)')

    @contextmanager
    def connection(self, mode):
        db = sqlite3.connect(self.root / f'{mode}.sqlite3', timeout=30)
        try:
            db.execute('PRAGMA journal_mode=WAL')
            with db:
                yield db
        finally:
            db.close()

    def settings(self):
        with self.connection('catalog') as db:
            row = db.execute('SELECT payload FROM settings WHERE id=1').fetchone()
        return json.loads(row[0]) if row else {}

    def save_settings(self, values):
        safe = {k:v for k,v in values.items() if 'key' not in k.lower() and 'secret' not in k.lower()}
        merged = {**self.settings(), **safe}
        with self.connection('catalog') as db:
            db.execute('INSERT OR REPLACE INTO settings VALUES (1,?)', (dump(merged),))
        return merged

    def list_datasets(self):
        with self.connection('catalog') as db:
            return [json.loads(row[0]) for row in db.execute('SELECT payload FROM datasets ORDER BY rowid DESC')]

    def get_dataset(self, identifier):
        with self.connection('catalog') as db:
            row = db.execute('SELECT payload FROM datasets WHERE id=?', (identifier,)).fetchone()
        if not row: raise KeyError(identifier)
        return json.loads(row[0])

    def save_dataset(self, payload, identifier=None):
        data = DatasetInput.model_validate(payload).model_dump()
        old = self.get_dataset(identifier) if identifier else None
        data.update(id=identifier or uid(),version=(old['version']+1 if old else 1), updated_at=now(),created_at=old['created_at'] if old else now())
        with self.connection('catalog') as db:
            db.execute('INSERT OR REPLACE INTO datasets VALUES (?,?)',(data['id'],dump(data)))
        return data

    def delete_dataset(self, identifier):
        self.get_dataset(identifier)
        with self.connection('catalog') as db: db.execute('DELETE FROM datasets WHERE id=?',(identifier,))

    def create_run(self, options, settings):
        from .core import component_dependencies, ALL_CONFIGS, config_definitions
        snapshot = self.get_dataset(options['dataset_id'])
        configs = options['configs']
        if not configs or any(c not in ALL_CONFIGS for c in configs): raise ValueError('유효한 구성을 선택하세요')
        saved_settings = {k:v for k,v in settings.items() if 'key' not in k.lower() and 'secret' not in k.lower()}
        dependencies = component_dependencies(configs)
        data = dict(id=uid(),status='PENDING',selected_configs=configs,dependencies=dependencies,mode=options.get('mode','reuse'),demo=bool(options.get('demo')),dataset_snapshot=snapshot,settings=saved_settings,environment={},created_at=now(),started_at=None,finished_at=None,cancel_requested=False,progress={'completed':0,'total':0,'current':None},options=options,parent_run_id=options.get('parent_run_id'),events=[],error=None)
        data['config_definitions']=config_definitions(configs)
        self.update_run(data)
        return data

    def update_run(self, run):
        payload = {k:v for k,v in run.items() if k not in ('results','metrics','totals','cascade_diagnostics')}
        with self.connection('demo' if run['demo'] else 'real') as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT payload FROM runs WHERE id=?',(run['id'],)).fetchone()
            if old and json.loads(old[0]).get('cancel_requested'):
                payload['cancel_requested']=True
            db.execute('INSERT OR REPLACE INTO runs VALUES (?,?)',(run['id'],dump(payload)))

    def get_run(self, identifier, demo=False):
        with self.connection('demo' if demo else 'real') as db:
            row = db.execute('SELECT payload FROM runs WHERE id=?',(identifier,)).fetchone()
            if not row: raise KeyError(identifier)
            data = json.loads(row[0])
            data['results'] = [json.loads(r[0]) for r in db.execute('SELECT payload FROM results WHERE run_id=? ORDER BY rowid',(identifier,))]
        from .core import calculate_metrics, config_definitions
        from .cascade import cascade_diagnostics
        data.setdefault('config_definitions',config_definitions(data['selected_configs']))
        data['cascade_diagnostics'] = cascade_diagnostics(data['dataset_snapshot']['samples'],data['results'],data['selected_configs'])
        data['metrics'] = {config:calculate_metrics(data['dataset_snapshot']['samples'],[r for r in data['results'] if r['config_id']==config and not r.get('component_for') and not r.get('is_warmup')]) for config in data['selected_configs']}
        api = [r for r in data['results'] if r['config_id']=='jev' and not r.get('reused')]
        charged = [r['cost'] for r in api if r.get('cost') is not None]
        elapsed = None
        if data['started_at']:
            elapsed = (datetime.fromisoformat(data['finished_at'] or now())-datetime.fromisoformat(data['started_at'])).total_seconds()*1000
        def unknown_attempts(row):
            if 'unknown_cost_attempt_count' in row: return row['unknown_cost_attempt_count']
            return sum(a.get('cost') is None for a in (row.get('attempts') or [])) if row.get('cost') is None else 0
        data['totals'] = {'api_calls':sum(len(r.get('attempts') or []) for r in api),'cost_usd':sum(charged) if charged else None,'unknown_cost_calls':sum(unknown_attempts(r) for r in api),'elapsed_ms':elapsed,'cost_note':'실제 요청 기준. 알 수 없는 비용은 제외한 알려진 소계이며 0으로 가정하지 않습니다. DEMO는 유료 호출이 없습니다.'}
        for config,metric in data['metrics'].items():
            group=[r for r in data['results'] if (r['config_id']==config and not r.get('component_for')) or r.get('component_for')==config]
            new_api=[r for r in group if r['config_id']=='jev' and not r.get('reused')]
            known=[r['cost'] for r in new_api if r.get('cost') is not None]
            is_reuse=config.endswith('_jev') and data['mode']=='reuse'
            metric['cost']={'actual_usd':sum(known) if known else (0 if not data['demo'] and not new_api else None),'api_calls':sum(len(r.get('attempts') or []) for r in new_api),'unknown_calls':sum(unknown_attempts(r) for r in new_api),'reused':is_reuse,'operating_cost_usd':None,'note':'이 구성에 속한 신규 API 요청 비용. 로컬 1차 재사용과 Jev 2차 신규 호출은 구분하며 전력·장비 비용은 제외.' if config.endswith('_then_jev') else ('추가 API 지출. 구성 요소 비용은 단독 구성에 1회 계상; 새 실행 예상 운영비는 N/A' if is_reuse else '외부 API의 확인된 비용 소계. 로컬 전력·장비 비용 제외')}
            resources={}
            for key in ('system_ram_used_peak_bytes','backend_rss_peak_bytes','ollama_rss_peak_bytes','gpu_memory_peak_bytes','shared_gpu_memory_peak_bytes'):
                values=[r['resources'].get(key) for r in group if isinstance(r.get('resources'),dict) and isinstance(r['resources'].get(key),(int,float))]
                resources[key]=max(values) if values and config!='jev' else None
            resources['note']='시스템 RAM, 백엔드 RSS, Ollama/runner RSS는 별도 수집. 서로 합산하지 않음. Jev 서버 자원은 N/A.'
            metric['resources']=resources
        return data

    def run_metadata(self, identifier, demo=False):
        with self.connection('demo' if demo else 'real') as db:
            row=db.execute('SELECT payload FROM runs WHERE id=?',(identifier,)).fetchone()
        if not row: raise KeyError(identifier)
        return json.loads(row[0])

    def list_runs(self, demo=False):
        with self.connection('demo' if demo else 'real') as db:
            items=[json.loads(r[0]) for r in db.execute('SELECT payload FROM runs ORDER BY rowid DESC')]
        return items

    def save_result(self, result, demo=False):
        if result.get('status') != 'SUCCESS': result['decision'] = None
        elif result.get('decision') not in ('NORMAL','INJECTION','REVIEW'):
            result.update(status='ERROR',decision=None,error={'type':'invalid_decision','message':'유효하지 않은 최종 판정'})
        with self.connection('demo' if demo else 'real') as db:
            db.execute('INSERT OR REPLACE INTO results VALUES (?,?,?)',(result['id'],result['run_id'],dump(result)))

    def cancel(self, identifier, demo=False):
        run=self.get_run(identifier,demo)
        if run['status'] in ('PENDING','RUNNING'):
            run['cancel_requested']=True
            self.update_run(run)
        return run

    def delete_run(self, identifier, demo=False):
        run=self.get_run(identifier,demo)
        if run['status'] in ('PENDING','RUNNING'): raise ValueError('실행 중인 실험은 먼저 취소하세요')
        with self.connection('demo' if demo else 'real') as db:
            db.execute('DELETE FROM results WHERE run_id=?',(identifier,))
            db.execute('DELETE FROM runs WHERE id=?',(identifier,))

    def recover(self):
        for demo in (False,True):
            for run in self.list_runs(demo):
                if run['status'] in ('PENDING','RUNNING'):
                    run.update(status='INTERRUPTED',finished_at=now(),error={'type':'server_interrupted','message':'서버 중단. 기존 결과를 보존했습니다. 새 시도로 재실행하세요.'})
                    self.update_run(run)
                    for result in self.get_run(run['id'],demo)['results']:
                        if result['status'] in ('PENDING','RUNNING'):
                            result.update(status='SKIPPED',decision=None,error={'type':'server_interrupted','message':'서버 중단으로 미완료'})
                            self.save_result(result,demo)
