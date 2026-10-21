"use client";
import { useEffect, useState } from "react";
import { RefreshCw, Save } from "lucide-react";
import { api, post } from "@/lib/api";
import { displayDate, json } from "@/lib/types";
import { Badge, Button, Field, Notice, Panel } from "./shared";
import { PromptViewer, type ClassificationPrompt } from "./prompt-viewer";

type Props={settings:Record<string,unknown>;onRefresh:()=>Promise<void>;notify:(m:string,error?:boolean)=>void};
const editable=["ollama_url","foundation_sec_model","qwen_model","qwen_thinking","jev_model","context_length","temperature","seed","max_output_tokens","timeout_seconds","max_attempts"] as const;
export function Settings({settings,onRefresh,notify}:Props) {
  const [form,setForm]=useState<Record<string,string>>({});const [busy,setBusy]=useState(false);const [check,setCheck]=useState<Record<string,unknown>|null>(null);
  useEffect(()=>{setForm(Object.fromEntries(editable.map(k=>[k,String(settings[k]??(k==="qwen_thinking"?false:""))])));},[settings]);
  const update=(key:string,value:string)=>setForm(s=>({...s,[key]:value}));
  const perform=async(fn:()=>Promise<void>)=>{setBusy(true);try{await fn();}catch(e){notify((e as Error).message,true);}finally{setBusy(false);}};
  const ollama=check?.ollama as {installed_models?:{name?:string;model?:string}[];version?:string;connected?:boolean}|undefined;
  const installed=ollama?.installed_models||[];
  const checkModels=(check?.models||{}) as Record<string,{ready?:boolean;status?:string;model?:string;requested_model?:string;identity_unverified?:boolean;warnings?:unknown[];error?:{type?:string;message?:string}}>;
  return <>
    <Notice><strong>API 키는 백엔드 환경변수로만 설정합니다.</strong> <code>OPENROUTER_API_KEY</code>를 프로젝트 루트의 로컬 .env 또는 현재 백엔드 실행 환경에 설정하세요. 브라우저, DB, 로그에는 키를 저장하지 않습니다. 이 화면에서는 설정 여부만 표시합니다.</Notice>
    <form className="stack" onSubmit={e=>{e.preventDefault();void perform(async()=>{const payload=Object.fromEntries(editable.map(k=>[k,k==="qwen_thinking"?form[k]==="true":["context_length","temperature","seed","max_output_tokens","timeout_seconds","max_attempts"].includes(k)?Number(form[k]):form[k]]));await api("/settings",{method:"PUT",body:JSON.stringify(payload)});await onRefresh();notify("추론 설정을 저장했습니다. 기존 실험 스냅샷은 변경하지 않습니다.");});}}>
      <div className="split"><Panel title="Ollama 로컬 모델" description="설치된 실제 태그를 지정하세요. 모델을 조용히 대체하거나 자동 다운로드하지 않습니다."><div className="stack">
        <Field label="Ollama 연결 주소" htmlFor="setting-ollama"><input id="setting-ollama" className="form-control" required value={form.ollama_url||""} onChange={e=>update("ollama_url",e.target.value)} placeholder="http://127.0.0.1:11434"/></Field>
        <Field label="Foundation-Sec 실제 모델 태그" htmlFor="setting-foundation" description="Foundation-Sec-8B-Reasoning / Q4_K_M 확인 필요"><input id="setting-foundation" className="form-control" list="installed-models" value={form.foundation_sec_model||""} onChange={e=>update("foundation_sec_model",e.target.value)} placeholder="설치된 실제 Ollama 모델 태그"/></Field>
        <Field label="Qwen 모델 태그" htmlFor="setting-qwen" description="Qwen3.5-9B / Q4_K_M 확인 필요"><input id="setting-qwen" className="form-control" list="installed-models" required value={form.qwen_model||""} onChange={e=>update("qwen_model",e.target.value)}/></Field>
        <Field label="Qwen thinking 모드" htmlFor="setting-qwen-thinking" description="Qwen 단독·Qwen → Jev의 로컬 단계에 적용합니다. ON은 추론 생성으로 출력 예산과 처리 시간이 늘어날 수 있습니다."><select id="setting-qwen-thinking" className="form-control" value={form.qwen_thinking||"false"} onChange={e=>update("qwen_thinking",e.target.value)}><option value="false">OFF · 추론 끄기</option><option value="true">ON · 추론 켜기</option></select></Field>
        <datalist id="installed-models">{installed.map((m,i)=><option key={i} value={m.name||m.model}/>)}</datalist><p className="caption">로컬 동시 요청 1. Foundation-Sec와 Qwen을 동시에 로드하지 않습니다. Intel GPU 가속은 확인 전 미검증입니다.</p>
      </div></Panel>
      <Panel title="OpenRouter Jev" description="Decisions 전용 어댑터 · 일반 Chat Completions와 분리"><div className="stack">
        <Field label="OpenRouter 모델 ID" htmlFor="setting-jev"><input id="setting-jev" className="form-control" required value={form.jev_model||""} onChange={e=>update("jev_model",e.target.value)}/></Field>
        <div className="row"><strong className="text-xs">API 키 상태</strong><Badge variant={settings.openrouter_key_configured?"secondary":"outline"}>{settings.openrouter_key_configured?"설정됨 · 인증/추론 미검증":"연결 필요 · 미설정"}</Badge></div>
        <p className="caption">모델의 실제 제공 여부, 반환 버전, provider, usage, cost는 API가 확인하거나 반환한 정보만 저장합니다. 반환되지 않는 값은 null로 남깁니다.</p><p className="caption">Jev 서버 RAM / GPU: N/A. PC의 API 클라이언트 메모리를 외부 모델 메모리로 표시하지 않습니다.</p>
      </div></Panel></div>
      <Panel title="공통 추론 조건" description="기본 출력은 최소 판정만 요청합니다. 모델별 실제 지원 설정은 실험 스냅샷과 연결 상세에서 확인합니다."><div className="field-grid">
        <Field label="컨텍스트 길이" htmlFor="setting-context" description="입력·시스템 지시·thinking·최종 답변이 공유합니다. 모델 지원 범위는 연결 검사에서 확인합니다."><input id="setting-context" className="form-control" type="number" min="4096" max="65536" required value={form.context_length||"4096"} onChange={e=>update("context_length",e.target.value)}/></Field>
        <Field label="temperature" htmlFor="setting-temp"><input id="setting-temp" className="form-control" type="number" min="0" max="2" step="0.1" required value={form.temperature||"0"} onChange={e=>update("temperature",e.target.value)}/></Field>
        <Field label="seed" htmlFor="setting-seed"><input id="setting-seed" className="form-control" type="number" min="0" max="2147483647" required value={form.seed||"0"} onChange={e=>update("seed",e.target.value)}/></Field>
        <Field label="출력 토큰 제한" htmlFor="setting-tokens" description="thinking + 최종 JSON의 총 상한입니다. 출력만 늘리면 입력 공간이 줄어듭니다."><input id="setting-tokens" className="form-control" type="number" min="16" max="8192" required value={form.max_output_tokens||"64"} onChange={e=>update("max_output_tokens",e.target.value)}/></Field>
        <Field label="요청 timeout · 초" htmlFor="setting-timeout"><input id="setting-timeout" className="form-control" type="number" min="1" max="600" required value={form.timeout_seconds||"120"} onChange={e=>update("timeout_seconds",e.target.value)}/></Field>
        <Field label="최대 시도 횟수 · 최초 포함" htmlFor="setting-attempts"><input id="setting-attempts" className="form-control" type="number" min="1" max="3" required value={form.max_attempts||"3"} onChange={e=>update("max_attempts",e.target.value)}/></Field>
      </div><div className="row mt-4"><Button type="button" variant="outline" disabled={busy} onClick={()=>setForm(s=>({...s,context_length:"8192",max_output_tokens:"4096",timeout_seconds:"480",qwen_thinking:"true"}))}>Thinking 시험 설정 채우기</Button><span className="caption">8192 컨텍스트 · 총 출력 4096 · 480초 · Qwen ON. 아래 설정 저장을 누르면 적용됩니다.</span></div>
      <p className="caption mt-3">두 로컬 모델의 공통 예산입니다. 컨텍스트 증가로 RAM과 처리 시간이 늘 수 있습니다. 완료·정확도 향상은 미검증입니다. OFF/ON 비교 시 같은 예산을 사용하세요. 변경 후에는 새 실험을 시작하세요. 실패 항목 재실행은 이전 실험 설정을 사용합니다.</p>
      <p className="caption mt-4">저장된 예산: 컨텍스트 {String(settings.context_length??"N/A")} · 총 출력 {String(settings.max_output_tokens??"N/A")} · 최대 입력 UTF-8 바이트 {String(settings.input_limit_bytes??settings.max_input_bytes??"N/A")} · 자동 절단 없음. 입력 바이트 기반의 보수적 계산이며 정확한 토큰 수가 아닙니다. 모델의 기존 system/messages는 추가 검사합니다.</p>
      <p className="caption mt-3">Qwen thinking 저장값: {settings.qwen_thinking===true?"ON":"OFF"} · Foundation thinking / reasoning: {settings.thinking==null?"모델 지원 확인 후 결정 · 미지정":String(settings.thinking)} · 메모리 수집 간격 {String(settings.memory_interval_seconds??"N/A")}초</p></Panel>
      <div className="row"><Button type="submit" disabled={busy}><Save/>설정 저장</Button><Button type="button" variant="outline" disabled={busy} onClick={()=>void perform(async()=>{setCheck(await post("/preflight"));notify("설치 모델과 연결 상태를 확인했습니다. 유료 추론은 실행하지 않았습니다.");})}><RefreshCw/>설치 모델 및 연결 확인</Button></div>
    </form>
    {check && <Panel title="설치 및 실행 환경 확인" description={`마지막 확인 ${displayDate(check.checked_at as string)} · Ollama ${ollama?.version||"N/A"}`}><div className="row mb-3"><Badge variant="outline">{ollama?.connected?"Ollama 연결됨":"Ollama 연결 필요"}</Badge><Badge variant="outline">실제 유료 추론 미검증</Badge><Badge variant="outline">GPU 백엔드 확인 필요</Badge></div>
      <div className="table-scroll"><table className="data-table"><thead><tr><th>모델</th><th>상태</th><th>요청 태그 / 모델 ID</th><th>확인 정보</th></tr></thead><tbody>{Object.entries(checkModels).map(([id,m])=><tr key={id}><td className="name">{id==="foundation_sec"?"Foundation-Sec":id==="qwen"?"Qwen":"Jev"}</td><td><Badge variant={m.ready?"secondary":"outline"}>{m.ready?"연결 준비됨":m.error?.type==="MODEL_NOT_INSTALLED"?"설치 필요":m.status==="CONNECTION_REQUIRED"?"API 키 연결 필요":m.error?.type==="MODEL_NOT_CONFIGURED"?"모델 태그 설정 필요":m.error?.type==="MODEL_IDENTITY_MISMATCH"?"모델 정체성 불일치":m.status||"미검증"}</Badge>{m.identity_unverified&&<Badge variant="outline">모델 정체성 미검증</Badge>}</td><td>{m.requested_model||m.model||"미설정"}</td><td className="max-w-md whitespace-normal text-xs">{m.error?.message|| (id==="jev"?"키 존재 확인은 인증·유료 추론 검증이 아닙니다.":"Q4_K_M / 모델 메타데이터 확인")}{m.warnings?.length?<p className="caption mt-1">{m.warnings.map(w=>typeof w==="string"?w:json(w)).join(" · ")}</p>:null}</td></tr>)}</tbody></table></div>
      <p className="caption mt-3">설치된 태그: {installed.length?installed.map(m=>m.name||m.model).join(", "):"N/A · 연결 상태 또는 설치 목록을 확인하세요."}</p><details className="subsection"><summary className="text-xs font-semibold">전체 환경·모델 템플릿·오프로딩 확인 원본</summary><pre className="text-block mt-3">{json(check)}</pre></details>
    </Panel>}
    <Panel title="판정 및 결합 정책" description="두 결합 구성에 동일한 공통 정책을 적용합니다."><dl className="key-values"><dt>판정 기준</dt><dd>{String(settings.prompt_version??"N/A")}</dd><dt>결합 정책</dt><dd>{String(settings.policy_version??"N/A")}</dd><dt>전처리</dt><dd>{String(settings.preprocess_version??"N/A")}</dd><dt>실시간 호출 방식</dt><dd>{String(settings.live_call_strategy??"순차")}</dd></dl><p className="caption mt-3">두 구성 요소가 SUCCESS이고 판정이 같으면 해당 판정을 사용합니다. 불일치 또는 하나 이상 REVIEW면 REVIEW입니다. 기술적 실패·취소·미완료는 유효한 최종 판정을 만들지 않습니다.</p><details className="subsection"><summary className="text-xs font-semibold">공개 설정 전체</summary><pre className="text-block mt-3">{json(settings)}</pre></details></Panel>
    <PromptViewer prompt={settings.classification_prompt as ClassificationPrompt | undefined}/>
  </>;
}
