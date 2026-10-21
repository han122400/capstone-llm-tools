# 시작 환경 확인

확인일: 2026-10-12 (Asia/Seoul). 초기 샌드박스 조회가 차단되어 읽기 전용 명령을 별도로 허용받아 확인했다. 전역 설정·드라이버·모델 파일은 변경하지 않았다.

| 항목 | 확인값 |
| --- | --- |
| CPU | Intel Core Ultra 7 258V |
| 시스템 모델 | 960XHA |
| 물리 RAM | 33,834,090,496 bytes (약 31.51 GiB) |
| GPU 장치 | Intel Arc 140V GPU (16GB로 보고됨) |
| 드라이버 | 32.0.101.8626 |
| Ollama 서버/클라이언트 | 0.35.1 / 0.35.1 |
| Python | 3.10.0 |
| Node / npm | 22.19.0 / 10.9.3 |
| OpenRouter 키 | 현재 프로세스 환경변수에 미설정 |

`/api/ps` 조회 시 로드된 모델은 없었다. GPU 장치 존재는 추론 가속 확인이 아니다. Intel GPU 가속, 실행 backend 이름, offload는 실제 요청 시의 `/api/ps` 원본과 모델 metadata로 판단해야 하며 아직 실측 추론을 확인하지 않았다.

## 모델 목록

- `hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q4_K_M-GGUF:Q4_K_M`: 설치됨, 목록 digest prefix `d354dd3e0e64`. `/api/show`에서 GGUF / llama / 8.03B / Q4_K_M, capabilities `thinking, completion` 확인. thinking 값 목록은 null이라 확인되지 않은 제어값을 보내지 않는다.
- `foundation-sec-web:latest`: 설치됨, 사용자 정의 태그. 기본 비교에는 별도 확인한 원본 HF 태그를 사용한다.
- `qwen3.5:2b`: 설치됨. 요구된 9B를 대체하지 않는다.
- `qwen3.5:9b`: 시작 시 미설치. 아래 후속 설치 기록 참조.
- `typesafe/jev-1.13`: 공식 공개 모델 metadata와 Decisions 문서로 사양 확인. 인증과 유료 추론은 미검증.

실제 모델 응답은 자동 테스트에 사용하지 않는다. 자동 테스트는 가짜 응답(DEMO) 또는 httpx MockTransport만 사용한다.

## 후속 설치: Qwen3.5:9B

2026-10-12 17:56 (Asia/Seoul), 사용자의 명시적인 다운로드 요청으로 `ollama pull qwen3.5:9b`를 실행했다. SHA256 검증 및 manifest 저장 후 success, exit 0을 확인했다. 기존 2B 및 Foundation-Sec 모델은 그대로 유지했다.

- 태그: `qwen3.5:9b`
- `/api/tags` 파일 크기: 6,550,825,550 bytes (약 6.55 GB, 실행 RAM이 아님)
- digest: `56671c2ab9385f9cfcb404638e32cd62d88e3501d44822208363c010179a3c90`
- `ollama show`: qwen35 / 9.0B / Q4_K_M / 모델 최대 컨텍스트 262144 (대시보드 기본 실험 컨텍스트는 4096)
- 모델 최소 Ollama 요구 버전: 0.30.0. 현재 0.35.1을 업데이트하지 않았다.
- 실제 추론·GPU 가속 검증은 수행하지 않았다.
