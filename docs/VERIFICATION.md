# 검증 기록

2026-10-12 (Asia/Seoul). 실행하지 않은 추론·테스트를 통과로 취급하지 않는다.

## 실제 수행한 환경·API 조회

- Ollama `/api/version`, `/api/tags`, `/api/show`, `/api/ps` 읽기 전용 조회.
- Foundation-Sec 원본 Q4_K_M 설치·digest·8.03B·Reasoning 메타데이터 확인.
- Qwen3.5:9B 미설치, OpenRouter 키 미설정 확인.
- Intel Core Ultra7 258V / Arc140V / 물리 RAM 확인. GPU 추론 가속은 미검증.
- OpenRouter 공식 Decisions 문서와 공개 모델별 endpoints 조회. 인증·유료 추론은 미검증.
- GitHub 이슈 #5는 웹 및 connector에서 접근 불가/404. 사용자 명세로 구현.

## 자동 테스트

백엔드 실행 명령:

```powershell
Set-Location -LiteralPath 'C:\Users\vinny\Desktop\2026-2\정보보호응용\팀플\LLM comparison test\backend'
& '..\.venv\Scripts\python.exe' -m pytest -q
```

최종 결과: **73 passed in 4.41s**. 지표 고정 8건, 분모 0·전부 REVIEW/ERROR·한 클래스, 9가지 판정 결합과 미완료 상태, 인증/제한/timeout/서버/스키마 오류, 제한 재시도, 취소 시 청구 이력 보존, 공통 입력·메타데이터 제외, 설치·모델 정체·양자화·컨텍스트 검사, 비용 중복 방지, 모델 해제, live 지연 직접 측정, 스냅샷·DEMO 분리, 서버 중단·새 시도, 안전한 CSV/API를 포함한다. 네트워크는 httpx MockTransport로 대체하며 실제 모델을 로드하지 않는다.

Windows의 제한된 실행 환경은 asyncio의 로컬 socketpair도 차단해 일반 mock 테스트가 멈출 수 있었다. 로컬 실행 권한으로 동일 테스트를 수행했다. 이는 모델·유료 API 호출 허용이나 전역 보안 설정 변경이 아니다.

최종 프론트엔드 검증도 직접 실행했다.

| 명령 | 결과 |
| --- | --- |
| `npm.cmd run typecheck` | 통과, exit 0 |
| `npm.cmd run build` | Next.js 16.4.0 프로덕션 빌드 통과, exit 0 |
| `npm.cmd run test:e2e` | **7 passed (22.2s)**, exit 0 |

Playwright는 데이터셋 생성·편집·삭제와 안전한 본문 표시, JSON/CSV 가져오기 및 유효성 검사, 5개 DEMO 구성 실행, 진행·취소·새 시도·실패 상태, 새로고침 복원, 사례·필터·이력·내보내기, 키 미설정·모델 미설치·외부 전송 고지, 데스크톱·모바일 흐름을 확인했다. 차트 실제 막대 높이 검증도 포함했다. 설치된 Microsoft Edge와 격리된 3101/8101 서버·테스트 DB를 사용했다. 실제 추론 요청은 테스트에서 금지한다.

## IAB 수동 흐름

Codex 인앱 브라우저에서 실제 서비스 `http://127.0.0.1:3001`에 접속했다. 초기 실제 결과 빈 상태 → 합성 smoke 5건 등록 → DEMO 선택 → 다섯 구성 실행 → 25/25 완료 → 비교표와 차트 → 새로고침 복원 → 사례 매트릭스와 원본 응답·구성 요소 ID → 설정의 실제 설치 사전 검사를 확인했다. DEMO 물리 외부 API 호출은 **0회**였다. 사용자 runtime에는 이 명시적인 DEMO 기록과 합성 데이터만 추가했고 실제 평가 기록은 만들지 않았다. 최종 프로덕션 서버를 3001/8001에 다시 실행한 후 실제 평가 기본 화면의 빈 결과와 다섯 구성 N/A를 재확인했다.

## 시각 검증

구현 당시 Image Gen 시각 참고 이미지와 실제 Playwright 데스크톱·모바일 screenshot을 `view_image`로 직접 확인했다. 초기 콘셉트 이미지는 구현 완료 후 문서 정리 과정에서 삭제했으며, 실제 화면 기록은 `docs/qa/`에 보존한다. 최종 데스크톱 viewport는 1280×900, 모바일은390×844다.

비교한 항목: 탐색 구조/브랜드와 제목, 흰 패널·슬레이트 배경·인디고 강조색, 5개 구성의 표 순서, 실제/DEMO 구분과 N/A 빈 상태, 분자·분모의 가시성, 두 차트의 배치, 모바일 상단 탐색과 가로 스크롤 표. 시각 참고 이미지가 잘못 붙인 Qwen=API/Jev=Local을 명세에 맞게 바로잡았고, 전체 시간·Precision/Recall·추가 비용·원본 결과 정보는 실제 요구사항에 맞게 확장했다. 콘셉트 승인 단계를 다시 요구하지 않고 사용자의 최종 구현 명세를 우선했다.

초기 screenshot에서 Recharts 기본 애니메이션이 완료되기 전에 막대가 찍혀 실제 표 비율과 달라 보이는 문제를 발견했다. 연구 차트의 애니메이션을 비활성화하고 실제 값이 즉시 그려지도록 수정했다. 데스크톱 화면 전체 캡처의 sticky 탐색 위치도 캡처 전 스크롤을 위로 이동해 확인한다. 시각 참고를 픽셀 단위 동일 화면이라고 주장하지 않으며 기능·분모의 정확성을 우선했다.

최종 화면 기록은 `docs/qa/`에 의도적으로 보존한다. 이 파일들의 DEMO 수치는 모델 성능 자료가 아니다.

## 남은 실제 연동 검증

- Foundation-Sec 실제 판정 및 출력 토큰64의 충분성.
- Qwen3.5:9B 설치 후 Q4_K_M·실제 추론.
- OpenRouter 키 설정 후 인증·Jev 원본 choice/usage/cost 반환.
- 실제 모델 실행 시 CPU/GPU backend와 offload/메모리.
- 확장된 독립 평가 데이터에 대한 성능 비교.

현재 어떤 모델이 우수하거나 Jev 결합이 성능을 개선했다고 결론 내릴 근거는 없다.
