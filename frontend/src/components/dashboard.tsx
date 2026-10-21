"use client";
import { useCallback, useEffect, useState } from "react";
import { Activity, Database, FileSearch, LayoutGrid, Play, Settings2, ShieldCheck, X, RefreshCw, Download as DownloadIcon } from "lucide-react";
import { api } from "@/lib/api";
import { CONFIGS, Config, Dataset, Run, displayDate } from "@/lib/types";
import { Button, Badge, Notice, Download } from "./shared";
import { Overview } from "./overview";
import { AggregateOverview } from "./aggregate-overview";
import { Datasets } from "./datasets";
import { RunManager } from "./run-manager";
import { Cases } from "./cases";
import { Settings } from "./settings";
import { ToggleGroup, ToggleGroupItem } from "./ui/toggle-group";

type Tab = "overview" | "datasets" | "runs" | "cases" | "settings";
const nav = [
  {id:"overview",label:"개요 및 비교",icon:LayoutGrid,title:"모델 비교 대시보드",description:"동일한 이메일 · 단독 평가와 로컬 → Jev 2단계 검증"},
  {id:"datasets",label:"데이터셋",icon:Database,title:"이메일 데이터셋",description:"합성 이메일과 정답을 관리하고 버전별 평가 스냅샷을 보존합니다."},
  {id:"runs",label:"평가 실행",icon:Play,title:"평가 실행 및 이력",description:"연결 상태와 실행 조건을 확인한 후 5개 구성을 평가합니다."},
  {id:"cases",label:"사례 비교",icon:FileSearch,title:"이메일별 판정 비교",description:"같은 입력의 원본 판정과 결합 결과를 나란히 확인합니다."},
  {id:"settings",label:"설정",icon:Settings2,title:"실행 환경 및 설정",description:"실제 설치 모델, 추론 파라미터, 판정 정책을 확인합니다."}
] as const;
export function Dashboard() {
  const [scope,setScope]=useState("experiment");
  const [tab,setTab]=useState<Tab>("overview");
  const [demo,setDemo]=useState(false);
  const [configs,setConfigs]=useState<Config[]>(CONFIGS);
  const [datasets,setDatasets]=useState<Dataset[]>([]);
  const [runs,setRuns]=useState<Run[]>([]);
  const [runId,setRunId]=useState("");
  const [run,setRun]=useState<Run|null>(null);
  const [settings,setSettings]=useState<Record<string,unknown>>({});
  const [loading,setLoading]=useState(true);
  const [loadError,setLoadError]=useState("");
  const [toast,setToast]=useState<{message:string;error?:boolean}|null>(null);
  const notify=useCallback((message:string,error=false)=>setToast({message,error}),[]);
  const navigate=(next:Tab)=>{setTab(next);window.location.hash=next;};
  const selectRun=useCallback((id:string)=>{
    setRunId(id);const url=new URL(window.location.href);if(id)url.searchParams.set("run",id);else url.searchParams.delete("run");window.history.replaceState({},"",url);
  },[]);
  const refresh=useCallback(async()=>{
    try {
      const [ds,rs,ss,cc]=await Promise.all([api<Dataset[]>("/datasets"),api<Run[]>(`/runs?demo=${demo}`),api<Record<string,unknown>>("/settings"),api<Config[]>("/configs")]);
      setDatasets(ds);setRuns(rs);setSettings(ss);setConfigs(cc);setLoadError("");
    }catch(e){setLoadError((e as Error).message);}finally{setLoading(false);}
  },[demo]);
  useEffect(()=>{
    const search=new URLSearchParams(window.location.search);setDemo(search.get("demo")==="true");setRunId(search.get("run")||"");
    const next=window.location.hash.slice(1);if(nav.some(x=>x.id===next))setTab(next as Tab);
  },[]);
  useEffect(()=>{void refresh();},[refresh]);
  useEffect(()=>{
    if(!runId){setRun(null);return;}
    let alive=true;let timer:ReturnType<typeof setTimeout>;
    const poll=async()=>{
      try{const r=await api<Run>(`/runs/${runId}`);if(!alive)return;
        if(r.demo!==demo){setRun(null);return;}
        setRun(r);if(["PENDING","RUNNING"].includes(r.status))timer=setTimeout(poll,1000);
        else void refresh();
      }catch(e){if(alive){notify((e as Error).message,true);setRun(null);}}
    };void poll();return()=>{alive=false;clearTimeout(timer);};
  },[runId,demo,notify,refresh]);
  useEffect(()=>{if(!runId && runs[0]?.demo===demo)selectRun(runs[0].id);},[runId,runs,demo,selectRun]);
  useEffect(()=>{if(!toast)return;const timer=setTimeout(()=>setToast(null),7000);return()=>clearTimeout(timer);},[toast]);
  const switchDemo=(value:boolean)=>{
    setDemo(value);setRun(null);setRuns([]);selectRun("");const url=new URL(window.location.href);url.searchParams.set("demo",String(value));window.history.replaceState({},"",url);
  };
  const selected=nav.find(x=>x.id===tab)!;
  const onCreated=(r:Run)=>{setDemo(r.demo);selectRun(r.id);setRun(r);void refresh();};
  return <div className="app-shell">
    <aside className="sidebar"><div className="brand"><ShieldCheck strokeWidth={1.8}/><div><strong>메일 가드 랩</strong><span>모델 비교 실험실</span></div></div>
      <nav className="navigation" aria-label="주 탐색">{nav.map(item=><button key={item.id} aria-current={tab===item.id?"page":undefined} onClick={()=>navigate(item.id)}><item.icon/>{item.label}</button>)}</nav>
      <div className="sidebar-foot"><strong>● 로컬 전용</strong>연구용 탐지기 분류 평가<br/>메일 작업 및 공격 실행 없음</div>
    </aside>
    <main className="main"><header className="page-header"><div><h1>{selected.title}</h1><p>{selected.description}</p></div><Button onClick={()=>navigate("runs")}><Play data-icon="inline-start"/>평가 실행</Button></header>
      <div className="stack">
        {loadError && <Notice variant="error"><div className="row between"><span>{loadError}</span><Button variant="outline" size="sm" onClick={()=>void refresh()}><RefreshCw/>다시 연결</Button></div></Notice>}
        {tab!=="datasets" && tab!=="settings" && <div className="toolbar">
          <ToggleGroup type="single" value={demo?"demo":"actual"} onValueChange={value=>{if(value)switchDemo(value==="demo");}} size="sm" variant="outline" aria-label="평가 데이터 구분"><ToggleGroupItem value="actual">실제 평가</ToggleGroupItem><ToggleGroupItem value="demo">DEMO</ToggleGroupItem></ToggleGroup>
          {tab==="overview" && <ToggleGroup type="single" value={scope} onValueChange={v=>{if(v)setScope(v);}} variant="outline" aria-label="통계 범위"><ToggleGroupItem value="experiment">실험별 통계</ToggleGroupItem><ToggleGroupItem value="all">전체 통계</ToggleGroupItem></ToggleGroup>}
          {(tab!=="overview" || scope==="experiment") && <select aria-label="실험 선택" className="form-control" value={runId} onChange={e=>selectRun(e.target.value)}><option value="">실험을 선택하세요</option>{runs.map(r=><option key={r.id} value={r.id}>{r.demo?"[DEMO] ":""}{displayDate(r.started_at||r.created_at)} (KST) · {r.dataset_snapshot?.name||"실험"} · {r.id.slice(0,8)} · {r.status}</option>)}</select>}
          {run && (tab!=="overview" || scope==="experiment") && <><Download href={`/api/runs/${run.id}/export?format=json`}><DownloadIcon/>JSON</Download><Download href={`/api/runs/${run.id}/export?format=csv`}>CSV</Download></>}
          {demo && <Badge variant="outline">DEMO · 가짜 모델 응답</Badge>}
        </div>}
        {loading ? <div role="status" className="rounded-lg border bg-white p-8 text-muted-foreground"><Activity className="mb-2 size-5"/>로컬 저장 데이터를 불러오는 중입니다…</div> : <>
          {tab==="overview" && (scope==="all"?<AggregateOverview key={String(demo)} demo={demo} configs={configs} onStart={()=>navigate("runs")}/>:<Overview run={run} configs={configs} onStart={()=>navigate("runs")}/>)}
          {tab==="datasets" && <Datasets datasets={datasets} onRefresh={refresh} notify={notify}/>}
          {tab==="runs" && <RunManager datasets={datasets} configs={configs} runs={runs} run={run} demo={demo} settings={settings} onCreated={onCreated} onSelect={selectRun} onRefresh={refresh} notify={notify}/>}
          {tab==="cases" && <Cases run={run} configs={configs}/>}
          {tab==="settings" && <Settings settings={settings} onRefresh={refresh} notify={notify}/>}
        </>}
      </div>
      <footer className="mt-6 text-[11px] text-muted-foreground">NORMAL은 프롬프트 인젝션이 아닌 판정입니다. 이메일의 모든 보안 위험이 없다는 의미는 아닙니다. · 측정값이 없으면 N/A · 합성 이메일 분류 평가</footer>
    </main>
    {toast && <div role="alert" className={`alert-message ${toast.error?"error":""}`}><span>{toast.message}</span><button className="close-button" aria-label="알림 닫기" onClick={()=>setToast(null)}><X className="size-4"/></button></div>}
  </div>;
}
