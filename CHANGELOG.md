# Changelog

All notable changes to the `antigravity_cli` Home Assistant integration will be documented in this file.

## 1.2.0 (2026-09-16)

### 애드온 옵션 제어, 모델 쿼터 센서 및 커스텀 챗 서비스 추가 (Options Control, Quota Sensors & Chat Service)
- **애드온 설정 옵션 제어 엔티티 추가**:
  - `switch.antigravity_cli_auto_start_remote_control`: 리모트 데몬 자동 시작 옵션 on/off 스위치
  - `switch.antigravity_cli_enable_terminal`: 웹 터미널 기능 on/off 스위치
  - `select.antigravity_cli_chat_mode`: 채팅 작동 모드 선택 엔티티 (`full` 자율 에이전트, `fast_only` 로컬 고속 제어, `monitoring` 모니터링 전용)
  - 애드온 백엔드의 `GET /api/options` 및 `POST /api/options`와 실시간 연동
- **AI 모델 잔여 쿼터 센서 (RAM 점유 0% 무부하 보장)**:
  - `sensor.antigravity_cli_gemini_quota`: Gemini 주간 쿼터 잔여율 (%)
  - `sensor.antigravity_cli_claude_quota`: Claude 주간 쿼터 잔여율 (%)
  - `agy` 서브프로세스를 정기 폴링하지 않고 워밍업된 메모리 캐시만 즉시 참조하여 추가 메모리 소모 0% 보장
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
