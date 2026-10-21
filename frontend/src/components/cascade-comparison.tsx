"use client";
import {CascadeDiagnostic,Config,Result,decisionName} from '@/lib/types';
import {Badge,Panel} from './shared';

export function DecisionTransition({result:r}:{result:Result}) {
  if(!r.config_id.endsWith('_then_jev'))return null;
  return <div className="mt-2 text-xs whitespace-normal min-w-40">
    <strong>로컬 {decisionName(r.local_decision)} → Jev {decisionName(r.jev_decision)}</strong>
    <div className="mt-1"><Badge variant="outline">{r.status!=='SUCCESS'?'단계 미완료':r.decision_changed?'판정 변경':'판정 유지'}</Badge></div>
    <span className="caption">최종: {r.status==='SUCCESS'?decisionName(r.decision):'판정 없음 · '+r.status}</span>
  </div>;
}

export function CascadeComparison({diagnostics,configs}:{diagnostics?:Record<string,CascadeDiagnostic>;configs:Config[]}) {
  const entries=Object.entries(diagnostics||{});
  if(!entries.length)return null;
  const name=(id:string)=>configs.find(c=>c.id===id)?.name||id;
  const fields=[['compared','비교 가능'],['improved','오답 → 정답'],['worsened','정답 → 오답'],['correct_to_review','정답 → 검토 필요'],['review_to_correct','검토 필요 → 정답'],['final_review','최종 검토 필요'],['unavailable','비교 불가']];
  return <>
    <Panel title="2단계 판정 변경" description="로컬 1차 판정과 Jev 2차 판정의 차이입니다. 불일치만으로 검토 필요가 되지 않으며 Jev가 최종 판정합니다.">
      {entries.map(([id,d])=><div className="subsection" key={id}><h3>{name(id)} · 판정 변경 {d.changed}건 / 두 단계 성공 {d.compared}건</h3><p className="caption">전체 {d.N}건 · 단계 미완료 {d.unavailable}건. 판정 변경이 곧 정답 개선을 뜻하지는 않습니다.</p><div className="table-scroll"><table className="data-table" aria-label={`${name(id)} 판정 변경 방향`}><thead><tr><th>로컬 1차 → Jev 최종</th>{['NORMAL','INJECTION','REVIEW'].map(v=><th key={v}>{decisionName(v)}</th>)}</tr></thead><tbody>{['NORMAL','INJECTION','REVIEW'].map(a=><tr key={a}><th>{decisionName(a)}</th>{['NORMAL','INJECTION','REVIEW'].map(b=><td key={b}><span>{d.transitions[a]?.[b]??0}건</span><small className="caption block">{decisionName(a)} → {decisionName(b)}</small></td>)}</tr>)}</tbody></table></div></div>)}
    </Panel>
    <Panel title="Jev 단독 대비 개선·악화" description="같은 실험·동일 이메일 입력에서 Jev 단독과 2단계 최종 판정이 모두 성공한 사례를 비교합니다.">
      <div className="table-scroll"><table className="data-table" aria-label="Jev 단독 대비 판정 변화"><thead><tr><th>구성</th>{fields.map(([key,label])=><th key={key}>{label}</th>)}</tr></thead><tbody>{entries.map(([id,d])=><tr key={id}><td>{name(id)}</td>{fields.map(([key])=><td key={key}>{!d.baseline.compared&&!['compared','unavailable'].includes(key)?'N/A':`${d.baseline[key]}건`}</td>)}</tr>)}</tbody></table></div>
      <p className="caption mt-3">Jev 단독 미선택·실패·입력 불일치 또는 2단계 미완료는 비교 불가입니다. 검토 필요는 오답이나 탐지 성공으로 묶지 않습니다. 추가 시간과 비용은 구성별 처리 시간·비용 표에서 함께 확인하세요.</p>
    </Panel>
  </>;
}
