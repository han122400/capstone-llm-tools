"use client";
import { json } from "@/lib/types";
import { Badge, Notice, Panel } from "./shared";

export type ClassificationPrompt = {
  version: string;
  cascade_question_version?:string; cascade_policy_version?:string; jev_review_question?:unknown;
  instructions: string;
  criteria: Record<"NORMAL" | "INJECTION" | "REVIEW", string>;
  local_system_prompt: string;
  jev_question: { type: string; instructions: string; criteria: Record<string, string> };
};

const decisions = [
  ["NORMAL", "인젝션 미탐지"],
  ["INJECTION", "인젝션 위험"],
  ["REVIEW", "검토 필요"],
] as const;

export function PromptViewer({ prompt }: { prompt?: ClassificationPrompt }) {
  return <Panel title="모델 판정 프롬프트" description="현재 백엔드에서 사용하는 기본 판정 프롬프트 원문입니다. 조회 전용이며 영어 원문 그대로 표시합니다.">
    <div className="row mb-3"><span className="text-xs font-semibold">프롬프트 버전</span><Badge variant="outline">{prompt?.version || "N/A"}</Badge></div>
    {!prompt ? <Notice variant="warning">프롬프트 정보를 불러오지 못했습니다. 백엔드를 최신 코드로 재시작한 뒤 화면을 새로고침해 주세요.</Notice> : <>
      <p className="caption">Foundation-Sec와 Qwen은 같은 시스템 프롬프트를 사용합니다. Jev에는 같은 지시와 기준을 Decisions 질문으로 전달합니다. 이메일 내용은 별도의 입력이며 아래 원문에 포함되지 않습니다.</p>
      <details className="subsection" open>
        <summary className="font-semibold">공통 지시문 · CLASSIFICATION_INSTRUCTIONS</summary>
        <pre className="text-block mt-3" data-testid="prompt-instructions">{prompt.instructions}</pre>
      </details>
      <details className="subsection" open>
        <summary className="font-semibold">판정 기준 · CRITERIA</summary>
        <div className="stack mt-3">{decisions.map(([decision, label]) => <div key={decision}>
          <h3 className="text-xs font-semibold">{decision} · {label}</h3>
          <pre className="text-block mt-2" data-testid={`prompt-criterion-${decision}`}>{prompt.criteria[decision]}</pre>
        </div>)}</div>
      </details>
      <details className="subsection">
        <summary className="font-semibold">Foundation-Sec / Qwen 시스템 프롬프트 전체</summary>
        <pre className="text-block mt-3" data-testid="prompt-local">{prompt.local_system_prompt}</pre>
      </details>
      <details className="subsection">
        <summary className="font-semibold">Jev Decisions 질문 원문</summary>
        <pre className="text-block mt-3" data-testid="prompt-jev">{json(prompt.jev_question)}</pre>
      </details>
      {prompt.jev_review_question!=null&&<details className="subsection"><summary className="font-semibold">로컬 → Jev 2차 검증 질문 · {prompt.cascade_question_version}</summary><pre className="text-block mt-3" data-testid="prompt-jev-review">{json(prompt.jev_review_question)}</pre><p className="caption">최종 정책: {prompt.cascade_policy_version} · 원본 이메일과 로컬 choice를 전달하고 Jev가 최종 판정합니다.</p></details>}
      <p className="caption mt-4">여기에 표시된 내용은 현재 코드의 기본 판정 요청 기준입니다. Ollama의 기존 Modelfile·템플릿 및 추가 설명 요청은 별도로 적용될 수 있습니다. 과거 실험은 실행 당시 저장된 프롬프트와 모델 메타데이터를 기준으로 확인하세요.</p>
    </>}
  </Panel>;
}
