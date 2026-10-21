# 이메일 프롬프트 인젝션 모델 비교 대시보드

> 개발: 박한빈 ([han122400](https://github.com/han122400)). ProDog 캡스톤 관련 개인 개발 산출물입니다.
> 이 저장소는 프로젝트별 브랜치로 구성됩니다. [전체 프로젝트 안내](https://github.com/han122400/capstone-llm-tools/tree/main)

Windows에서 실행하는 연구용 MVP입니다. **실제 Ollama와 OpenRouter Jev 요청을 수행하는 어댑터**, Python 평가 엔진, SQLite 저장, 한국어 Next.js 대시보드를 포함합니다. 기본 화면은 실제 평가 빈 상태이며 명시적으로 선택한 DEMO만 가짜 모델 응답을 사용합니다.

이 도구는 이메일의 **프롬프트 인젝션 분류 성능**을 측정합니다. 스팸·피싱 종합 판정이나 실제 이메일 에이전트의 공격 차단 성능이 아닙니다. NORMAL은 프롬프트 인젝션이 아닌 판정이며 모든 보안 위험이 없다는 뜻이 아닙니다. 실제 메일 연결·발송·삭제·첨부파일·공격 명령 실행은 없습니다.

## 빠른 시작 (PowerShell)

아래 명령은 이 README가 있는 프로젝트 폴더에서 실행합니다.

```powershell
# 이 README가 있는 프로젝트 폴더에서 실행
powershell -NoProfile -ExecutionPolicy Bypass -File '.\scripts\setup.ps1'
Copy-Item -LiteralPath '.env.example' -Destination '.env'
```

이미 `.env`가 있다면 복사하지 말고 필요한 값만 수정하세요. `ExecutionPolicy Bypass`는 위 명령 프로세스에만 적용하며 전역 정책을 변경하지 않습니다. Python 3.10 이상, Node 22 이상과 npm이 필요합니다. 설치 스크립트는 프로젝트 `.venv`와 `frontend/node_modules`만 구성합니다. 모델을 다운로드하거나 Ollama·드라이버를 업데이트하지 않습니다.

별도 터미널 두 개에서 실행합니다.

```powershell
# 터미널 1: 백엔드
powershell -NoProfile -ExecutionPolicy Bypass -File '.\scripts\backend.ps1'
```

```powershell
# 터미널 2: 프론트엔드
powershell -NoProfile -ExecutionPolicy Bypass -File '.\scripts\frontend.ps1'
```

대시보드: [http://127.0.0.1:3001](http://127.0.0.1:3001). API 문서: [http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs). 다른 프로젝트가 기존 3000·8000 포트를 사용 중이어서 이 프로젝트는 3001·8001을 사용합니다. 둘 다 loopback에만 bind합니다. 종료는 각 터미널에서 Ctrl+C입니다.

프로덕션 빌드는 `frontend`에서 `npm.cmd run build`, `npm.cmd run start`입니다. `EVALUATOR_BACKEND_URL` 환경변수로 Next의 백엔드 주소를 변경할 수 있습니다(기본 `http://127.0.0.1:8001`). 포트 변경 시 백엔드의 허용 로컬 origin도 함께 수정하세요.

## 첫 평가 순서

1. **데이터셋**에서 합성 smoke 데이터 5건을 등록합니다. 한국어·영어 업무 요청, 역할 사칭, 결과 조작, 교육 목적 공격 인용을 포함합니다.
2. **DEMO**를 선택하고 5개 구성으로 실행해 저장·이력·사례·내보내기 흐름을 확인합니다. DEMO 판정·속도는 실제 모델 성능이 아닙니다.
3. **설정 → 연결 상태 확인**에서 실제 설치 태그와 양자화, Ollama 버전, Jev 키 설정 여부를 확인합니다. 이 단계는 유료 추론을 수행하지 않습니다.
4. Foundation-Sec 태그를 확인합니다. 이번 PC에서는 원본 HF Q4_K_M 태그와 `qwen3.5:9b`(9.0B, Q4_K_M)가 설치되어 있습니다. Qwen9B는 2026-10-12 사용자의 별도 다운로드 요청으로 설치했습니다. 기존 2B는 비교에 대체 사용하지 않습니다.
5. Jev를 사용하려면 백엔드 전용 `.env`의 `OPENROUTER_API_KEY`를 설정하고 백엔드를 재시작합니다. UI는 키의 설정 여부만 보여 줍니다.
6. **실제 평가**를 선택합니다. 새 구성은 단독 3개와 **Foundation-Sec → Jev / Qwen → Jev**입니다. 기본 **로컬 1차 재사용**은 같은 실험의 로컬 판정만 재사용하고, 각 2단계 구성의 Jev는 원문과 로컬 판정을 받아 새로 요청합니다. 원문·로컬 판정의 OpenRouter 전송 및 추가 비용 발생 가능성을 확인한 뒤 시작합니다.
7. 개요에서 자동 판정률·탐지율·오탐·REVIEW·실패를 함께 확인하고 사례에서 원본 입력/응답, 오류, 구성 요소 결과 ID를 확인합니다. JSON/CSV로 내보낼 수 있습니다.

smoke는 연동 확인용 소표본입니다. 모델 우열이나 Jev 결합의 개선을 입증하는 평가가 아닙니다. 개발 데이터와 최종 평가 데이터는 dataset split으로 구분하고, 비슷한 공격 변형은 template_family로 추적하세요.

## 환경변수

| 이름 | 기본값 / 의미 |
| --- | --- |
| `OLLAMA_URL` | `http://127.0.0.1:11434` |
| `FOUNDATION_SEC_MODEL` | 실제 확인한 `hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q4_K_M-GGUF:Q4_K_M` |
| `QWEN_MODEL` | `qwen3.5:9b` |
| `OPENROUTER_API_KEY` | 비어 있음. 백엔드 환경변수에서만 사용 |
| `OPENROUTER_JEV_MODEL` | `typesafe/jev-1.13` |
| `CONTEXT_LENGTH` | 4096 |
| `TEMPERATURE`, `SEED` | 0, 42 (Ollama) |
| `MAX_OUTPUT_TOKENS` | 64. 추론 모델은 reasoning 때문에 부족할 수 있으며 한도 실패를 ERROR로 보존 |
| `TIMEOUT_SECONDS`, `MAX_ATTEMPTS` | 120초, 최대 3회 |
| `EVALUATOR_DATA_DIR` | 선택. 저장 위치 기본은 프로젝트 `runtime/` |
| `EVALUATOR_BACKEND_URL` | Next 백엔드 proxy 주소, 기본 8001 |

설정 화면에서 저장한 비밀 아닌 값은 SQLite에 보존되며 해당 환경 기본값보다 우선합니다. API 키는 설정 API로 입력·저장할 수 없습니다. 로컬 모델 옵션을 Jev에 임의로 전달하지 않습니다. 적용 옵션·모델 template/system/parameters/digest·반환 모델·버전을 결과와 이벤트에 남깁니다. 실제 GPU 가속은 장치 존재만으로 가정하지 않습니다.

**설정 → Ollama 로컬 모델 → Qwen thinking 모드**에서 ON/OFF를 선택하고 **설정 저장**을 누르면 새 실험의 Qwen 단독 및 Qwen → Jev 로컬 단계에 적용됩니다. 기본값은 OFF이며 Foundation-Sec의 thinking 설정에는 영향을 주지 않습니다. `/api/show`에서 선택 옵션의 지원이 확인된 경우에만 Ollama의 `think` 필드로 전달하며, 미지원 옵션은 오류로 표시합니다. 선택값(`qwen_thinking`)은 실험 설정 스냅샷에, 실제 적용값은 요청의 `request_options.think`와 모델 메타데이터의 `thinking_applied`에 기록합니다. 기존 실험은 변경하지 않습니다. ON에서는 추론 생성도 출력 예산을 사용하므로 출력 한도와 timeout을 함께 확인하세요. 이 옵션 추가만으로 실제 thinking 추론이나 성능 향상이 검증된 것은 아닙니다.

**Thinking 시험 설정:** 설정 화면의 **Thinking 시험 설정 채우기 → 설정 저장**은 컨텍스트 8192, 총 출력 4096, timeout 480초, Qwen thinking ON을 선택합니다. 출력은 thinking과 최종 JSON의 공통 상한입니다. 컨텍스트는 4096–65536, 출력은 16–8192 범위에서 편집 가능하며 입력 공간이 없는 조합은 저장·새 실험 시작 시 거부합니다. 실제 모델 지원 컨텍스트는 연결 검사에서 확인합니다. RAM과 지연이 늘 수 있으며 추론 완료나 정확도 개선을 보장하지 않습니다. 두 로컬 모델은 같은 예산을 사용하고 계속 순차 실행합니다. Jev에는 로컬 옵션을 전달하지 않습니다.

변경한 예산으로 평가하려면 **새 실험**을 시작하세요. **실패 항목 재실행**은 기존 실험 설정을 유지합니다. OFF/ON 비교는 같은 데이터·프롬프트·컨텍스트·출력·timeout으로 진행하세요. 출력 소진은 `OUTPUT_LIMIT`, 일반 JSON 파싱 실패는 `PARSE_ERROR`로 구분합니다. 이전 실험 결과는 소급 변경하지 않습니다. [예산 설계 및 검증 기록](docs/THINKING_BUDGET.md)을 참고하세요.

**설정 → 모델 판정 프롬프트**에서 현재 백엔드의 공통 지시문, NORMAL/INJECTION/REVIEW 기준, Foundation-Sec·Qwen 시스템 프롬프트 전체, Jev Decisions 질문 원문과 버전을 조회할 수 있습니다. 조회는 모델/API 추론을 실행하지 않습니다. 원문은 `backend/app/prompts.py`에서 관리하며 화면은 조회 전용입니다. 과거 실험의 기준은 해당 실험에 저장된 스냅샷으로 확인하세요.

## 구조

```text
backend/app/
  core.py          공통 입력, 5개 구성, 결합 정책, 지표
  cascade.py       로컬 → Jev 입력, 최종 판정, 변경 방향·기준선 비교
  adapters.py      Ollama / Jev Decisions / DEMO
  settings.py      환경설정 및 비밀 제외
  telemetry.py     시스템·백엔드·Ollama 프로세스 RSS 수집
  schemas.py       데이터셋 및 API 입력 검증
  store.py         SQLite, 불변 스냅샷, CSV 수식 방지
  engine.py        단일 큐, 순차 모델 로드, 재사용, 실시간, 취소
  main.py          FastAPI 로컬 API
backend/tests/     지표·어댑터·저장·엔진·API 테스트
frontend/src/      대시보드와 shadcn/ui 구성요소
frontend/tests/    Playwright 비용 없는 사용자 흐름
data/smoke.json    합성 이메일
scripts/          Windows 설치·실행·테스트
docs/             사용·연동 문서, 환경·검증 기록
runtime/          실제와 DEMO DB (Git 제외)
```

Next.js 16 / React 19 / TypeScript / Tailwind 4 / shadcn/ui / Recharts, FastAPI / SQLite / httpx / psutil을 사용합니다. 프론트엔드 없이 `backend` 테스트로 정책·어댑터·지표·실행을 검증할 수 있습니다. Promptfoo·OpenJev·별도 TypeSafe 키는 의존성이 아닙니다.

## 판정과 지표

현재 판정 기준은 `email-injection-choice-v3`입니다. 인용 여부 → 명확한 지시·권한 우회 → 구체적 유도가 있으나 맥락이 필요한 REVIEW → 일반 업무 NORMAL의 판정 순서를 명시합니다. 단순 회신 요청·승인 언급과 승인 절차 우회를 구분하며, 로컬과 Jev는 `backend/app/prompts.py`의 공통 기준을 사용합니다. 변경 내용과 검증 범위는 [프롬프트 v3](docs/PROMPT_V3.md)를 참고하세요. 기존 v1/v2 실험 기록은 보존됩니다. 실제 탐지 성능 개선은 아직 검증하지 않았습니다.

실행 상태(PENDING/RUNNING/SUCCESS/ERROR/CANCELLED/SKIPPED)와 판정(NORMAL/INJECTION/REVIEW/null)을 분리합니다. 기술적 실패는 null이며 REVIEW나 NORMAL로 대체하지 않습니다. 새 2단계 구성은 `local-then-jev-final-v1` 정책과 `email-injection-jev-review-v2` 질문을 사용하며 **Jev의 2차 판정이 최종 판정**입니다. 예비 판정과의 일치 자체를 정당성의 근거로 삼지 않고, 의견이 다르다는 이유로 REVIEW로 바꾸지 않습니다. 사례 화면에 “로컬 정상 → Jev 인젝션” 같은 변경 방향을 표시합니다. 로컬 요청 실패 시 Jev 호출을 생략하고, 어느 단계든 실패하면 최종 판정은 null입니다. 과거 재검토 v1 질문 스냅샷은 보존됩니다.

과거 `foundation_sec_jev` / `qwen_jev` 기록의 `unanimous-or-review-v1` 정책은 그대로 보존합니다. 이력에는 “기존 독립 결합”으로 표시하고 새 실행·재실행 대상으로는 선택할 수 없습니다. 새 구성과 같은 통계 행으로 합치지 않습니다. 상세 계약과 검증은 [로컬 → Jev 평가](docs/CASCADE_EVALUATION.md)를 참고하세요.

전체 스냅샷 N은 실패·취소 후에도 고정입니다. 자동 판정률·REVIEW·올바른 자동 판정·기술적 실패율은 N 기준입니다. 탐지율·누락률은 실제 INJECTION 전체, 오탐률은 실제 NORMAL 전체 기준입니다. 자동 Precision/Recall/F1은 REVIEW·실패를 제외한 자동 판정 집합 기준이며 자동 판정률과 함께 표시합니다. 모든 지표는 서버가 분자·분모·설명을 반환합니다. 분모 0과 미측정은 N/A입니다. 부분 결과는 표시하지만 완료된 결과와 순위를 매기지 않습니다.

## 실행·시간·비용·자원

- 기본 재사용 모드는 같은 실험·스냅샷·설정·입력 해시의 **로컬 1차 응답만** 재사용합니다. Jev 단독 응답은 2단계에 재사용하지 않습니다. 두 로컬 판정이 같아도 2차 Jev 요청은 구성마다 따로 호출합니다. 전체 실측 지연은 N/A이며 각 단계 요청 시간을 보존합니다. 새 Jev 호출·비용은 실제 요청마다 한 번씩 합산합니다.
- 전체 순차 호출 모드는 두 구성 모두 **로컬 → Jev 순차 호출**하며 로컬 요청 시작부터 Jev 최종 판정까지 직접 측정합니다. 모델 초기 준비 시간은 별도 이벤트입니다. 단독 평가도 선택하면 별도 요청이 추가됩니다.
- 로컬 모델은 한 번에 하나씩 준비·해제하고 `/api/ps`로 확인합니다. 해제 실패 시 다음 로컬 모델을 로드하지 않습니다. 각 이메일에는 새 messages만 전달합니다.
- 설명 옵션은 로컬 판정 후 별도 요청입니다. 원래 판정 지연, 추가 설명 지연과 원본 응답을 분리합니다. Jev 설명은 만들어 넣지 않습니다. 워밍업은 로컬만 사용하며 본 평가 지표에서 제외합니다.
- 평균·중앙값·P95는 성공과 실패를 나눕니다. P95는 선형 보간이며 소표본에서 안정적인 성능으로 해석하지 않습니다.
- `psutil`로 0.25초 간격의 샘플 피크를 수집합니다. 시스템 RAM, 백엔드 RSS, Ollama/runner RSS를 별도로 표시하며 합산하지 않습니다. 측정 간격보다 짧은 요청은 피크를 놓칠 수 있습니다. Jev 서버 RAM/GPU 및 전용·공유 GPU 세부 값은 N/A입니다.
- 요청별 자원 외에 로딩·워밍업·해제까지 포함한 전체 실험 자원을 `experiment_resources`에 별도 보존하며 JSON 내보내기로 확인할 수 있습니다.
- 비용은 응답의 `usage.cost`만 실제 비용 소계로 사용합니다. 알려지지 않은 시도 비용 수를 함께 표시합니다. timeout/취소된 외부 요청도 청구될 수 있으나 확인할 수 없으면 null입니다. 가격 추정·전력 비용은 구현하지 않았으며 N/A입니다.
- 입력은 공통 이메일 내용의 줄바꿈만 정규화합니다. 정답·샘플 ID·유형·메모는 전달하지 않습니다. 자동 절단 없이 공통 보수적 UTF-8 한도를 검사합니다. 예산 정책 `utf8-reserve-v2`는 시스템 프롬프트 바이트·총 출력·템플릿 512·경계 여유 1을 컨텍스트에서 빼고 최대 3000바이트로 제한합니다. 프롬프트 v3에서 4096/64는 입력1965바이트, 4096/1024는 1005바이트, 8192/4096은 2029바이트입니다. 과거 예산 정책은 경계 여유 1이 없었으며 기존 실험은 보존합니다. 템플릿 여유는 가정이며 정확한 토크나이저 검증이 아닙니다. 특이한 사용자 Modelfile의 반복 렌더링까지 보장하지 않습니다.

서버 재시작 시 미완료 실험을 INTERRUPTED로 표시합니다. 실패·미완료 재실행은 원본 스냅샷의 해당 샘플을 담은 **새 실험**이며 parent_run_id로 연결합니다. 기존 결과를 덮어쓰거나 다른 실험 응답을 자동 재사용하지 않습니다.

5개 새 구성을 N건에 모두 실행하면, 재시도·워밍업이 없는 성공 기준으로 Jev는 단독 N회 + 두 2차 검증 각 N회 = **3N회** 호출됩니다. 로컬 1차 재사용 여부와 관계없이 동일합니다. 예를 들어 100건이면 Jev 요청은 300회입니다.

## 저장·안전

`runtime/catalog.sqlite3`은 데이터셋과 비밀 아닌 설정, `runtime/real.sqlite3`과 `runtime/demo.sqlite3`은 각각 실제/DEMO 실험·요청 원본을 저장합니다. 완료된 실험은 데이터셋·설정 스냅샷을 소유합니다. 데이터셋 수정/삭제가 과거 결과를 바꾸지 않습니다. UI의 실험 삭제로 원본 응답을 포함한 해당 실험 기록을 삭제할 수 있습니다.

메일·모델 출력은 React 텍스트로만 렌더링합니다. HTML·명령·링크를 실행하지 않습니다. CSV 내보내기는 수식 시작 문자를 이스케이프합니다. `.env`, DB, 로그, build/test runtime은 Git에서 제외합니다. API 키·Authorization·메일 전문을 일반 로그에 남기지 않습니다. 원본 메일·응답은 로컬 DB에 있으므로 그 파일을 공유할 때 주의하세요. OpenRouter 포함 실제 평가에는 제목/본문이 해당 외부 서비스로 전송됩니다.

## 테스트

```powershell
# 전체: Pytest + 타입 + 빌드 + Playwright
powershell -NoProfile -ExecutionPolicy Bypass -File '.\scripts\test.ps1'

# 백엔드만
Set-Location -LiteralPath '.\backend'
& '..\.venv\Scripts\python.exe' -m pytest -q

# 프론트엔드만 (프로젝트 루트에서)
Set-Location -LiteralPath '.\frontend'
npm.cmd run typecheck
npm.cmd run build
npm.cmd run test:e2e
```

Playwright는 설치된 Microsoft Edge(`msedge`)를 사용합니다. 다른 브라우저는 `PLAYWRIGHT_CHANNEL`로 지정할 수 있습니다. 테스트는 별도의 3101·8101 서버와 테스트 저장 위치를 사용하며 모든 평가를 DEMO로 실행합니다. 실제 OpenRouter 추론과 Ollama 모델 로드/다운로드를 자동 테스트에서 수행하지 않습니다. 연결 상태 UI의 테스트 응답도 실제 유료 호출을 사용하지 않습니다.

실제 통합 검증은 일반 테스트와 분리하여 위 첫 평가 순서의 **실제 평가 시작** UI로 명시적으로 실행하세요. 현재 설치 검증 범위와 실측하지 않은 항목은 [연동 검증](docs/INTEGRATION.md), [환경 확인](docs/ENVIRONMENT.md), 최종 테스트 결과는 [검증 기록](docs/VERIFICATION.md)에 있습니다.

## 제약과 검증 범위

단일 프로세스·단일 큐용 MVP이며 여러 uvicorn worker를 사용하지 마세요. 실제 인증·Jev 유료 추론, Qwen9B 추론, Foundation-Sec 실제 판정 및 GPU 가속은 아직 미검증입니다. 공식 API 문서 및 설치 metadata 확인과 mock 테스트의 성공은 실제 탐지 성능 입증이 아닙니다. 관련 GitHub 이슈는 404로 접근할 수 없어 사용자 명세를 구현 기준으로 사용했습니다. 커밋·푸시·클라우드 배포는 수행하지 않았습니다.


## 공개 데이터셋과 Gmail 공통 입력 (2026-10-12)

지정 공개 저장소의 **Paired email scenarios**에서 최종 평가 NORMAL 50 / INJECTION 50건과 별도 개발 10 / 10건을 준비했습니다. 같은 정상·공격 쌍, 승인 주장 계열과 원본 시나리오가 집합을 넘지 않게 분리했습니다. 기본 데이터셋 목록에 추가되어 있으며 실제 평가는 자동 시작하지 않았습니다.

팀 Gmail 파서의 실제 응답 계약과 `analysis_text` 생성 규칙을 확인해 공통 입력 변환 계층을 추가했습니다. 본문만 있는 공개 자료는 nullable 평가용 래퍼로 표현하고 Gmail ID·발신자·시각·수집 상태를 만들지 않습니다. 정답과 출처는 별도 배지/필터로 표시하며 모델 입력에는 포함하지 않습니다. JSON/CSV와 실험 스냅샷에 출처를 보존합니다.

원본에 명시적 라이선스는 발견되지 않았습니다. 이 출처는 사전 승인·정책을 꾸며내는 사회공학적 문맥 조작을 다루므로 전통적인 지시문 공격 전반이나 에이전트 차단 성능으로 결과를 일반화하지 않습니다. 원본·생성 데이터는 Git 추적에서 제외합니다.

- [선정 수량·출처·계약 매핑·변환/검증 명령·첫 실제 평가 순서](docs/PUBLIC_DATA_GMAIL.md)
- [100건 offline mock 검증 기록](docs/PUBLIC_DATA_GMAIL_VERIFICATION.json)
- [백엔드·프론트엔드·브라우저 QA](docs/PUBLIC_DATA_GMAIL_QA.md)

추가 파일: `backend/app/email_input.py`, `scripts/prepare_public_dataset.py`, `scripts/verify_prepared_dataset.py`, `frontend/src/components/source-info.tsx`, `backend/tests/test_email_contract.py`, `backend/tests/test_public_selection.py`, `frontend/tests/public-email.spec.ts`. 기존 SQLite JSON 저장 구조를 확장해 완료된 과거 실험은 보존합니다. 새 환경변수는 필요 없습니다.


## 한국어 판정 건수와 전체 통계

개요의 기본 화면은 가장 최근 실험입니다. `실험별 통계`에서 날짜·시간으로 실험을 선택하고, `전체 통계`에서 지금까지의 누적 결과를 조회합니다. 실제 평가와 DEMO는 별도로 집계합니다.

메인 표는 **전체 메일, 정상 판정 정답, 인젝션 탐지 정답, 오탐, 미탐, 검토 필요, 실행 오류**를 건수로 표시합니다. 부분 결과에는 대기·진행 중·취소·미실행도 표시합니다. 실행 성공은 정답을 뜻하지 않습니다. 정답 비율·탐지율·오탐률·미탐률은 아래 성능 요약에서, 자동 판정률·정밀도·재현율·F1은 펼치기에서 확인합니다.

전체 통계는 데이터셋의 저장 버전·개발/평가 구분, 프롬프트 버전, 평가 방식으로 필터링할 수 있습니다. 같은 이메일을 반복 평가한 경우 각각 누적 평가 건수에 포함합니다. 구성별 분모는 해당 구성을 선택한 실험의 스냅샷만 합산하며 내부 구성 요소와 워밍업 결과는 판정 건수에서 제외합니다. 비율은 백엔드에서 누적 건수로 다시 계산합니다. API 비용은 실제 호출 기준으로 한 번만 집계하고, 재사용 결합의 전체 실측 시간은 N/A입니다. 미완료 실험과 혼합 조건은 안내로 표시하며 순위를 매기지 않습니다.

조회 API: `GET /api/statistics?demo=false&dataset=...&prompt=...&mode=...`. 데이터셋 필터 값은 응답의 `options.datasets`에서 확인합니다. 통계 조회는 모델/API 추론을 시작하지 않습니다. 새 기능 검증: 백엔드 `tests/test_statistics.py`, 브라우저 `tests/statistics.spec.ts`.
