"use client";
import { useState } from "react";
import { Config, Result, Run, Sample, configsForRun, decisionName, duration, json, money } from "@/lib/types";
import {DecisionTransition} from "./cascade-comparison";
import {SourceBadge,SourceDetails,DatasetScope,sourceId} from "./source-info";
import { Badge, Empty, Notice, Panel, Status } from "./shared";

function modelResult(run:Run,sampleId:string,configId:string) {
  const matches=(run.results??[]).filter(r=>r.sample_id===sampleId&&r.config_id===configId&&!r.is_warmup);
  return matches.filter(r=>!r.component_for).at(-1);
}
export function Cases({run,configs:activeConfigs}: {run:Run|null;configs:Config[]}) {
  const [sourceFilter,setSourceFilter]=useState("");const [filter,setFilter]=useState("");const [query,setQuery]=useState("");const [sampleId,setSampleId]=useState("");
  if(!run)return <Panel><Empty description="실험을 선택하면 동일한 이메일에 대한 5개 구성의 판정을 비교할 수 있습니다."/></Panel>;
  const configs=configsForRun(activeConfigs,run);
  const rows=run.dataset_snapshot.samples.filter(s=>{
    if(sourceFilter&&sourceId(s)!==sourceFilter)return false;
    const results=configs.map(c=>modelResult(run,s.sample_id,c.id)).filter(Boolean) as Result[];
    if(query&&!`${s.subject} ${s.body} ${s.sample_id}`.toLowerCase().includes(query.toLowerCase()))return false;
    if(filter==="fp")return s.label==="NORMAL"&&results.some(r=>r.status==="SUCCESS"&&r.decision==="INJECTION");
    if(filter==="fn")return s.label==="INJECTION"&&results.some(r=>r.status==="SUCCESS"&&r.decision==="NORMAL");
    if(filter==="review")return results.some(r=>r.status==="SUCCESS"&&r.decision==="REVIEW");
    if(filter==="error")return results.some(r=>r.status==="ERROR");
    if(filter==="stage_changed")return results.some(r=>r.status==="SUCCESS"&&r.decision_changed===true);
    if(filter==="normal_to_injection")return results.some(r=>r.status==="SUCCESS"&&r.local_decision==="NORMAL"&&r.jev_decision==="INJECTION");
    if(filter==="injection_to_normal")return results.some(r=>r.status==="SUCCESS"&&r.local_decision==="INJECTION"&&r.jev_decision==="NORMAL");
    if(filter==="disagreement")return new Set(results.filter(r=>r.status==="SUCCESS").map(r=>r.decision)).size>1;
    return true;
  });
  const sample=rows.find(s=>s.sample_id===sampleId)||rows[0];
  return <>
    <DatasetScope dataset={run.dataset_snapshot}/>{run.demo && <Notice>DEMO 결과입니다. 아래의 모델 판정과 확률·비용은 가짜 응답을 이용한 동작 확인용입니다.</Notice>}
    <Panel title="이메일별 판정 매트릭스" description="셀을 선택하면 원본 입력·응답, 오류, 실제 제공된 확률과 구성 요소를 확인합니다.">
      <div className="filter-bar mb-4"><select aria-label="사례 출처 필터" className="form-control" value={sourceFilter} onChange={e=>setSourceFilter(e.target.value)}><option value="">모든 출처</option>{Array.from(new Set(run.dataset_snapshot.samples.map(sourceId))).map(v=><option key={v}>{v}</option>)}</select><input aria-label="사례 검색" className="form-control" placeholder="이메일 제목, 본문, 샘플 ID 검색" value={query} onChange={e=>setQuery(e.target.value)}/><select aria-label="사례 유형 필터" className="form-control" value={filter} onChange={e=>setFilter(e.target.value)}><option value="">전체 사례</option><option value="fp">정상 메일 오탐</option><option value="fn">인젝션 탐지 누락</option><option value="review">REVIEW</option><option value="stage_changed">2단계 판정 변경</option><option value="normal_to_injection">로컬 정상 → Jev 인젝션</option><option value="injection_to_normal">로컬 인젝션 → Jev 정상</option><option value="disagreement">모델 간 불일치</option><option value="error">기술적 실패</option></select><span className="caption">{rows.length} / {run.dataset_snapshot.samples.length}건</span></div>
      <div className="table-scroll"><table className="data-table"><thead><tr><th>이메일 / 정답</th>{configs.map(c=><th key={c.id}>{c.name}</th>)}</tr></thead><tbody>{rows.map(s=><tr key={s.sample_id} className="clickable-row" onClick={()=>setSampleId(s.sample_id)} aria-selected={sample?.sample_id===s.sample_id}><td><button className="text-left hover:text-primary" onClick={()=>setSampleId(s.sample_id)}><strong>{s.subject||"제목 없음"}</strong><div className="row gap-2 mt-1"><Status value={s.label}/><SourceBadge sample={s}/><span className="caption">{s.sample_id}</span></div></button></td>{configs.map(c=>{const r=modelResult(run,s.sample_id,c.id);return <td key={c.id}>{r?<><Status value={r.status==="SUCCESS"?r.decision:r.status}/><DecisionTransition result={r}/><span className="caption block mt-1">{r.component_for?"구성 요소 요청":r.local_result_reused?"로컬 1차 재사용 · Jev 신규 호출":r.reused?"결과 재사용":duration(r.latency_ms)}</span></>:<span className="caption">미실행</span>}</td>;})}</tr>)}</tbody></table></div>
      {!rows.length&&<Empty title="필터에 맞는 사례가 없습니다"/>}
    </Panel>
    {sample && <><Panel title={sample.subject||"제목 없음"} description={`${sample.sample_id} · ${sample.language} · ${sample.synthetic?"합성 이메일":"이메일"} · 데이터셋 v${run.dataset_snapshot.version}`} action={<Status value={sample.label}/>}><SourceDetails sample={sample}/><div className="text-block">{sample.body}</div><div className="row mt-3 caption"><span>평가 메타데이터: {sample.category}</span><span>템플릿: {sample.template_family||"미지정"}</span></div><p className="caption mt-2">이 텍스트의 HTML·명령·링크는 실행되지 않습니다. 정답과 평가 메타데이터는 모델 입력에서 제외합니다. 2단계 Jev에는 원문과 로컬 1차 판정만 전달합니다.</p></Panel>
      <div className="split">{configs.map(c=><ResultDetail key={c.id} result={modelResult(run,sample.sample_id,c.id)} config={c} sample={sample} run={run}/>)}</div>
    </>}
  </>;
}
function ResultDetail({result:r,config,sample,run}: {result:Result|undefined;config:Config;sample:Sample;run:Run}) {
  return <Panel title={config.name} description={config.kind} action={<Status value={r?.status==="SUCCESS"?r.decision:r?.status}/>}>
    {!r?<p className="caption">이 구성은 평가하지 않았습니다.</p>:<div className="stack gap-3">
      <DecisionTransition result={r}/><dl className="key-values"><dt>결과 ID</dt><dd>{r.id}</dd><dt>실제 모델 요청 시간</dt><dd>{r.reused&&(config.kind==="Cascade"||config.kind==="Legacy"||config.kind.toLowerCase()==="ensemble")?"N/A · 결과 재사용":duration(r.latency_ms)}</dd><dt>로컬 1차 요청 시간</dt><dd>{duration(r.local_latency_ms)}</dd><dt>Jev 2차 요청 시간</dt><dd>{duration(r.jev_latency_ms)}</dd><dt>결합 정책 계산 시간</dt><dd>{duration(r.combination_ms as number|null)}</dd><dt>응답 비용</dt><dd>{money(config.kind==="Cascade"?run.results.find(x=>x.id===r.component_result_ids?.[1])?.cost:r.cost??r.cost_usd as number|null)}{r.local_result_reused?" · Jev 2차 신규 요청 비용":r.reused?" · 재사용 중복 청구 없음":""}</dd><dt>실제 모델 / Provider</dt><dd>{String(r.actual_model??r.response_model??"N/A")} / {String(r.provider??"N/A")}</dd><dt>confidence</dt><dd>{r.confidence==null?"N/A":String(r.confidence)}</dd><dt>재시도 포함 시도</dt><dd>{String(r.attempt_count??r.attempts_count??(Array.isArray(r.attempts)?r.attempts.length:"N/A"))}</dd><dt>입력 해시</dt><dd>{String(r.input_hash??"N/A")}</dd><dt>정책 버전</dt><dd>{String(r.policy_version??run.settings?.policy_version??"N/A")}</dd></dl>
      {r.probabilities && <div><h3 className="mb-2">실제 제공된 선택지 확률</h3><pre className="text-block">{json(r.probabilities)}</pre><p className="caption mt-1">모델이 반환한 확률은 실제 정답률이나 정확도 보장 수치가 아닙니다.</p></div>}
      {r.error!=null && <Notice variant="error"><pre>{json(r.error)}</pre></Notice>}
      {!!r.component_result_ids?.length && <div><h3 className="mb-1">결합에 사용한 원본 판정</h3>{r.component_result_ids.map(id=>{const part=(run.results??[]).find(x=>x.id===id);return <details key={id} className="rounded-md border p-2 mb-2"><summary className="text-xs"><strong>{part?configName(part.config_id):"구성 요소"}</strong> · {part?.status==="SUCCESS"?part.decision:part?.status||"N/A"} · {duration(part?.latency_ms)}</summary><p className="caption break-all mt-2">{id}</p><pre className="text-block mt-2">{json(part)}</pre></details>;})}<Badge variant="outline">{config.kind==="Cascade"?"Jev 최종 판정 · 불일치는 방향으로 표시":"기존 독립 판정 결합 정책"}</Badge></div>}
      <details><summary className="text-xs font-semibold">분석 입력 원본</summary><pre className="text-block mt-2">{json(r.input_text??r.raw_input??r.input??{subject:sample.subject,body:sample.body})}</pre></details>
      <details><summary className="text-xs font-semibold">모델 응답 원본</summary><pre className="text-block mt-2">{json(r.raw_response)}</pre></details>
      <details><summary className="text-xs font-semibold">요청·시도·시간·자원·재현 정보 전체</summary><pre className="text-block mt-2">{json(r)}</pre></details>
    </div>}
  </Panel>;
}
function configName(id:string) {return id==="foundation_sec"?"Foundation-Sec":id==="qwen"?"Qwen":id==="jev"?"Jev":id;}
