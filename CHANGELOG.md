# Changelog

All notable changes to the `antigravity_cli` Home Assistant integration will be documented in this file.

## 1.3.0 (2026-10-08)

### 초고속 Gemini API 직접 연동 및 3단계 대화 아키텍처 (Direct Gemini API & 3-Tier Assist Architecture)
- **Direct Google Gemini API 탑재**:
  - 통합구성요소 옵션(`Options Flow`) 및 최초 구성 화면에서 `gemini_api_key` 및 `gemini_model`(`gemini-2.5-flash` 기본값) 설정 지원
  - 정형화되지 않은 자연어 질의(지식, 일상 대화, 복합 질문 등)를 애드온 MCP 거치지 않고 Google Generative Language REST API로 직접 호출하여 응답 속도를 기존 4~10초에서 **1.0~1.5초**로 획기적 단축
  - 멀티턴 대화 히스토리 및 스마트홈 컨텍스트(현재 시각, 실내외 환경, 기기 현황) 주입
  - `control_device` 함수 호출(Tool Calling) 지원으로 자연어 제어 명령도 단일 라운드트립으로 즉시 실행
- **4단계 대화 파이프라인 (4-Tier Architecture)**:
  - **Tier 1 (0.05초)**: 로컬 고속 패턴 매칭 (기기 온/오프, 토글, %, 온도, 외출/취침 모드, 라디오, 날씨/온습도/문열림/세탁기 상태)
  - **Tier 2 (1.0~1.5초)**: 비정형 자연어 질의 직결 Gemini API (`gemini-2.5-flash`)
  - **Tier 3 (4~10초)**: 접두사(`/agy`, `/ai`) 명시 시 또는 Gemini 미설정 시 애드온 `/api/chat` 자율 에이전트/MCP(88개 도구) 폴백
  - **Tier 4 (오프라인 폴백)**: 외부 API 및 애드온 서버 불가 시, 엉뚱한 집 상태 요약 대신 정확한 원인 및 조치 안내 메시지 즉시 반환
- **대화 처리 동작 모드 일원화 (3종 통합 모드)**:
  - 중복되던 애드온 MCP 체크박스를 제거하고 [대화 처리 동작 모드] 단일 드롭다운으로 일원화
  - `초고속 모드 (로컬 + Gemini API)`: 로컬 0.05초 + Gemini 1초대 직결 (MCP 대기 완전 배제, 최고 속도)
  - `풀 하이브리드 모드 (로컬 + Gemini + 애드온 MCP)`: 로컬 -> Gemini -> 애드온 88개 MCP 도구까지 총동원
  - `로컬 전용 모드`: 외부 통신 없는 순수 로컬 패턴 매칭 전용
- **테스트 스위트 확장**:
  - `test_conversation.py`, `test_config_flow.py`, `test_gemini_client.py` 등 총 28개 테스트 전원 통과 (100% Pass)

## 1.2.0 (2026-09-16)

### 애드온 옵션 제어 및 커스텀 챗 서비스 추가 (Options Control & Chat Service)
- **애드온 설정 옵션 제어 엔티티 추가**:
  - `switch.antigravity_cli_auto_start_remote_control`: 리모트 데몬 자동 시작 옵션 on/off 스위치
  - `switch.antigravity_cli_enable_terminal`: 웹 터미널 기능 on/off 스위치
  - `select.antigravity_cli_chat_mode`: 채팅 작동 모드 선택 엔티티 (`full` 자율 에이전트, `fast_only` 로컬 고속 제어, `monitoring` 모니터링 전용)
  - 애드온 백엔드의 `GET /api/options` 및 `POST /api/options`와 실시간 연동
- **커스텀 챗 서비스 (`antigravity_cli.chat`) 신설**:
  - 자동화 및 스크립트에서 모드(`hybrid`/`llm_mcp`/`fast_local`), 대화 ID(`chat_id`), 모델(`model`)을 지정하여 챗을 실행하고 생성된 응답(`response`, `conversation_id`, `success`)을 직접 반환받을 수 있는 서비스 등록
- **테스트 스위트 및 린터 검증**:
  - `select` 및 `services` 단위 테스트 신설, 총 13개 테스트 전원 통과 및 Ruff 린트/포맷 100% 검증

## 1.1.0 (2026-09-12)

### 리모트 제어 데몬 스위치 및 안전 끄기 락 (Remote Control Switch & Turn-off Lock)
- `switch.antigravity_cli_remote_control`: `agy remote-control serve` 데몬 실행/중지 제어
- 추론 중(`thinking`), 도구 실행 중(`executing_tool`), 파일 수정 중(`file_working`) 시 데이터 보호를 위한 안전 **끄기 락(Lock)** 기능 탑재
- 에이전트 실시간 작업 상태 센서 (`sensor.antigravity_cli_agent_activity`) 및 데몬 상태 센서 (`sensor.antigravity_cli_daemon_status`) 추가

## 1.0.0 (2026-08-29)

### 최초 릴리즈 (Initial Release)
- Assist 대화 에이전트 연동 (고속 스마트홈 제어 및 미응답 시 로컬 폴백)
- 기본 상태 센서 6종 (`status`, `active_sessions`, `uptime`, `memory_usage`, `cpu_usage`, `scheduled_count`)
- 상태 강제 동기화 버튼 (`button.antigravity_cli_sync_status`)
