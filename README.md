# Sentinel · 웹 취약점 보고서 워크스페이스

> 개발: 박한빈 ([han122400](https://github.com/han122400)). ProDog 캡스톤 관련 개인 개발 산출물입니다.
> 이 저장소는 프로젝트별 브랜치로 구성됩니다. [전체 프로젝트 안내](https://github.com/han122400/capstone-llm-tools/tree/main)

프런트엔드는 Vite + JavaScript, 백엔드는 FastAPI를 사용합니다.
FastAPI가 로컬 Ollama API를 호출하고 실제 모델 응답으로 정형화된 보고서를 생성합니다.
모델 학습·개발·다운로드는 수행하지 않습니다. 대시보드에서 프로젝트 `Modelfile`과 Ollama 연결 설정을 편집하고 저장할 수 있습니다.

기본 연결 모델: `hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q4_K_M-GGUF:Q4_K_M`

## 실행

Node.js 22.12 이상, Python 3.10 이상이 필요합니다.

의존성을 설치한 뒤 프로젝트 루트의 **`run.cmd`를 더블클릭**하면 FastAPI와 Vite를 한 번에 실행합니다. 터미널에서는 다음과 같이 실행할 수 있습니다.

```powershell
.\run.cmd
```

백엔드와 프런트엔드 로그는 각각 별도 터미널 창에 표시됩니다. 각 창에서 `Ctrl+C`를 누르면 해당 서버를 종료합니다. `.venv`가 있으면 가상 환경의 Python을 우선 사용하고, 없으면 PATH의 `python`을 사용합니다. 포트 8001 또는 5174가 사용 중이면 해당 서버의 중복 실행을 건너뜁니다. 다른 프로그램이 이 포트를 사용하고 있다면 해당 프로그램을 종료한 후 다시 실행하세요. Ollama는 별도로 실행 중이어야 합니다.

처음 설치하거나 각 서버를 따로 실행하려면 아래 명령을 사용하세요.

프런트엔드:

```powershell
npm install
npm run dev
```

접속: http://127.0.0.1:5174

별도의 터미널에서 백엔드:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8001
```

로컬 Ollama가 실행 중이어야 하며 지정한 모델이 설치되어 있어야 합니다. 상태 확인:

```powershell
ollama list
ollama show --modelfile hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q4_K_M-GGUF:Q4_K_M
```

API 문서: http://127.0.0.1:8001/docs

`GET /api/health`는 Ollama의 `/api/tags`에서 지정한 모델의 설치 여부를 확인합니다.
`POST /api/reports/generate`는 `title`과 `input_data` 두 필드만 받습니다.
화면은 같은 두 필드를 `POST /api/reports/generate/stream`으로 보내며, SSE 이벤트로 진행 상태, 생각 로그, 보고서 응답과 검증된 최종 결과를 받습니다.
제목은 보고서 저장용이며 모델에 전달하지 않습니다. 입력 데이터는 접두어를 붙이거나 공백·줄바꿈을 변경하지 않고 Ollama의 `/api/chat`에 그대로 전달합니다.
시스템 지침은 기존 `Modelfile`의 `SYSTEM` 블록을 사용합니다.
Vite 개발 서버는 `/api` 요청을 FastAPI의 8001 포트로 전달합니다.
기본 Ollama 주소는 `http://127.0.0.1:11434`입니다. 설정 페이지에서 변경할 수 있으며, 저장된 주소가 없을 때는 `OLLAMA_BASE_URL` 환경변수를 기본값으로 사용합니다.

## Ollama 설정

사이드바의 **Ollama 설정**에서 로컬 서버 주소, 설치된 모델, 메모리 유지 시간, 전체 Modelfile을 관리합니다. 모델 선택은 Modelfile의 `FROM`과 함께 변경됩니다. 연결 확인은 화면에서 편집한 값을 검사하고, 실제 보고서 생성에는 저장된 설정을 사용합니다.

- `FROM`: 설치된 Ollama 모델 이름. 모델 목록은 `/api/tags`에서 가져옵니다.
- `SYSTEM`: 보고서 생성에 사용할 시스템 프롬프트. 여러 줄 프롬프트는 `SYSTEM """ ... """` 구문으로 편집합니다.
- `PARAMETER`: `temperature`, `top_p`, `min_p`, `repeat_penalty`, `num_ctx`, `num_predict`, `top_k`, `seed`, `repeat_last_n`, `stop`을 지원합니다. `stop`은 여러 번 지정할 수 있습니다.

Modelfile 구문은 [Ollama 공식 문서](https://docs.ollama.com/modelfile)를 참고할 수 있습니다. 이 페이지는 앱의 생성 요청에 적용할 `FROM`, `SYSTEM`, `PARAMETER`를 저장합니다. `TEMPLATE`, `MESSAGE` 등 지원하지 않는 구문은 저장 시 오류로 안내합니다.

기본 설정은 `temperature` 0.1, `num_ctx` 16,384, `num_predict` 4,096을 바로 표시합니다. 접힌 **고급 설정**에는 `top_p` 0.95, `repeat_penalty` 1.0, 고정 seed 사용 여부와 숫자, 선택적인 `top_k` 입력을 제공합니다. 필드와 Modelfile 편집기는 양방향으로 동기화하며, 페이지를 여는 것만으로 파일을 변경하지 않습니다. seed 고정을 해제하거나 top_k를 비우면 해당 PARAMETER를 제거하고 모델 기본값을 사용합니다. `stop`은 Modelfile 편집기에서만 설정합니다. 잘못된 종료 문구는 JSON 보고서를 중간에 끊을 수 있습니다.

각 필드에 시작값, 최소·최대값과 조절 방법을 안내합니다. 아래 범위는 **앱의 입력 제한**이며 모든 모델의 지원 범위를 의미하지 않습니다. 특히 컨텍스트 크기는 모델과 RAM·VRAM에 맞춰 조절해야 합니다.

| 파라미터 | 앱 최소값 | 앱 최대값 | 권장 시작값 |
| --- | ---: | ---: | ---: |
| temperature | 0 | 2 | 0.1 |
| num_ctx | 512 | 131,072 | 16,384 |
| num_predict | 1 | 32,768 | 4,096 |
| top_p | 0 | 1 | 0.95 |
| repeat_penalty | 0 | 10 | 1.0 |
| seed | 0 | 2,147,483,647 | 선택 시 예: 42 |
| top_k | 0 | 2,000 | 선택 시 40 |

토큰 수·seed·top_k는 정수로 입력합니다. seed 고정은 결과 비교에 도움을 주지만 완전히 동일한 출력은 보장하지 않습니다. 파라미터의 의미는 [Ollama 파라미터 공식 설명](https://docs.ollama.com/modelfile#valid-parameters-and-values)을 참고하세요.

저장하면 실제 프로젝트 `Modelfile`을 갱신하고 서버 주소·메모리 유지 시간은 `.ollama-settings.json`에 보관합니다. 두 파일은 백엔드 재시작 후에도 유지되며, 다음 보고서부터 재시작 없이 적용됩니다. 보고서마다 시스템 프롬프트와 현재 입력만 전달하므로 대화 이력은 공유하지 않습니다.

메모리 유지 시간은 즉시 해제(`0`), 1분, 5분, 15분, 1시간 중 선택합니다. 모델을 메모리에 유지해도 이전 보고서의 대화 내용은 다음 요청으로 전달하지 않습니다.
보고서 생성 중에는 설정 저장을 거부하고, 문법·값 범위가 잘못되면 파일을 변경하지 않습니다. 다른 화면이나 파일 편집으로 설정이 바뀌었으면 다시 불러오도록 안내합니다. 저장하지 않은 편집은 화면을 이동해도 유지됩니다.

설정 API: `GET/PUT /api/settings/ollama`, `GET /api/ollama/models`, `POST /api/ollama/check`. 연결 주소는 로컬 루프백 주소만 지원합니다. 모델 설치·등록은 기존 Ollama 환경에서 진행합니다.

## 구현된 화면과 동작

- **대시보드**: 보고서 수, 확인된 항목, 검증 필요 항목, 완료율, 기간별 생성 차트, 판정 분포, 최근 보고서, 실시간 모델 Thinking 로그.
- **보고서 작성**: 제목과 입력 데이터 두 칸, 원본 데이터 붙여넣기, 필수값 확인, 실제 모델 분석, 실시간 생각 로그와 오류 표시.
- **보고서 목록**: 이름·대상 검색, 완료/초안 필터, 판정 필터, 검색 결과 없음 상태.
- **상세 보기**: 대상, 엔드포인트, 판정, 취약점 유형, CWE/OWASP, 근거, 추가 검증 사항, JSON 및 Thinking 로그 탭.
- **설정**: Ollama 서버 주소 편집, 설치된 모델 조회·선택, 연결 확인, 메모리 유지 시간 설정, 전체 Modelfile 편집·저장·다시 불러오기, 저장된 파라미터 표시, 기본 내보내기 형식 저장.
- **공통**: JSON 복사, JSON/Markdown 다운로드, 전체 JSON 내보내기, 보고서 삭제, 로컬 저장, 모바일 메뉴, 키보드 모달 탐색.

분석 대상은 따로 입력하지 않습니다. 보고서의 대상 표시는 모델이 반환한 `findings`의 `target`에서 가져옵니다. 과거 보고서의 입력 내용도 계속 조회할 수 있습니다.

## 데이터와 모델 응답

초기 보고서와 가상 프로필은 없습니다. 데이터가 없으면 통계는 0이고 빈 상태 안내가 표시됩니다.
이전 버전의 기본 더미 보고서는 브라우저 저장소에서 자동 제거합니다. 직접 입력해서 만든 기존 초안은 보존하고 분석 대기로 표시합니다.

새 보고서는 로컬 모델의 실제 응답이 성공했을 때만 저장합니다. 실패하면 오류가 표시되고 입력 내용은 유지됩니다.
모델 응답은 `classification`, `findings` 및 항목별 필드를 검증하며, 입력에 없는 근거 인용과 판정 불일치는 거부합니다.
Ollama 미연결, 모델 미설치, 타임아웃, 잘못된 JSON 응답에는 더미 결과를 반환하지 않습니다.

생성 중에는 대시보드와 작성 화면을 이동해도 같은 생각 로그가 이어집니다. 로그가 길면 자동으로 최신 내용으로 스크롤하며, 위쪽 내용을 읽고 있을 때는 스크롤 위치를 유지합니다. 로그 복사와 텍스트 다운로드도 지원합니다.
로그에는 실제 모델이 보낸 텍스트만 표시합니다. 서버 진행 상태는 별도로 표시하며, 모델이 생각 데이터를 보내지 않으면 빈 로그 안내를 표시합니다. 실패 시 이미 받은 로그와 입력 내용은 유지합니다. 성공한 로그는 보고서에 함께 저장하고 상세 보기에서 다시 확인할 수 있습니다.

Ollama의 `message.thinking` 응답을 실시간 로그로 표시합니다. 기본 모델의 [공식 모델 카드](https://huggingface.co/fdtn-ai/Foundation-Sec-8B-Reasoning#serving-with-vllm)에 명시된 `minimax_m2` 형식처럼 생각을 `message.content` 앞부분에 보내는 응답도 `</think>` 구분자로 분리합니다. 다른 모델을 선택하면 `/api/show`의 지원 기능에 맞춰 thinking 옵션을 설정합니다.

스트리밍과 일반 생성 모두 Ollama의 `format`에 JSON 스키마를 전달하여 최종 답변을 **보고서 객체 하나**로 제한합니다. 근거 문자열은 현재 입력의 비어 있지 않은 원문 줄 또는 문단에서 선택하도록 제한하므로 줄바꿈·공백·따옴표를 바꾼 인용을 방지합니다. 입력과 Modelfile 시스템 프롬프트는 그대로 전달합니다. Ollama의 별도 thinking 출력은 유지하고, 최종 결과는 Pydantic으로 필수 필드와 원본 근거를 다시 검증합니다. 전체 판정은 검증된 항목의 판정에서 `CONFIRMED > SUSPECTED > ATTACK_SURFACE > INFORMATIONAL` 순서로 계산하며 개별 판정은 바꾸지 않습니다. 스키마 제약은 보고서 형식을 위한 것으로 모델의 분석 정확도를 보장하지 않습니다. [Ollama 구조화 출력 문서](https://docs.ollama.com/capabilities/structured-outputs)를 참고할 수 있습니다.

`[CASE-001]`, `[CASE-002]`처럼 구분하고 각 사례에 HTTP 요청을 넣은 입력은 해당 사례 수를 최소 분석 항목 수로 지정합니다. 항목 수가 부족하면 완료 보고서로 저장하지 않습니다. 이는 개수 확인이며 모든 사례의 내용이 정확히 분석됐음을 보장하지는 않습니다. 사례 표식이나 인사말만으로 분석 항목을 만들지는 않습니다.

실패하면 JSON 구문 오류, 필드 검증 오류, 입력에 없는 근거, 출력 한도 초과를 구분해 안내합니다. 필드 오류에는 `findings.0.endpoint`처럼 확인할 위치를 표시하며, 검증하지 못한 출력을 완성된 보고서로 저장하지 않습니다.

제공된 근거를 분석하는 서비스이며, 대상 사이트를 자동으로 방문하거나 취약점 테스트를 실행하지 않습니다.
모델은 한 번에 한 건의 요청을 처리하며, 중복 요청에는 409 응답을 반환합니다. 모델 응답 제한 시간은 300초입니다.

보고서 및 내보내기 설정은 `localStorage`에 저장됩니다. 백엔드 DB와 사용자 인증은 포함하지 않습니다. 개발 서버는 로컬 주소에만 바인딩합니다.

Google Fonts의 DM Sans와 Noto Sans KR을 사용하며, 인터넷 연결이 없으면 시스템 글꼴로 대체됩니다.

## 검증 및 빌드

```powershell
npm run check
npm test
npm run build
npm run preview
python -m unittest discover -s backend -p "test_*.py" -v
```

`dist/`에 정적 프런트엔드가 생성됩니다. Vite 설정은 Windows 환경의 설정 파일 번들링 제약을 피하도록 `--configLoader native`로 실행합니다.
실제 보고서 생성에는 FastAPI가 필요합니다. 프로덕션에서는 `/api`를 FastAPI로 전달하도록 별도 프록시를 구성해야 합니다.
단위 검증은 모의 HTTP 응답으로 수행하며 제품 초기 데이터로 사용하지 않습니다.
