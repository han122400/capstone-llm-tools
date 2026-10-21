export type Decision = "NORMAL" | "INJECTION" | "REVIEW";
export type ResultStatus = "PENDING" | "RUNNING" | "SUCCESS" | "ERROR" | "CANCELLED" | "SKIPPED";
export type Config = {id: string; name: string; kind: string; components?: string[]};
export type Sample = {
  sample_id: string; subject: string; body: string; label: "NORMAL" | "INJECTION";
  language: string; category: string; synthetic: boolean | null; created_at?: string | null;
  notes: string; template_family?: string;
  source_dataset?: string | null; source_dataset_name?: string | null;
  source_url?: string | null; source_version?: string | null; source_sample_id?: string | null;
  source_file?: string | null; source_record_index?: number | null; source_line?: number | null;
  source_file_hash?: string | null; source_data_version?: string | null; source_download_url?: string | null;
  source_context?: Record<string,unknown> | null; pair_id?: string | null;
  transformation_version?: string | null; transformation_notes?: string | null;
  body_hash?: string | null; body_hash_method?: string | null;
  email?: {kind:"body_only"|"gmail_parsed";content:{analysis_text:string;subject?:string|null;sender?:string|null;warnings?:string[]|null;truncated?:boolean|null;attachments?:unknown[]|null;[key:string]:unknown}} | null;
};
export type Dataset = {id: string; name: string; version: number | string; split: "development" | "evaluation"; samples: Sample[];manifest?:Record<string,unknown>|null};
export type Metric = {value: number | null; numerator: number; denominator: number; description: string};
export type Latency = {count?: number; mean_ms: number | null; median_ms: number | null; p95_ms: number | null; max_ms?:number|null};
export type ConfigMetrics = {
  N: number; counts: Record<string, number>;
  class_counts?: Record<string,number>;
  confusion: Record<string, Record<string, number>>;
  metrics: Record<string, Metric>;
  latency?: {success: Latency; error: Latency};
  cost?: {actual_usd:number|null;api_calls:number;unknown_calls:number;reused?:boolean;operating_cost_usd?:number|null;note?:string};
  resources?: Record<string,number|string|null>;
};
export type Result = {
  id: string; run_id: string; config_id: string; sample_id: string; status: ResultStatus;
  decision: Decision | null; latency_ms: number | null; cost?: number | null;
  raw_response?: unknown; raw_input?: unknown; error?: unknown;
  component_result_ids?: string[]; reused?: boolean;
  local_decision?:Decision|null; jev_decision?:Decision|null; decision_changed?:boolean|null;
  local_result_reused?:boolean; local_latency_ms?:number|null; jev_latency_ms?:number|null;
  probabilities?: Record<string, number> | null; confidence?: number | null;
  resources?: Record<string, unknown> | null;
  [key: string]: unknown;
};
export type Run = {
  id: string; status: string; selected_configs: string[]; mode: "reuse" | "live";
  demo: boolean; dataset_snapshot: Dataset; settings: Record<string, unknown>;
  environment: Record<string, unknown>; created_at: string; started_at?: string;
  finished_at?: string; progress: {completed: number; total: number; current?: string | {config_id:string;sample_id:string} | null};
  config_definitions?:Config[]; cascade_diagnostics?:Record<string,CascadeDiagnostic>;
  results: Result[]; metrics: Record<string, ConfigMetrics>;
  totals: {api_calls?: number; cost_usd?: number | null; unknown_cost_calls?: number; elapsed_ms?: number | null};
  [key: string]: unknown;
};
export const CONFIGS: Config[] = [
  {id:"foundation_sec",name:"Foundation-Sec",kind:"Local"},
  {id:"qwen",name:"Qwen",kind:"Local"},
  {id:"jev",name:"Jev",kind:"API"},
  {id:"foundation_sec_then_jev",name:"Foundation-Sec → Jev",kind:"Cascade",components:["foundation_sec","jev"]},
  {id:"qwen_then_jev",name:"Qwen → Jev",kind:"Cascade",components:["qwen","jev"]}
];
export const LEGACY_CONFIGS:Config[]=[
  {id:"foundation_sec_jev",name:"Foundation-Sec + Jev · 기존 독립 결합",kind:"Legacy",components:["foundation_sec","jev"]},
  {id:"qwen_jev",name:"Qwen + Jev · 기존 독립 결합",kind:"Legacy",components:["qwen","jev"]}
];
export function configsForRun(configs:Config[],run:Run|null) {
  if(run?.selected_configs.some(id=>LEGACY_CONFIGS.some(c=>c.id===id)))return [...configs.filter(c=>!c.id.endsWith("_then_jev")),...LEGACY_CONFIGS];
  return configs;
}
export function modeLabel(run:Run) {
  const cascade=run.selected_configs.some(id=>id.endsWith("_then_jev"));
  return cascade?(run.mode==="reuse"?"2단계 평가 · 로컬 1차 재사용":"2단계 평가 · 전체 순차 호출"):(run.mode==="reuse"?"결과 재사용 평가":"실시간 독립 결합 평가");
}
export const decisionName=(value:string|null|undefined)=>({NORMAL:"정상",INJECTION:"인젝션",REVIEW:"검토 필요"}[value||""]||"판정 없음");
export type CascadeDiagnostic={N:number;compared:number;changed:number;unavailable:number;transitions:Record<string,Record<string,number>>;baseline:Record<string,number>};
export type Statistics = {
  config_definitions?:Config[];cascade_diagnostics?:Record<string,CascadeDiagnostic>;
  run_count:number;run_ids:string[];partial_run_count:number;sample_count:number;
  class_counts:Record<string,number>;mixed_conditions:boolean;
  metrics:Record<string,ConfigMetrics>;totals:Run['totals'];
  options:{datasets:{value:string;label:string}[];prompts:string[]};
};
export const metricLabels: Record<string,string> = {
  automatic_rate:"자동 판정률", injection_detection_rate:"인젝션 자동 탐지율", false_positive_rate:"정상 메일 오탐률",
  review_rate:"REVIEW 비율", error_rate:"기술적 실패율", correct_rate:"올바른 자동 판정 비율",
  miss_rate:"탐지 누락률", injection_review_rate:"실제 인젝션의 REVIEW 비율", injection_error_rate:"실제 인젝션의 실패 비율",
  precision:"자동 판정 Precision", recall:"자동 판정 Recall", f1:"자동 판정 F1"
};
export const statusLabels: Record<string,string> = {PENDING:"대기",RUNNING:"진행 중",COMPLETED:"완료",CANCELLED:"취소",INTERRUPTED:"서버 중단",SUCCESS:"성공",ERROR:"실패",SKIPPED:"미실행"};
export function percent(value: number | null | undefined) {return value == null ? "N/A" : `${(value * 100).toFixed(1)}%`;}
export function duration(ms: number | null | undefined) {return ms == null ? "N/A" : ms < 1000 ? `${ms.toFixed(0)} ms` : `${(ms/1000).toFixed(2)} s`;}
export function money(value: number | null | undefined) {return value == null ? "N/A" : `$${value.toFixed(6)}`;}
export function displayDate(value: string | null | undefined) {return value ? new Date(value).toLocaleString("ko-KR",{timeZone:"Asia/Seoul"}) : "N/A";}
export function json(value: unknown) {return value == null ? "N/A" : typeof value === "string" ? value : JSON.stringify(value,null,2);}
