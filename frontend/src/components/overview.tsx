"use client";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";
import { Database, Mail, Play, Timer } from "lucide-react";
import { Config, Run, Statistics, configsForRun, modeLabel, metricLabels, percent, money, duration, displayDate, json } from "@/lib/types";
import { CascadeComparison } from "./cascade-comparison";
import { Panel, Button, Badge, Status, Empty, Notice } from "./shared";

const summaryColumns=[["correct_rate","정답 비율"],["injection_detection_rate","인젝션 탐지율"],["false_positive_rate","오탐률"],["miss_rate","미탐률"]];
const advancedColumns=[["automatic_rate","자동 판정률"],["precision","정밀도"],["recall","재현율"],["f1","F1"]];
export function Overview({run,aggregate,demo,configs:activeConfigs,onStart}: {run:Run|null;aggregate?:Statistics;demo?:boolean;configs:Config[];onStart:()=>void}) {
  const configs=aggregate ? [...activeConfigs,...(aggregate.config_definitions||[]).filter(c=>!activeConfigs.some(a=>a.id===c.id))] : configsForRun(activeConfigs,run);
  const cascades=configs.filter(c=>c.id.endsWith("_then_jev")||c.id.endsWith("_jev"));
  const metrics=aggregate?.metrics ?? run?.metrics;
  const totals=aggregate?.totals ?? run?.totals;
  const hasData=aggregate ? aggregate.run_count>0 : !!run;
  const unfinished=["PENDING","RUNNING","CANCELLED","SKIPPED"];
  const showIncomplete=Object.values(metrics||{}).some(m=>unfinished.some(s=>m.counts[s]>0));
  const sampleCount=aggregate?.sample_count ?? run?.dataset_snapshot.samples.length;
  const normalCount=aggregate?.class_counts.NORMAL ?? run?.dataset_snapshot.samples.filter(s=>s.label==="NORMAL").length ?? 0;
  const injectionCount=aggregate?.class_counts.INJECTION ?? run?.dataset_snapshot.samples.filter(s=>s.label==="INJECTION").length ?? 0;
  const rateTable=(columns:string[][])=><div className="table-scroll"><table className="data-table"><thead><tr><th>모델 구성</th>{columns.map(([key,label])=><th key={key} className="num">{label}</th>)}</tr></thead><tbody>{configs.map(c=><tr key={c.id}><td className="name">{c.name}</td>{columns.map(([key])=>{const m=metrics?.[c.id]?.metrics[key];return <td key={key} className="num metric-cell">{percent(m?.value)}{m&&<small>{m.numerator} / {m.denominator}</small>}</td>;})}</tr>)}</tbody></table></div>;
  const [detailConfig,setDetailConfig]=useState("foundation_sec");
  const [pair,setPair]=useState("foundation_sec,qwen");
  const compareIds=(pair.split(",").every(id=>configs.some(c=>c.id===id))?pair:"foundation_sec,qwen").split(",");
  const compareConfigs=compareIds.map(id=>configs.find(c=>c.id===id)!);
  const data=configs.map(c=>({name:c.name,id:c.id,
    automatic:metrics?.[c.id]?.metrics?.automatic_rate?.value == null ? null : metrics[c.id].metrics.automatic_rate.value!*100,
    detection:metrics?.[c.id]?.metrics?.injection_detection_rate?.value == null ? null : metrics[c.id].metrics.injection_detection_rate.value!*100,
    review:metrics?.[c.id]?.metrics?.review_rate?.value == null ? null : metrics[c.id].metrics.review_rate.value!*100
  }));
  const selectedMetrics=metrics?.[detailConfig];
  const partial=run && run.status!=="COMPLETED";
  const latencyData=run?.results?.filter(r=>r.latency_ms!=null && !r.is_warmup && !r.component_for && !(r.reused && r.config_id.endsWith("_jev"))).map(r=>({name:configs.find(c=>c.id===r.config_id)?.name||r.config_id,ms:r.latency_ms,status:r.status,sample:r.sample_id}))||[];
  return <>
    {run && <Notice><div className="row between"><div><strong>{run.dataset_snapshot.name}</strong> · v{run.dataset_snapshot.version} · {run.dataset_snapshot.split==="evaluation"?"최종 평가 데이터":"개발 데이터"} · {displayDate(run.started_at||run.created_at)} · {String(run.environment?.prompt_version||"프롬프트 미기록")}<br/>{modeLabel(run)}{run.mode==="reuse"?" · 결합 전체 실측 시간 N/A":""}</div><div className="row">{run.demo && <Badge variant="outline">DEMO</Badge>}<Status value={run.status}/></div></div></Notice>}
    {partial && <Notice variant="warning">이 실험은 부분 결과입니다. 취소·진행 중·서버 중단 결과를 포함하며 완료된 실험과 동일하게 순위화하지 않습니다.</Notice>}
    <div className="three">
      <div className="stat"><div className="stat-icon"><Mail/></div><div><div className="stat-label">{aggregate?"누적 평가 메일 · 반복 평가 포함":"평가 대상 · 데이터셋 스냅샷"}</div><div className="stat-value">{sampleCount ?? "N/A"}<span className="ml-2 text-xs font-normal text-muted-foreground">이메일</span></div></div></div>
      <div className="stat"><div className="stat-icon"><Timer/></div><div><div className="stat-label">{aggregate?"실험 소요 시간 합계":"전체 실험 소요 시간"}</div><div className="stat-value">{duration(totals?.elapsed_ms)}</div></div></div>
      <div className="stat"><div className="stat-icon"><Database/></div><div><div className="stat-label">실제 API 지출{(demo||run?.demo)?" · DEMO 모의값":""}</div><div className="stat-value">{money(totals?.cost_usd)}</div><p className="caption">{hasData ? `${totals?.api_calls??0}회 호출 · 비용 미확인 ${totals?.unknown_cost_calls??0}회` : "응답 비용 기준 · 재사용 중복 제외"}</p></div></div>
    </div>
    {aggregate && <Notice><strong>전체 통계 · 실험 {aggregate.run_count}회</strong><p>누적 평가 {aggregate.sample_count}건 · 정상 {normalCount}건 · 인젝션 {injectionCount}건</p><p className="caption">같은 이메일의 반복 평가도 각각 집계합니다. 구성별 전체 메일 수는 해당 구성을 선택한 실험만 합산합니다. 결합 내부 호출과 워밍업은 판정 건수에서 제외합니다.</p></Notice>}
    {aggregate?.mixed_conditions && <Notice variant="warning">서로 다른 데이터셋·프롬프트·설정·평가 방식이 포함된 누적 통계입니다. 같은 조건을 비교하려면 위 필터를 선택하세요.</Notice>}
    {!!aggregate?.partial_run_count && <Notice variant="warning">미완료 실험 {aggregate.partial_run_count}회가 포함된 부분 결과입니다. 대기·진행 중·취소·미실행을 별도 표시하며 성능 순위를 매기지 않습니다.</Notice>}
    <Panel title="5개 구성 비교" description={hasData?`${aggregate?"누적 평가":"총"} ${sampleCount}건 · 정상 ${normalCount}건 · 인젝션 ${injectionCount}건`:aggregate?"선택한 조건의 평가가 없습니다":"아직 실행된 평가가 없습니다"}>
      <div className="table-scroll"><table className="data-table" aria-label="모델별 판정 건수"><thead><tr><th>모델 구성</th><th className="num">전체 메일</th><th className="num">정상 판정 정답</th><th className="num">인젝션 탐지 정답</th><th className="num">오탐</th><th className="num">미탐</th><th className="num">검토 필요</th><th className="num">실행 오류</th>{showIncomplete&&unfinished.map(s=><th className="num" key={s}>{{PENDING:"대기",RUNNING:"진행 중",CANCELLED:"취소",SKIPPED:"미실행"}[s]}</th>)}</tr></thead><tbody>
        {configs.map(c=>{const m=metrics?.[c.id];const cells=m?[m.N,m.confusion.NORMAL.NORMAL,m.confusion.INJECTION.INJECTION,m.confusion.NORMAL.INJECTION,m.confusion.INJECTION.NORMAL,m.metrics.review_rate.numerator,m.counts.ERROR,...(showIncomplete?unfinished.map(s=>m.counts[s]):[])]:Array(7+(showIncomplete?4:0)).fill(null);return <tr key={c.id}><td className="name"><div className="row gap-2"><span>{c.name}</span><Badge variant="secondary">{c.kind}</Badge></div></td>{cells.map((value,i)=><td className="num" key={i}>{value==null?"—":`${value}건`}</td>)}</tr>;})}
      </tbody></table></div>
      <p className="caption mt-3">오탐: 정상을 인젝션으로 판단 · 미탐: 인젝션을 정상으로 판단 · 검토 필요: 판단 보류 · 실행 오류: 호출 또는 응답 처리 실패</p>
      <p className="caption">실행이 성공해도 오답일 수 있습니다. 검토 필요는 정답이나 실행 오류에 포함하지 않습니다. — = 해당 구성 미평가</p>
    </Panel>
    {hasData && <Panel title="성능 요약" description="정답 비율은 전체 메일, 탐지율·미탐률은 실제 인젝션, 오탐률은 실제 정상 메일 기준입니다.">{rateTable(summaryColumns)}<details className="subsection"><summary className="font-semibold">상세 지표 펼치기 · 자동 판정률, 정밀도, 재현율, F1</summary>{rateTable(advancedColumns)}<p className="caption mt-3">정밀도: 인젝션 판정 중 정답 비율 · 재현율: 자동 판정한 실제 인젝션 중 탐지 비율 · F1: 정밀도와 재현율의 조화평균. 검토 필요·실행 오류를 제외하므로 자동 판정률과 함께 확인하세요. 분모가 0이면 N/A입니다.</p></details></Panel>}
    {hasData && <Panel title="처리 시간과 비용" description="시간은 판정 정답 여부와 관계없이 응답 처리에 성공한 요청 기준입니다. 재사용 결합 전체 실측 시간은 N/A입니다."><div className="table-scroll"><table className="data-table"><thead><tr><th>모델 구성</th><th>평균 처리 시간</th><th>최대 처리 시간</th><th>실제 추가 API 비용</th></tr></thead><tbody>{configs.map(c=>{const m=metrics?.[c.id];return <tr key={c.id}><td>{c.name}</td><td>{duration(m?.latency?.success?.mean_ms)}</td><td>{duration(m?.latency?.success?.max_ms)}</td><td>{money(m?.cost?.actual_usd)}{!!m?.cost?.unknown_calls&&<small className="caption block">비용 미확인 {m.cost.unknown_calls}회</small>}</td></tr>;})}</tbody></table></div><p className="caption mt-3">비용은 확인된 응답 비용 소계이며 재사용 비용은 중복 합산하지 않습니다. DEMO 값은 실제 지출이 아닙니다.</p></Panel>}
    <CascadeComparison diagnostics={aggregate?.cascade_diagnostics??run?.cascade_diagnostics} configs={configs}/>
    {run && <Panel title="단독 모델과 결합 구성 비교" description="동일한 지표를 함께 확인하세요. 검토 필요 증가와 정답 개선은 구분합니다. 2단계의 최종 판정은 Jev가 결정합니다." action={<select aria-label="구성 비교 쌍" className="form-control w-auto max-w-full" value={compareIds.join(",")} onChange={e=>setPair(e.target.value)}>
      <option value="foundation_sec,qwen">Foundation-Sec ↔ Qwen</option>{cascades.flatMap(c=>[<option key={c.id} value={`${c.components?.[0]},${c.id}`}>{c.components?.[0]==="qwen"?"Qwen":"Foundation-Sec"} ↔ {c.name}</option>,<option key={`jev-${c.id}`} value={`jev,${c.id}`}>Jev ↔ {c.name}</option>])}{cascades.length===2&&<option value={cascades.map(c=>c.id).join(",")}>두 구성 비교</option>}
    </select>}><div className="table-scroll"><table className="data-table"><thead><tr><th>비교 항목</th>{compareConfigs.map(c=><th key={c.id}>{c.name}</th>)}</tr></thead><tbody>{["injection_detection_rate","automatic_rate","review_rate","error_rate","miss_rate","false_positive_rate","f1"].map(key=><tr key={key}><td>{metricLabels[key]}</td>{compareIds.map(id=>{const m=metrics?.[id]?.metrics?.[key];return <td className="metric-cell" key={id}>{percent(m?.value)}{m&&<small>{m.numerator}/{m.denominator}</small>}</td>;})}</tr>)}<tr><td>실행 성공 요청 평균 시간</td>{compareIds.map(id=><td key={id}>{duration(metrics?.[id]?.latency?.success?.mean_ms)}</td>)}</tr><tr><td>실제 추가 API 지출</td>{compareIds.map(id=><td key={id}>{money(metrics?.[id]?.cost?.actual_usd)}</td>)}</tr></tbody></table></div><p className="caption mt-3">2단계 평가는 로컬 1차를 재사용해도 Jev 2차를 새로 호출합니다. 기존 독립 결합 기록은 원래 재사용 정책을 유지합니다. 비용은 실제 신규 호출 기준입니다.</p></Panel>}
    <div className={aggregate?"":"split"}>
      <Panel title="탐지 성능과 자동 판정률" description="탐지율과 판정 유보의 변화를 함께 비교합니다.">
        {hasData ? <div className="chart" aria-label="구성별 자동 판정률, 탐지율, REVIEW 비율 막대그래프"><ResponsiveContainer width="100%" height="100%"><BarChart data={data} margin={{left:-18,right:10,bottom:16}}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0"/><XAxis dataKey="name" tick={{fontSize:10}} interval={0} angle={-10} height={44}/><YAxis domain={[0,100]} tick={{fontSize:11}} tickFormatter={v=>`${v}%`}/><Tooltip formatter={(v)=>`${Number(v).toFixed(1)}%`}/><Legend wrapperStyle={{fontSize:11}}/>
          <Bar name="자동 판정률" dataKey="automatic" fill="#4338ca" radius={[3,3,0,0]} isAnimationActive={false}/><Bar name="인젝션 자동 탐지율" dataKey="detection" fill="#0f766e" radius={[3,3,0,0]} isAnimationActive={false}/><Bar name="REVIEW 비율" dataKey="review" fill="#c79840" radius={[3,3,0,0]} isAnimationActive={false}/>
        </BarChart></ResponsiveContainer></div> : <div className="chart-empty"><strong>아직 실행된 평가가 없습니다</strong><span>평가를 실행하면 실제 측정값을 표시합니다.</span></div>}
      </Panel>
      {!aggregate && <Panel title="샘플별 요청 처리 시간" description="재시도를 포함한 누적 지연 · 결합 재사용 전체 지연은 N/A">
        {latencyData.length ? <div className="chart" aria-label="샘플별 성공 실패 요청 시간 분포"><ResponsiveContainer width="100%" height="100%"><ScatterChart margin={{left:-8,right:10,bottom:12}}><CartesianGrid strokeDasharray="3 3" vertical={false}/><XAxis type="category" dataKey="name" allowDuplicatedCategory={false} tick={{fontSize:10}} interval={0}/><YAxis type="number" dataKey="ms" name="처리 시간" unit="ms" tick={{fontSize:10}}/><ZAxis range={[34,34]}/><Tooltip cursor={{strokeDasharray:"3 3"}}/><Legend wrapperStyle={{fontSize:11}}/><Scatter name="실행 성공" data={latencyData.filter(r=>r.status==="SUCCESS")} fill="#4338ca" isAnimationActive={false}/><Scatter name="실행 오류" data={latencyData.filter(r=>r.status==="ERROR")} fill="#b4233c" isAnimationActive={false}/></ScatterChart></ResponsiveContainer></div> : <div className="chart-empty"><strong>측정된 요청 시간이 없습니다</strong><span>성공과 실패 요청을 구분해 표시합니다.</span></div>}
      </Panel>}
    </div>
    {hasData && <Panel title="측정 세부 정보" description="구성별 지표 정의와 실행 상태를 확인합니다." action={<select aria-label="지표 상세 구성" className="form-control w-auto" value={detailConfig} onChange={e=>setDetailConfig(e.target.value)}>{configs.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select>}>
      {selectedMetrics ? <>
        <div className="row mb-4">{Object.entries(selectedMetrics.counts||{}).map(([s,n])=><span className="row gap-1" key={s}>{s==="SUCCESS"?"실행 성공":s==="ERROR"?"실행 오류":<Status value={s}/>}<strong>{n}</strong></span>)}</div>
        <div className="table-scroll"><table className="data-table"><thead><tr><th>요청 상태</th><th>표본 수</th><th>평균</th><th>중앙값</th><th>P95</th></tr></thead><tbody>{(["success","error"] as const).map(status=><tr key={status}><td>{status==="success"?"실행 성공":"실행 오류"}</td><td>{selectedMetrics.latency?.[status]?.count??"N/A"}</td><td>{duration(selectedMetrics.latency?.[status]?.mean_ms)}</td><td>{duration(selectedMetrics.latency?.[status]?.median_ms)}</td><td>{duration(selectedMetrics.latency?.[status]?.p95_ms)}</td></tr>)}</tbody></table></div>
        <p className="caption mt-2">소표본의 P95는 안정적인 대표 성능으로 해석하지 않습니다. 로컬 cold/warm 상태를 외부 Jev 서버에 적용하지 않습니다.</p>
        <div className="subsection"><h3>정답 × 유효한 판정 혼동행렬</h3><div className="table-scroll"><table className="data-table mt-2"><thead><tr><th>실제 정답</th><th>NORMAL</th><th>INJECTION</th><th>REVIEW</th></tr></thead><tbody>{["NORMAL","INJECTION"].map(label=><tr key={label}><td>{label}</td>{["NORMAL","INJECTION","REVIEW"].map(d=><td key={d}>{selectedMetrics.confusion?.[label]?.[d]??0}</td>)}</tr>)}</tbody></table></div><p className="caption mt-2">ERROR, CANCELLED, SKIPPED, PENDING, RUNNING은 위 혼동행렬에서 제외하고 실행 상태로 별도 집계합니다.</p></div>
        <details className="subsection"><summary className="font-semibold">모든 지표의 분자·분모와 계산 설명</summary><div className="mt-3">{Object.entries(selectedMetrics.metrics).map(([key,m])=><div className="metric-definition" key={key}><div><strong>{metricLabels[key]||key}</strong>{percent(m.value)} · {m.numerator}/{m.denominator}</div><p>{m.description}</p></div>)}</div><p className="caption mt-4">자동 판정 Recall의 분모는 TP+FN입니다. 전체 인젝션 자동 탐지율은 실제 인젝션 전체를 분모로 사용하여 REVIEW와 실패도 포함합니다.</p></details>
      </> : <Empty title="선택한 구성의 평가 결과가 없습니다"/>}
    </Panel>}
    {run && <Panel title="비용과 로컬 자원 비교" description="수집 가능한 피크 값 · 시스템 RAM, 백엔드 RAM, Ollama runner RAM을 구분합니다."><div className="table-scroll"><table className="data-table"><thead><tr><th>구성</th><th>실제 추가 API 지출</th><th>API 호출</th><th>시스템 RAM 피크</th><th>백엔드 RSS 피크</th><th>Ollama RSS 피크</th><th>GPU / 공유 메모리</th></tr></thead><tbody>{configs.map(c=>{const m=metrics?.[c.id];const res=m?.resources;const bytes=(key:string)=>typeof res?.[key]==="number"?`${(Number(res[key])/1024/1024).toFixed(1)} MiB`:"N/A";return <tr key={c.id}><td className="name">{c.name}</td><td>{money(m?.cost?.actual_usd)}{m?.cost?.unknown_calls?<span className="caption block">비용 미확인 {m.cost.unknown_calls}회</span>:null}</td><td>{m?.cost?.api_calls??"N/A"}</td><td>{bytes("system_ram_used_peak_bytes")}</td><td>{bytes("backend_rss_peak_bytes")}</td><td>{bytes("ollama_rss_peak_bytes")}</td><td>{bytes("gpu_memory_peak_bytes")} / {bytes("shared_gpu_memory_peak_bytes")}</td></tr>;})}</tbody></table></div><p className="caption mt-3">Jev 서버 RAM / GPU는 N/A입니다. PC 클라이언트 메모리는 외부 모델 메모리가 아닙니다. 공유 메모리를 RAM과 합산하지 않습니다. 로컬 API 청구액과 하드웨어·전력 비용은 다릅니다.</p></Panel>}
    {run && <Panel title="실행 조건 및 재현성" description="서로 다른 모델 설정은 속도 비교 시 함께 확인합니다."><details><summary className="text-xs font-semibold">환경 · 추론 설정 · 모델 정보</summary><pre className="text-block mt-3">{json({environment:run.environment,settings:run.settings,events:run.events,mode:run.mode})}</pre></details><p className="caption mt-3">재사용 결합의 실제 모델 처리 시간과 결합 계산 시간은 사례에서 구분합니다. 새로운 운영 호출의 예상 비용을 실험의 실제 지출로 표시하지 않습니다.</p></Panel>}
    {!hasData && <Notice><div className="row between"><div><strong>평가를 시작할 준비가 되면</strong><p>데이터셋을 등록하고 설치 모델 및 API 연결을 확인하세요. 실제 측정 전에는 성능 수치를 채우지 않습니다.</p></div><Button variant="outline" onClick={onStart}><Play/>첫 평가 준비</Button></div></Notice>}
  </>;
}
