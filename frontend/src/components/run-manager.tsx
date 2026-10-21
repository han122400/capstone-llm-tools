"use client";
import { useState } from "react";
import { Play, RefreshCw, Square, Trash2, Download as DownloadIcon } from "lucide-react";
import { api, post } from "@/lib/api";
import { Config, Dataset, Run, modeLabel, LEGACY_CONFIGS, displayDate, duration, json, money } from "@/lib/types";
import { Badge, Button, Download, Empty, Field, Notice, Panel, Status } from "./shared";
import {DatasetScope} from "./source-info";
import { FieldSet, FieldLegend } from "./ui/field";

type Props={datasets:Dataset[];configs:Config[];runs:Run[];run:Run|null;demo:boolean;settings:Record<string,unknown>;onCreated:(r:Run)=>void;onSelect:(id:string)=>void;onRefresh:()=>Promise<void>;notify:(m:string,error?:boolean)=>void};
type Preflight={checked_at?:string;models?:Record<string,{ready?:boolean;status?:string;model?:string;requested_model?:string;error?:{type?:string;message?:string};[key:string]:unknown}>;[key:string]:unknown};
export function RunManager({datasets,configs,runs,run,demo,settings,onCreated,onSelect,onRefresh,notify}:Props) {
  const [datasetId,setDatasetId]=useState("");const active=datasets.find(d=>d.id===datasetId)||datasets[0];
  const [selected,setSelected]=useState(configs.map(c=>c.id));const [mode,setMode]=useState<"reuse"|"live">("reuse");
  const [explanations,setExplanations]=useState(false);const [warmup,setWarmup]=useState(false);const [transfer,setTransfer]=useState(false);
  const [preflight,setPreflight]=useState<Preflight|null>(null);const [busy,setBusy]=useState(false);
  const dependsJev=selected.some(c=>c==="jev"||c.endsWith("_jev"));
  const plannedJevCalls=(active?.samples.length??0)*selected.filter(c=>c==="jev"||c.endsWith("_then_jev")).length;
  const current=run?.progress?.current;
  const currentText=typeof current==="object"&&current?`${configs.find(c=>c.id===current.config_id)?.name||current.config_id} · ${current.sample_id}`:current||"대기 또는 완료";
  const work=async(fn:()=>Promise<void>)=>{setBusy(true);try{await fn();}catch(e){notify((e as Error).message,true);}finally{setBusy(false);}};
  const check=()=>void work(async()=>{setPreflight(await post<Preflight>("/preflight"));notify("연결 상태를 확인했습니다. 유료 추론 요청은 보내지 않았습니다.");});
  const start=()=>void work(async()=>{
    if(!active)throw new Error("먼저 데이터셋을 등록하세요.");if(!selected.length)throw new Error("하나 이상의 평가 구성을 선택하세요.");
    if(!demo && dependsJev && !transfer)throw new Error("OpenRouter 전송과 비용 발생 가능성을 확인하세요.");
    const r=await post<Run>("/runs",{dataset_id:active.id,configs:selected,mode,demo,explanations,warmup,external_transfer_confirmed:transfer});
    onCreated(r);notify(`${demo?"DEMO 모의":"실제"} 평가를 대기열에 등록했습니다.`);
  });
  const toggle=(id:string)=>setSelected(s=>s.includes(id)?s.filter(x=>x!==id):[...s,id]);
  return <>
    {demo && <Notice><strong>DEMO · 실제 모델을 호출하지 않습니다.</strong> 가짜 모델 응답으로 동작을 점검하며 실제 평가와 별도 저장합니다. DEMO 성능과 비용은 모델의 실제 성능이 아닙니다.</Notice>}
    <Panel title="새 평가" description="실험마다 데이터셋·설정·입력을 고정합니다. 기존 결과를 덮어쓰지 않습니다.">
      <div className="stack"><div className="field-grid"><Field label="평가 데이터셋" htmlFor="run-dataset"><select id="run-dataset" className="form-control" value={active?.id||""} onChange={e=>setDatasetId(e.target.value)}>{datasets.length===0 && <option value="">등록된 데이터셋 없음</option>}{datasets.map(d=><option key={d.id} value={d.id}>{d.name} · v{d.version} · {d.samples.length}건 · {d.split==="evaluation"?"최종 평가":"개발"}</option>)}</select></Field><Field label="평가 모드" htmlFor="run-mode"><select id="run-mode" className="form-control" value={mode} onChange={e=>setMode(e.target.value as "reuse"|"live")}><option value="reuse">로컬 1차 재사용 · Jev 2차 신규 호출</option><option value="live">2단계 전체 순차 호출 · 실측</option></select></Field></div>
        {active&&<DatasetScope dataset={active}/>}<FieldSet><FieldLegend variant="label">평가 구성 · 총 5개</FieldLegend><div className="config-grid">{configs.map(c=><label className="config-choice" key={c.id}><input type="checkbox" checked={selected.includes(c.id)} onChange={()=>toggle(c.id)} aria-label={`${c.name} 선택`}/><div><strong>{c.name}</strong><small>{c.kind} {c.components?.length?`· ${c.components.join(" → ")}`:"· 독립 판정"}</small></div></label>)}</div></FieldSet>
        <Notice>{mode==="reuse"?"로컬 1차 판정은 같은 실험 안에서 재사용합니다. 각 2단계 구성은 원본 이메일과 로컬 판정을 Jev에 새로 보내며 Jev의 답을 최종 판정으로 사용합니다. Jev 단독 응답은 재사용하지 않습니다. 전체 2단계 실측 시간은 N/A입니다.":"각 구성에서 로컬 1차 판단 → 원본 이메일과 로컬 판정을 Jev에 전달 → Jev 최종 판단까지 순차 실행하고 전체 시간을 직접 측정합니다. 두 모델의 답이 달라도 검토 필요로 강제 변경하지 않습니다. 단독 평가도 선택하면 별도 호출합니다."}</Notice>
        {dependsJev&&<p className="caption">선택한 구성의 Jev 요청 계획: {plannedJevCalls}회. 모든 1차 판정이 성공할 때의 수량이며 재시도는 별도입니다. {demo?"DEMO에서는 실제 호출·청구가 없습니다.":"실제 응답 비용은 요청별로 합산합니다."}</p>}
        <div className="row gap-6"><label className="check-row"><input type="checkbox" checked={explanations} onChange={e=>setExplanations(e.target.checked)}/>로컬 설명 생성 · 추가 지연 기록</label><label className="check-row"><input type="checkbox" checked={warmup} onChange={e=>setWarmup(e.target.checked)}/>로컬 워밍업 · 본 평가 통계에서 제외</label></div>
        <p className="caption">컨텍스트 {String(settings.context_length??4096)} · 로컬 동시 요청 1 · 모델별 묶음 실행 · 메일별 독립 세션. 긴 입력은 조용히 자르지 않습니다. Jev의 제공되지 않은 설명은 생성하지 않습니다.</p>
        {!demo && dependsJev && <Notice variant="warning"><strong>외부 전송 및 API 비용</strong><p>선택한 구성은 선택한 이메일의 확인된 제목·발신자와 공통 분석 본문을 OpenRouter에 전송합니다. 2단계 평가에서는 로컬 1차 판정도 함께 전송합니다. 정답과 출처는 전송하지 않습니다. 실제 요청에는 비용이 발생할 수 있습니다. API 키 존재 확인은 인증·추론 검증과 다릅니다.</p><label className="check-row mt-2"><input type="checkbox" checked={transfer} onChange={e=>setTransfer(e.target.checked)}/>합성 이메일 외부 전송과 유료 호출 가능성을 확인했습니다.</label></Notice>}
        <div className="sticky-actions"><Button disabled={busy||!active||!selected.length||(!demo&&dependsJev&&!transfer)} onClick={start}><Play/> {demo?"DEMO 평가 시작":"실제 평가 시작"}</Button><Button variant="outline" disabled={busy} onClick={check}><RefreshCw/>연결 상태 확인</Button><span className="caption">자동 다운로드·유료 자동 테스트 없음</span></div>
      </div>
    </Panel>
    {preflight && <Panel title="사전 연결 검사" description={`마지막 확인 ${displayDate(preflight.checked_at)} · 유료 추론 미수행`}>
      <div className="table-scroll"><table className="data-table"><thead><tr><th>구성 요소</th><th>준비 상태</th><th>모델 / 확인 정보</th></tr></thead><tbody>{Object.entries(preflight.models||{}).map(([id,m])=><tr key={id}><td>{configs.find(c=>c.id===id)?.name||id}</td><td><Badge variant={m.ready?"secondary":"outline"}>{m.ready?"연결 준비됨":m.status==="CONNECTION_REQUIRED"?"API 키 연결 필요":m.status==="NOT_INSTALLED"||m.error?.type==="MODEL_NOT_INSTALLED"?"설치 필요":m.error?.type==="MODEL_NOT_CONFIGURED"?"모델 태그 설정 필요":m.status||"미검증"}</Badge>{m.identity_verified===false&&<Badge variant="outline">모델 정체성 미검증</Badge>}</td><td>{m.requested_model||m.model||"미설정"}{!m.ready&&m.error!=null&&<p className="caption max-w-lg whitespace-normal">{json(m.error)}</p>}{Array.isArray(m.warnings)&&m.warnings.length>0&&<p className="caption max-w-lg whitespace-normal">{m.warnings.map(w=>typeof w==="string"?w:json(w)).join(" · ")}</p>}</td></tr>)}</tbody></table></div><details className="subsection"><summary className="text-xs font-semibold">환경·설치 목록·템플릿·오프로딩 원본</summary><pre className="text-block mt-3">{json(preflight)}</pre></details>
    </Panel>}
    {run && <Panel title="선택한 실험 진행 상태" description={`${run.id} · ${modeLabel(run)}`} action={<Status value={run.status}/>}>
      <div className="row between"><span><strong>{run.progress?.completed??0}</strong> / {run.progress?.total??0} 평가 항목 처리</span><span className="caption">전체 소요 {duration(run.totals?.elapsed_ms)}</span></div><div className="progress-track" role="progressbar" aria-label="평가 진행률" aria-valuenow={run.progress?.completed||0} aria-valuemin={0} aria-valuemax={run.progress?.total||1}><div className="progress-fill" style={{width:`${run.progress?.total?(run.progress.completed/run.progress.total)*100:0}%`}}/></div>
      <p className="caption">현재 샘플: {currentText}</p>
      <div className="row mt-4">{["PENDING","RUNNING"].includes(run.status)?<Button variant="outline" onClick={()=>void work(async()=>{const r=await post<Run>(`/runs/${run.id}/cancel`);onCreated(r);notify("취소를 요청했습니다. 진행 중 요청이 종료된 뒤 후속 실행을 중단합니다.");})}><Square/>취소</Button>:<Button variant="outline" disabled={run.selected_configs.some(id=>LEGACY_CONFIGS.some(c=>c.id===id))} title="기존 독립 결합은 이력 조회 전용입니다" onClick={()=>void work(async()=>{const r=await post<Run>(`/runs/${run.id}/retry`);onCreated(r);notify("실패·미완료 이메일을 새 실험으로 재실행합니다.");})}><RefreshCw/>실패·미완료 항목 재실행</Button>}<Download href={`/api/runs/${run.id}/export?format=json`}><DownloadIcon/>JSON</Download><Download href={`/api/runs/${run.id}/export?format=csv`}>CSV</Download></div>
      <details className="subsection"><summary className="text-xs font-semibold">모델 로드·해제 이벤트 및 실행 기록</summary><pre className="text-block mt-3">{json({events:run.events,errors:(run.results??[]).filter(r=>r.status==="ERROR").map(r=>({sample_id:r.sample_id,config_id:r.config_id,error:r.error})),environment:run.environment})}</pre></details>
    </Panel>}
    <Panel title="실험 이력" description={`${demo?"DEMO":"실제"} 평가만 표시합니다. 실험을 선택하면 개요와 사례 비교에서도 같은 결과를 조회합니다.`}>
      {runs.length===0?<Empty title="저장된 실험이 없습니다" description="평가를 시작하면 진행 상태와 결과가 로컬 SQLite에 저장됩니다."/>:<div className="table-scroll"><table className="data-table"><thead><tr><th>실험 / 데이터셋</th><th>상태</th><th>모드</th><th>구성</th><th>실제 API 비용</th><th>생성 시각</th><th>관리</th></tr></thead><tbody>{runs.map(r=><tr key={r.id}><td><button className="text-left hover:text-primary" onClick={()=>onSelect(r.id)}><strong>{r.dataset_snapshot?.name||"실험"}</strong><span className="caption block">{r.id.slice(0,12)} {r.demo?"· DEMO":""}</span></button></td><td><Status value={r.status}/></td><td>{modeLabel(r)}</td><td>{r.selected_configs?.length??0}개</td><td>{money(r.totals?.cost_usd)}</td><td>{displayDate(r.created_at)}</td><td><Button variant="ghost" size="icon" aria-label={`${r.id} 실험 삭제`} disabled={["PENDING","RUNNING"].includes(r.status)} onClick={()=>void work(async()=>{if(!window.confirm("이 실험의 원본 입력·응답과 측정 기록을 삭제할까요? 복구할 수 없습니다."))return;await api(`/runs/${r.id}`,{method:"DELETE"});if(r.id===run?.id)onSelect("");await onRefresh();notify("실험과 원본 응답을 삭제했습니다.");})}><Trash2/></Button></td></tr>)}</tbody></table></div>}
    </Panel>
  </>;
}
