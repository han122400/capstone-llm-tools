# 공개 데이터/Gmail 입력 QA — 2026-10-12

## 실제 실행 결과

| 검사 | 결과 | 확인 범위 |
|---|---|---|
| `python -m pytest backend/tests -q` | 88 passed, 11.12s | 기존 5개 구성/결합/오류/비용 + 새 입력 계약/HTML/누락/메타데이터 차단/CSV/스냅샷/선정 테스트 |
| `npm run typecheck` | PASS | TypeScript 전체 |
| `npm run build` | PASS | Next.js 16.4.0 production build |
| `npm run test:e2e` | 9 passed, 38.3s | Microsoft Edge, 1280px 및 390px 공개 입력 흐름, 기존 CRUD·진행·취소·이력·실패·내보내기·모바일 흐름 |
| `verify_prepared_dataset.py --bundle ...` | PASS | 준비한 최종 평가 100건, 개발 20건의 원문·쌍·출처·해시·CSV 검증. 임시 DB에서 300 mock 구성 요소 호출, 500 결과. 실제 API 0회 |
| 출처 혼합 데이터 필터 강화 후 `test:e2e -- --project=desktop tests/public-email.spec.ts` | 2 passed, 21.9s | 출처 미기록 기존 샘플이 실제로 제외되는지 1280px/390px 재검증 |
| `prepare_public_dataset.py --register` 재실행 | PASS | 동일 파일 유지, 동일 catalog dataset ID 재사용. 원본·기존 생성물·기존 실험을 덮어쓰지 않음 |
| 실제 production 3001 화면 읽기 검증 | PASS | 출처 필터 후 100개 행, NORMAL 50/INJECTION 50, pageerror 0. 기존 완료 실험 2개 조회 유지 |

브라우저 플러그인 전용 skill/runtime은 제공되지 않아 프로젝트에 설치된 Playwright를 사용했다. 테스트용 서버 3101/8101은 별도 임시 DB를 사용한다. 실제 시작 요청은 DEMO 외에는 테스트에서 차단한다. 이번 작업의 유료 호출·실제 모델 추론은 0회다. 100건 검증도 사용자 실험 이력에 추가하지 않는다.

## 렌더링 및 사용자 흐름

흐름: 데이터셋 JSON 가져오기 → 정답과 별도 출처 배지 → 출처 필터 → HTML/주석 원문 안전 표시 → CSV 내보내기/재가져오기 → 5개 DEMO 구성 → 사례 출처 필터 → 새로고침 후 실험 유지.

| 화면 확인 | 결과 |
|---|---|
| 올바른 페이지 URL/제목 | PASS — `http://127.0.0.1:3001/#datasets`, 메일 가드 랩 |
| 빈 페이지/프레임워크 오류 화면 없음 | PASS — 실제 목록 100개 행 및 비교 화면 렌더링 |
| 앱 JavaScript 오류 | PASS — pageerror 0 |
| 스크립트/HTML 실행 방지 | PASS — script 태그가 문자로 표시, window.publicExecuted 미생성 |
| 작은 화면 가로 넘침 | PASS — 390px에서 document 폭이 viewport 이하; 비교표 내부 가로 스크롤 |
| 스크린샷 확인 | PASS — 아래 두 DEMO 화면. production 확인 이미지는 Git 제외 test-results에 저장 |

테스트 중 CSV 접두사가 원래 apostrophe를 제거하는 경계 사례를 발견해 명시적인 encoding marker로 해결했다. 새 브라우저 테스트의 heading locator가 div 기반 CardTitle과 맞지 않는 실패도 실제 DOM의 텍스트 locator로 수정하고 전체 9개를 재실행했다. 초기 실패를 최종 통과로 오인하지 않았다.

![DEMO 공개 입력 사례 1280px](qa/public-input-1280.png)
![DEMO 공개 입력 사례 390px](qa/public-input-390.png)

## 보존 및 제약

- 원래 실제 실험 `f7381fd6e0424e95ae8df6be4d97f9cb`는 완료/샘플5/결과45, `ffd6b35ef42d40749401dda8edcee522`는 완료/샘플5/결과25로 조회된다. 서버 재시작 전 진행 중인 실험이 없음을 확인했다.
- 실제 서버를 127.0.0.1:8001 및 :3001에서 새 코드로 재시작했다. 기존 DB 파일을 교체하거나 초기화하지 않았다. 다른 프로젝트 포트와 팀 Gmail 코드는 변경하지 않았다.
- 최종 평가 dataset ID `208f39151111415ba8ba55f1d99002c4`, 개발 ID `16c3cce4d30d43bf938af2a8dbc9a467`.
- Foundation-Sec/Qwen/Jev 실제 추론, Intel GPU, Gmail OAuth/수집/MIME 파싱은 이번 변경에서 재검증하지 않았다. 라이선스 사용 허가 및 정답의 독립적 인간 검수도 미확인이다.
- 원본 공개 자료는 본문만 있는 영어 합성 문맥 조작 데이터다. 단일 출처, 파생 claim family 단위 분리 및 사용자 작업 미전달의 한계를 유지한다.
- Git commit/push/클라우드 배포를 수행하지 않았다.
