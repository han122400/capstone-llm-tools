"use client";
import {Sample,Dataset,json} from "@/lib/types";
import {Badge,Notice} from "./shared";

export const sourceId=(sample:Sample)=>sample.source_dataset||"미기록";
export function SourceBadge({sample}:{sample:Sample}) {
  return <Badge variant="outline">출처: {sourceId(sample)}</Badge>;
}
export function DatasetScope({dataset}:{dataset:Dataset}) {
  if(!dataset.manifest?.single_source)return null;
  return <Notice variant="warning"><strong>단일 출처 평가</strong> · 영어 합성 이메일의 본문 분류입니다. 원본 사용자 작업은 평가 메타데이터로 보존되며 모델에 전달하지 않습니다. 원본의 공격 정의는 승인·정책을 꾸며내는 문맥 조작을 포함합니다. Gmail 수집·첨부 분석·에이전트 차단 성능으로 해석하지 마세요.{dataset.manifest.license===null&&" 원본 라이선스: 미확인."}</Notice>;
}
export function SourceDetails({sample}:{sample:Sample}) {
  return <div className="stack gap-3"><div className="row"><SourceBadge sample={sample}/>{sample.email&&<Badge variant="outline">본문 범위 평가</Badge>}<Badge variant="outline">합성: {sample.synthetic==null?"미확인":sample.synthetic?"예":"아니요"}</Badge></div>
    {sample.email&&<Notice>입력: {sample.email.kind==="body_only"?"원본 본문만 있음 · Gmail/MIME 미검증":"팀 Gmail 파싱 응답"} · 수집 경고: {sample.email.content.warnings==null?"미확인":sample.email.content.warnings.join(", ")||"없음"} · 수집 잘림: {sample.email.content.truncated==null?"미확인":sample.email.content.truncated?"있음":"없음"} · 첨부 내용 분석: 미실시</Notice>}
    <details><summary className="text-xs font-semibold">출처·변환·공통 이메일 메타데이터</summary><pre className="text-block mt-2">{json({source_dataset:sample.source_dataset??null,source_dataset_name:sample.source_dataset_name??null,source_url:sample.source_url??null,source_version:sample.source_version??null,source_sample_id:sample.source_sample_id??null,source_file:sample.source_file??null,source_file_hash:sample.source_file_hash??null,source_data_version:sample.source_data_version??null,source_download_url:sample.source_download_url??null,source_record_index:sample.source_record_index??null,source_line:sample.source_line??null,pair_id:sample.pair_id??null,template_family:sample.template_family??null,transformation_version:sample.transformation_version??null,transformation_notes:sample.transformation_notes??null,original_body_hash:sample.body_hash??null,body_hash_method:sample.body_hash_method??null,source_context:sample.source_context??null,email:sample.email??null})}</pre></details>
  </div>;
}
