# Local → Jev Implementation Plan

**Goal:** 새 평가의 기존 독립 결합을 Foundation-Sec → Jev, Qwen → Jev로 교체하고 판정 변경 방향을 표시한다.
**Architecture:** 기존 SQLite 스냅샷·단일 큐를 유지한다. 새로운 구성 ID와 질문/정책 버전을 사용하며 과거 독립 결합은 조회 전용으로 보존한다.
**Tech Stack:** FastAPI / SQLite / Next.js / Pytest / Playwright.
**Spec:** 2026-10-13 사용자 승인: 로컬 원문 판정 후 원문+판정을 Jev에 전달, Jev 최종 판정, 불일치 방향 표시.

## Constraints and decisions
- 새 구성: foundation_sec_then_jev, qwen_then_jev. 기존 foundation_sec_jev/qwen_jev는 새 API 선택에서 제외하고 이력 조회와 기존 정책을 보존한다.
- Jev에는 공통 이메일 입력과 검증된 로컬 decision만 전달한다. 정답·출처·샘플 ID·메모·내부 추론·임의 생성 근거는 전달하지 않는다.
- Jev choice가 최종 결과다. 불일치 자체는 REVIEW 사유가 아니다. 로컬 실패 시 Jev 호출을 생략하고 ERROR/null을 보존한다.
- reuse: 같은 실험 로컬 결과만 재사용, 두 구성의 Jev는 각각 새로 호출. 전체 결합 지연 N/A, 단계별 시간 표시.
- live: 로컬 → Jev 전체 직접 측정. 로컬 동시 실행 1, 모델별 해제 확인 유지.
- 실제/DEMO 분리, 유료 추론 금지, 커밋·푸시·별도 worktree 없음. 사용자 요청에 따라 계획 작성 후 이 세션에서 직접 구현한다.

## Tasks
- [x] 1. 계약·질문·테스트: core.py, prompts.py, cascade.py 및 test_cascade.py. 새 5개 선택, 전이 9조합, ERROR/취소, 메타데이터 차단 테스트를 먼저 실행한다.
- [x] 2. 실행·저장: adapters.py의 predict_with_prior(text, decision), engine.py의 두 모드 순차 실행, store.py의 구성 스냅샷/진단 집계. Jev 신규 호출 수·비용·해시·원본·시간·취소·로컬 해제 테스트.
- [x] 3. API·누적 통계: main.py, schemas.py, statistics.py. 새 선택/과거 조회 분리, 오래된 결합 재실행은 명시적으로 차단. Jev 단독 대비 정답 개선/악화는 동일 실험·동일 입력의 성공한 결과끼리 계산하고 불가 건수를 표시한다.
- [x] 4. UI: types.ts, dashboard.tsx, overview.tsx, cases.tsx, run-manager.tsx. 새 이름·모드 설명, 로컬 → Jev 전이 배지·불일치 필터·9방향 요약, 기준선 개선/악화/검토 필요 집계. 과거 기록은 기존 구성/정책 이름으로 표시.
- [x] 5. 검증·문서: Pytest 전체, 타입 검사·빌드, Playwright mock. 실제 평가 시작 없이 기존 3001/8001 서버는 유휴 상태에서만 새 코드 반영. README와 검증 결과 기록.

## Review focus
- 같은 local decision이어도 서로 다른 구성의 Jev 호출을 합치지 않는다.
- 미완료/ERROR를 판정 불일치 또는 정확도 개선으로 집계하지 않는다.
- 실제 모델 입력 해시와 원본 이메일 입력 해시를 분리한다.
- 과거 구성의 지표를 새 2단계 지표와 같은 행에 합치지 않는다.
- Jev 단독 미선택/실패 시 비교는 N/A이며 새로운 기준선 평가를 자동 실행하지 않는다.

## Verification
`backend: ../.venv/Scripts/python.exe -m pytest -q`
`frontend: npm.cmd run typecheck; npm.cmd run build; npm.cmd run test:e2e`
OpenRouter Decisions 문서 재확인 2026-10-13: https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request (state + choice instructions/criteria; 기존 인증·응답 스키마 유지).

완료 기록: Pytest 121 passed (11.12s), 타입 검사 성공, Next 프로덕션 빌드 성공, Playwright 13 passed (50.3s). 브라우저 테스트는 mock/격리 저장소만 사용했다. 초기 실패는 기존 Jev 호출 수 기대값·숨겨진 option 선택·동일 URL hash 이동으로 인한 테스트 미새로고침·DEMO 실제 API 호출 수 기대값을 수정한 뒤 해소했다.

실서비스 GET 전용 검증: 실제 실험 4개 유지, 실행 중 0개, 기존 독립 결합 이력 조회와 새 두 구성 선택 확인, 브라우저 오류 0개. 실제 모델/유료 API 추론은 수행하지 않았다. 검증된 로컬 빌드는 `.next-cascade-build`에 분리하고 3001/8001의 유휴 서버에 반영했다. 코드 커밋·푸시 없음.
