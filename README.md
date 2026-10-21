# Capstone LLM Tools

박한빈이 개발한 보안 LLM 활용 도구 모음입니다. 각 프로젝트의 소스와 실행 방법은 별도 브랜치에서 확인할 수 있습니다.

| 프로젝트 | 코드 및 실행 방법 | 주요 내용 |
| --- | --- | --- |
| 이메일 프롬프트 인젝션 모델 비교 | [llm-comparison-test 브랜치](https://github.com/han122400/capstone-llm-tools/tree/llm-comparison-test) | Foundation-Sec·Qwen·Jev 비교, 독립/순차 결합, 데이터셋·실험 이력·오탐·미탐·실행 오류 분석 |
| 웹 취약점 보고서 생성 | [web-report-generation 브랜치](https://github.com/han122400/capstone-llm-tools/tree/web-report-generation) | 로컬 Ollama 기반 보고서 생성, 구조화 출력·원문 근거 검증, 실시간 로그 및 모델 설정 |

## 개인 기여

두 도구의 프론트엔드·백엔드, 모델 연결과 평가 흐름, 관련 테스트 및 문서를 개발했습니다. 이메일 모델 비교 도구는 ProDog 캡스톤의 모델 선정과 실험 분석을 위한 연구용 도구입니다. 웹 취약점 보고서 생성 도구는 제공된 보안 자료를 분석하는 별도 도구입니다.

## 코드 받기

```powershell
git clone --branch llm-comparison-test --single-branch https://github.com/han122400/capstone-llm-tools.git llm-comparison-test
git clone --branch web-report-generation --single-branch https://github.com/han122400/capstone-llm-tools.git web-report-generation
```

각 브랜치의 README에 설치·실행·테스트 방법과 구현 범위를 기록했습니다. 실제 메일, API 키, 로컬 DB, 설치된 의존성, 모델 가중치 및 외부 원본 데이터셋은 포함하지 않습니다. 모델과 API는 각자 환경에서 설정해야 합니다.

실험 결과는 기록된 데이터와 조건에 한정되며, 실제 AI 에이전트의 공격 차단 성능을 입증하지 않습니다. 외부 데이터의 출처와 재현 절차는 평가 도구의 `docs/PUBLIC_DATA_GMAIL.md`를 참고하세요.
