# 공개 이메일 데이터와 Gmail 공통 입력

확인일: 2026-10-12. 실제 구현 내용과 사용 방법은 이 문서에, offline 검증 결과는 `PUBLIC_DATA_GMAIL_VERIFICATION.json`에 기록한다.

## 출처와 라벨 확인

- 단일 출처: [compass-group-tue/prompt_injections_so_back](https://github.com/compass-group-tue/prompt_injections_so_back).
- README 제목: **AI Agents May Always Fall for Prompt Injections**. README 데이터셋 표의 표시 이름: **Paired email scenarios**.
- 실제 clone commit: `fbdb08b129a476ca44cd95d597eb96d67106bfd5`.
- 직접 포함된 파일: `defense_evaluation/paired_emails_dataset.json`, 4,200쌍. 별도 데이터 다운로드나 생성 API는 필요하지 않았다. 다른 하위 데이터셋과 결과 파일은 평가셋에 섞지 않았다.
- 파일 SHA-256: `ed70ce117fc5916fe547d1e432e6a1be17763eb51ee15cdb4f36feb3af03d5b4`. 별도 데이터 revision은 발견하지 못했으므로 null. 원본 파일 위치와 commit 고정 URL도 샘플마다 보존한다.
- **라이선스 미확인**: 해당 commit의 추적 파일과 README에서 LICENSE/COPYING 또는 명시적 사용 허가를 찾지 못했다. 공개 접근 가능성과 재사용·재배포 허가를 같은 의미로 취급하지 않는다. 원본과 생성 이메일은 Git에서 제외한다.
- README, `generate_data/generate_dataset.py`, `generation_prompt.txt`는 LLM 합성 생성을 설명한다. 이 근거로 synthetic=true를 기록한다. upstream 코드·설치·생성 스크립트는 실행하지 않았다.
- `classifier_eval/eval_classifier.py`는 `pair.benign.external_content`를 정상(0), `pair.attack.external_content`를 공격(1)으로 평가한다. 같은 매핑으로 NORMAL/INJECTION을 사용한다. 피싱 여부나 공격 성공 결과를 정답으로 사용하지 않는다.

이 출처의 공격 정의는 AI의 사전 승인·회사 정책·관리자 권한을 꾸며내는 문맥 조작이다. 생성 프롬프트는 이를 전통적인 지시문 공격과 구분하여 “social engineering, NOT prompt injection”이라고도 기술한다. README와 원본 분류기에서는 prompt-injection 평가 대상으로 사용한다. 따라서 이 데이터는 **출처의 문맥 조작 정의에 따른 본문 분류 평가**다. 원래 `user_prompt`와 `expected_action`은 source_context에 보존하지만 탐지기에는 전달하지 않는다. 실제 권한의 진위, 에이전트의 공격 차단 성능, 다른 공격 유형 전반의 우열을 측정하지 않는다. 정답의 의미적 타당성을 팀이 별도로 재검토할 수 있다.

## 선별과 분리

| 용도 | 정상 | 인젝션 | 원본 쌍 |
|---|---:|---:|---:|
| 최종 평가 | 50 | 50 | 50 |
| 개발·프롬프트 조정 | 10 | 10 | 10 |

seed=`20261012`. pair는 같은 집합에 보존한다. 원본 technique를 `claim:<technique>`로 표시하는 보수적인 **파생 분리 그룹**을 사용한다. 개발에는 `fabricated_manager_approval`, `fabricated_prior_agreement` 전체를 배정하고, 평가는 나머지 6종에서 고른다. 두 집합은 pair ID, 파생 family, 원본 scenario가 겹치지 않는다. 이는 랜덤 행 분리와 다른 분포를 만들므로 결과 해석에 반영해야 한다.

전체 파일에서 본문 완전 중복·서로 충돌하는 정답, 필수 필드, 원본 expected_action 규칙을 점검한다. 선별 시 소문자 4단어 shingle의 Jaccard 유사도(숫자는 #로 정규화) 0.65 이상인 다른 쌍을 제외한다. 정상/공격 같은 쌍 내부 유사성은 의도된 구조다. 선택된 집합 간 최대 점수는 0.0584415584였다. 이 휴리스틱은 의미적 독립성 보장이 아니며 100건을 100가지 독립 공격으로 집계하면 안 된다.

원본 생성 규칙에 없는 technique 3쌍(ID 605, 697, 698)은 검토 파일에 분리했다. 정답을 REVIEW로 바꾸거나 수량을 복제해서 채우지 않았다. `selection_manifest.json`은 seed, 선택한 원본 ID, 제외·검토 이유, 파일 해시, 분리 규칙, 한계와 라이선스 상태를 담는다. 각 데이터셋 manifest에는 실제 모델 입력 해시/바이트 수도 들어 있다.

## 저장 위치와 재현 명령

```text
data/raw/prompt_injections_so_back/                 원본 clone, 실행하지 않음
data/processed/prompt_injections_so_back/
  fbdb08b129a4-seed20261012/
    evaluation.json                               NORMAL 50 + INJECTION 50
    development.json                              NORMAL 10 + INJECTION 10
    selection_manifest.json                       선정·출처·중복 점검 기록
    review_required.json                          별도 검토 3쌍
scripts/prepare_public_dataset.py                  추출·변환, 선택적 catalog 등록
scripts/verify_prepared_dataset.py                 임시 DB에서만 mock 검증
```

```powershell
Set-Location -LiteralPath 'C:\Users\vinny\Desktop\2026-2\정보보호응용\팀플\LLM comparison test'
# 최초 확보 때만. 폴더가 있으면 status와 revision을 확인하고 기존 원본을 보존한다.
git clone 'https://github.com/compass-group-tue/prompt_injections_so_back.git' 'data/raw/prompt_injections_so_back'

# 같은 입력이면 같은 결과. 기존 생성 파일과 내용이 다르면 덮어쓰지 않고 중단한다.
& '.\.venv\Scripts\python.exe' 'scripts/prepare_public_dataset.py' --seed 20261012 --evaluation-pairs 50 --development-pairs 10 --register

# 유료 호출 없음. 사용자 DB 실험 이력에도 추가하지 않는다.
& '.\.venv\Scripts\python.exe' 'scripts/verify_prepared_dataset.py' --bundle 'data/processed/prompt_injections_so_back/fbdb08b129a4-seed20261012'
```

`--register`는 기본 `runtime/catalog.sqlite3`에 데이터셋만 추가하고 같은 이름/파일 해시의 기존 등록을 재사용한다. 평가를 시작하지 않는다. 다른 저장 경로로 서버를 실행한다면 UI 가져오기를 사용한다. 기본 catalog에는 평가·개발 두 데이터셋이 추가되어 있다. 완료된 기존 실험 2개와 원래 smoke 데이터는 수정하지 않았다.

## 팀 Gmail 계약과 매핑

확인한 팀 문서: [integration.md](https://github.com/ProDog-2026/workspace/blob/develop/src/gmail/docs/integration.md), `collect-api-contract.md`, 실제 `src/gmail/src/prodog_gmail/mail.py`, `docs/collect-api-sample.json`. 웹 문서 접근은 실패하여 같은 팀 저장소의 로컬 `develop` checkout에서 확인했다. 로컬 commit은 `6e82068c34690506f932f5c73d054257bb2cb996`이고 Gmail 관련 추적 파일의 변경은 없었다. 이 팀 저장소는 수정하지 않았다.

`email.kind=gmail_parsed`의 content는 실제 파서가 내보내는 모든 키를 요구한다. str을 임의로 null/숫자로 강제 변환하지 않는다.

| 팀 필드 | 파싱 응답 타입 | 공개 본문 자료 |
|---|---|---|
| id, thread_id | str | null; sample_id/pair_id로 대체하지 않음 |
| subject, sender | str (빈 문자열 허용) | null; 제목·발신자 추정하지 않음 |
| received_at | str 또는 null | null |
| labels | list[str] | null; 정답 label과 별개 |
| text_plain | str | 원본 external_content 한 덩어리를 텍스트로 보존; MIME 추출을 주장하지 않음 |
| text_html | str | null; 본문을 HTML MIME으로 추정하지 않음 |
| analysis_text | str | 동일 원본 본문 문자열 |
| attachments | list[Attachment] | null; 첨부가 없는 것으로 단정하지 않음 |
| warnings | list[str] | null; 파싱 경고가 없다고 단정하지 않음 |
| truncated | bool | null; 원본 수집 완전성 미확인 |
| body_hash | str 또는 null | content.body_hash=null (RFC822 원본 바이트 없음) |
| trust | literal UNTRUSTED | UNTRUSTED 입력 경계를 명시 |

Attachment의 필수 키는 filename:str, content_type:str, size_bytes:int|null, disposition:str, content_id:str, is_inline:bool이다. attachment content는 가져오거나 실행하지 않는다.

공개 자료는 Gmail 응답 자체로 위장하지 않고 `email.kind=body_only` 평가용 wrapper의 nullable projection에 넣는다. Sample의 subject/body는 UI·이전 형식 호환을 위한 사본이며 wrapper 원문과 충돌하면 가져오기를 거부한다. 제목 없는 행은 화면에서 “제목 없음”으로 표시한다. 이는 모델 입력의 가짜 제목이 아니다.

팀 파서는 MIME 순서대로 plain과 **원문 HTML**을 `"".join(analysis)`하여 analysis_text를 만든다. Gmail 입력은 이미 제공된 analysis_text를 그대로 사용한다. plain과 HTML 집계 필드만으로 MIME 순서를 다시 추측하지 않는다. 공개 자료는 본문 한 덩어리를 그대로 사용한다. HTML 태그·주석·hidden 요소를 제거하지 않는다. 이 작업에서 EML/MIME 파서를 새로 실행하거나 검증한 것은 아니다. 팀 응답 예시의 계약 수용과 HTML 보존만 테스트했다.

## 분석기 사용법과 안전 경계

```python
from app.email_input import sample_from_gmail
from app.core import model_input

# parsed_response는 팀 GET /api/mails/{id}의 기존 응답 딕셔너리.
# Gmail 계정을 연결하거나 API를 호출하는 함수가 아니다.
sample = sample_from_gmail(parsed_response, sample_id="internal-evaluation-001", label="NORMAL", synthetic=None)
text = model_input(sample)
```

이 sample을 기존 `POST /api/datasets`의 samples 배열 또는 JSON/CSV 가져오기에 사용한다. JSON 예시는 다음과 같다.

```json
{"name":"Gmail 파싱 응답 평가","split":"development","samples":[
  {"sample_id":"internal-001","label":"NORMAL","synthetic":null,
   "email":{"kind":"gmail_parsed","content":{"id":"기존 응답의 실제 값","thread_id":"기존 응답의 실제 값","subject":"기존 제목","sender":"기존 발신자","received_at":null,"labels":[],"text_plain":"기존 본문","text_html":"","analysis_text":"기존 본문","attachments":[],"warnings":[],"truncated":false,"body_hash":null,"trust":"UNTRUSTED"}}}
]}
```

위 예시의 빈 목록/false를 누락 정보의 기본값으로 쓰지 않는다. 실제 파서 응답값이 있어야 gmail_parsed로 가져올 수 있다. 본문만 있는 자료는 body_only wrapper를 사용한다.

모델 입력 허용 목록은 **확인된 subject, sender, analysis_text→body**다. null/빈 메타데이터는 나열하지 않는다. Gmail ID·스레드·labels·시간·해시·출처·원본 ID·정답·유형·notes·source_context·다른 모델 답변은 전송하지 않는다. 기존 sample은 종전 subject/body JSON 및 `subject-body-lf-v1`을 유지한다. 공통 이메일은 `gmail-analysis-lf-v1`로 기록한다. 모든 모델은 같은 JSON과 LF 정규화를 공유한다.

Sample.body_hash는 원본 external_content의 UTF-8 SHA-256이고 body_hash_method를 함께 기록한다. Gmail content.body_hash는 팀의 RFC822 본문 바이트 해시다. 결과 input_hash는 실제 모델 JSON 입력의 SHA-256이다. 이 세 의미를 혼동하지 않는다.

긴 입력은 기존 공통 보수적 UTF-8 한도에서 ERROR로 거부하며 절단하지 않는다. Gmail warnings가 있거나 truncated=true, attachments가 있으면 보수적으로 `incomplete_input` 오류 및 decision=null을 기록하고 모델 판정을 요청하지 않는다. 이는 단순 날짜 경고도 보류하는 MVP의 보수적 정책이다. body_only는 알려진 본문 범위에 대해서만 평가할 수 있으며 수집 완전성은 unknown으로 유지한다. 결과 input_quality에 수집 경고·잘림·첨부 범위·본문 해시·계약 revision과 한도 정책을 보존한다. 공통 결합은 오류를 NORMAL/REVIEW로 바꾸지 않는다.

화면은 React 텍스트/pre로만 표시한다. HTML·명령·링크는 실행하지 않는다. CSV는 수식 시작 문자를 escape하고 `__csv_text_encoding=spreadsheet-safe-v1` 표시를 넣는다. 이 표시가 있는 가져오기만 안전 접두사를 복원하여 실제 원문의 apostrophe도 보존한다. 새 CSV도 UTF-8이다.

## 호환성·테스트·첫 실제 평가

SQLite JSON payload에 optional 필드를 추가했다. 기존 테이블·행·완료된 snapshot은 다시 쓰지 않는다. 수정/삭제 후에도 실험 snapshot, 출처, 원본 응답은 해당 실험의 고정 기록으로 남는다. 데이터셋 UI 수정은 manifest를 유지한다. 출처가 없는 과거 샘플은 “미기록”, synthetic=null은 “미확인”으로 표시한다. 원문 wrapper는 보존하고 변경본은 공통 content와 함께 다시 가져온다.

```powershell
& '.\.venv\Scripts\python.exe' -m pytest backend/tests -q
Set-Location -LiteralPath '.\frontend'
npm.cmd run typecheck
npm.cmd run build
npm.cmd run test:e2e
```

실행·검증 결과는 `PUBLIC_DATA_GMAIL_VERIFICATION.json`과 `PUBLIC_DATA_GMAIL_QA.md` 참조. 기존 다섯 구성과 결합·실행·취소·오류·비용 테스트를 유지한다. 실제 모델 응답·GPU·유료 Jev·Gmail 인증/파싱·독립적인 사람의 정답 검수·라이선스 사용 권한은 이번 작업에서 검증하지 않았다.

첫 실행 순서:

1. 백엔드와 프론트엔드를 재시작하고 `http://127.0.0.1:3001`을 새로고침한다. `.env`의 기존 Ollama 태그 및 OPENROUTER_API_KEY/OPENROUTER_JEV_MODEL을 사용한다. 새 비밀 환경변수는 없다.
2. 데이터셋 → **공개 paired emails · 최종 평가 · seed 20261012** 선택. 100건의 정답/출처, 본문, 쌍, 선정 기록을 확인한다. 개발 20건으로 조정한 규칙을 최종 평가 정답에 맞춰 변경하지 않는다.
3. 필요하면 준비한 evaluation.json을 가져오거나 JSON/CSV로 내보낸다. 출처 필터로 이전 smoke와 구분한다.
4. DEMO로 화면과 저장 흐름을 확인할 수 있다. DEMO 수치는 실제 성능으로 해석하지 않는다.
5. 평가 실행 → 해당 최종 평가 데이터셋 → 실제 평가 → 원하는 5개 구성 → 기본 결과 재사용 모드. 모델 설치·연결 상태 및 실험 조건을 확인한다.
6. Jev 포함 시 본문 외부 전송·비용 안내를 확인하고 **사용자가 실제 평가 시작을 누른다**. 로컬 모델은 순차 실행·해제한다. 이번 구현 작업은 이 버튼을 누르지 않았다.
7. 사례와 지표를 함께 확인한다. 영어 합성 단일 출처·문맥 조작 분류의 한계를 유지한다. JSON/CSV snapshot으로 결과를 보관한다.
