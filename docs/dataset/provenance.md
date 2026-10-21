# 모델 평가 데이터와 사용 범위

모델 비교 도구는 이메일 본문에 대한 프롬프트 인젝션 분류 실험을 수행합니다. 실제 메일 발송·삭제나 공격 명령 실행은 수행하지 않습니다.

- `data/smoke.json`: 개발한 합성 smoke 샘플이며 연동 확인용입니다.
- `backend/tests/fixtures/gmail_contract_sample.json`: `.invalid` 주소와 명시적 합성 표식을 사용하는 Gmail 응답 계약 테스트 자료입니다. 실제 사용자의 메일이 아닙니다.
- 외부 평가 출처: [compass-group-tue/prompt_injections_so_back](https://github.com/compass-group-tue/prompt_injections_so_back), Paired email scenarios.
- 확인한 원본 commit: `fbdb08b129a476ca44cd95d597eb96d67106bfd5`. 소스와 변환 계약을 직접 확인한 기록은 프로젝트 `docs/PUBLIC_DATA_GMAIL.md`에 있습니다. 논문 자체의 독립 검증 결과를 주장하지 않습니다.
- 공개 원본과 변환 데이터는 Git에서 제외했습니다. 해당 revision의 명시적 라이선스를 확인하지 못했으며, 원본·변환 데이터의 재배포 권한을 가정하지 않습니다.
- 포함된 문서·차트·스크린샷은 평가 도구와 실험 분석 기록입니다. 단일 출처의 영어 합성 자료에 대한 결과를 다른 공격 계열이나 에이전트 방어 능력으로 일반화하지 않습니다.
