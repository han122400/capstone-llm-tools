"use client";
import {useEffect,useState} from "react";
import {api} from "@/lib/api";
import {Config,Statistics} from "@/lib/types";
import {Notice,Button} from "./shared";
import {Overview} from "./overview";

export function AggregateOverview({demo,configs,onStart}:{demo:boolean;configs:Config[];onStart:()=>void}) {
  const [dataset,setDataset]=useState("");
  const [prompt,setPrompt]=useState("");
  const [mode,setMode]=useState("");
  const [data,setData]=useState<Statistics|null>(null);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");
  const [revision,setRevision]=useState(0);
  useEffect(()=>{
    const controller=new AbortController();
    setLoading(true);setError("");
    const params=new URLSearchParams({demo:String(demo),dataset,prompt,mode});
    api<Statistics>(`/statistics?${params}`,{signal:controller.signal})
      .then(value=>{setData(value);setLoading(false);})
      .catch(e=>{if(!controller.signal.aborted){setError(e.message);setLoading(false);}});
    return()=>controller.abort();
  },[demo,dataset,prompt,mode,revision]);
  return <>
    <div className="toolbar">
      <label className="min-w-0 flex-1 basis-56">데이터셋<select aria-label="전체 통계 데이터셋" className="form-control max-w-full" value={dataset} onChange={e=>setDataset(e.target.value)}><option value="">모든 데이터셋·버전</option>{data?.options.datasets.map(d=><option key={d.value} value={d.value}>{d.label}</option>)}</select></label>
      <label className="min-w-0 flex-1 basis-56">프롬프트<select aria-label="전체 통계 프롬프트" className="form-control max-w-full" value={prompt} onChange={e=>setPrompt(e.target.value)}><option value="">모든 프롬프트 버전</option>{data?.options.prompts.map(p=><option key={p}>{p}</option>)}</select></label>
      <label className="min-w-0 flex-1 basis-56">평가 방식<select aria-label="전체 통계 평가 방식" className="form-control max-w-full" value={mode} onChange={e=>setMode(e.target.value)}><option value="">모든 평가 방식</option><option value="reuse">결과 재사용</option><option value="live">실시간 결합</option></select></label>
      <Button variant="outline" onClick={()=>setRevision(x=>x+1)}>통계 새로고침</Button>
    </div>
    {error?<Notice variant="error">{error}</Notice>:loading?<div role="status">전체 통계를 불러오는 중입니다…</div>:data&&<Overview run={null} aggregate={data} demo={demo} configs={configs} onStart={onStart}/>}
  </>;
}
