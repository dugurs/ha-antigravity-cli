# Antigravity CLI Integration for Home Assistant (`antigravity_cli`)

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/default)
[![Validate with hassfest](https://img.shields.io/badge/hassfest-passing-green.svg)](https://github.com/home-assistant/actions/tree/master/hassfest)

Home Assistant의 기본 음성/텍스트 어시스턴트인 **Assist**를 [`antigravity-cli` 애드온](https://github.com/dugurs/homeassistant-addons/tree/main/addons/antigravity-cli)의 자연어 스마트홈 제어 엔진과 연결해 주는 커스텀 통합구성요소입니다. 애드온 없이는 동작하지 않는 **얇은 클라이언트**이며, 실제 기기 제어·문답 로직은 대부분 애드온 쪽에 있습니다.

---

## 🚀 주요 기능

### Assist 초고속 3단계 대화 아키텍처 (3-Tier Engine)
HA의 **설정 > 음성 지원(Voice Assistants)**에서 이 통합구성요소를 대화 에이전트로 지정하면, Assist 음성 명령이 3단계 파이프라인으로 지능적·초고속 처리됩니다:
- **Tier 1 (0.05초 - 초고속 로컬 엔진)**:
  - 기기 온/오프, 토글, 커튼 열림/닫힘, %, 에어컨/난방 온도 설정, 방 스코핑, 위험 기기 확인 게이트, 복합 명령("안방 등하고 선풍기 켜줘").
  - 온습도/미세먼지 센서, 날씨/문열림/세탁기·건조기 가전 상태 브리핑, 외출/취침 모드, 라디오 재생 등을 클라우드 호출 없이 **50ms(0.05초)** 만에 즉시 실행합니다.
- **Tier 2 (1.0~1.5초 - 직결 Google Gemini API)**:
  - 로컬 패턴에 매칭되지 않는 비정형 자연어 질의("달의 지름이 얼마야?", "양자역학 원리가 뭐야?", "비 올 것 같은데 창문 닫아야 해?")가 들어오면, Google Generative Language REST API로 직접 호출되어 **1초대**에 빠르고 자연스럽게 응답합니다.
  - 통합구성요소 옵션에서 **Gemini API 키**를 설정하면 즉시 활성화됩니다 (`gemini-2.5-flash` 기본 탑재).
  - 스마트홈 기기 제어 도구(`control_device`)가 내장되어 있어, 비정형 자연어 제어 명령("어두우니까 거실 불 좀 은은하게 켜줘")도 단 1번의 API 왕복으로 실행 및 응답합니다.
- **Tier 3 (풀 하이브리드 모드 시 애드온 자율 에이전트 / MCP)**:
  - 대화 처리 동작 모드가 **'풀 하이브리드 모드'**일 때, 명령 앞에 `/agy`, `agy `, `/ai`, `ai `, `/llm`, `질문:` 등의 접두사를 붙이거나 Gemini API 키가 없을 때/호출 실패 시 애드온 `/api/chat` 본체(Antigravity CLI + ha-mcp 88종 도구)로 라우팅됩니다.
  - **초고속 모드(기본값)**에서는 느린 MCP 대기(4~10초)를 건너뛰어 음성 비서로서의 최고 속도를 유지합니다.
- **Tier 4 (오프라인/장애 비상 안내 폴백)**:
  - Gemini API 및 애드온 서버가 모두 오프라인이거나 응답하지 않는 경우, 엉뚱한 집 상태 요약을 읊는 대신 사용자가 문제를 인지하고 해결할 수 있도록 명확한 안내 메시지("해당 명령을 이해하거나 처리할 수 없습니다. Gemini API 키를 등록하거나 Antigravity CLI 애드온 연결 상태를 확인해주세요.")를 반환합니다.

### 센서 (Sensors)
애드온의 `/api/status`를 주기적으로 폴링해(기본 30초) 센서로 노출합니다:
- **상태 및 모니터링**: 상태(`status`), 활성 세션 수(`active_sessions`), 가동 시간(`uptime`), 메모리 사용량(`memory_usage`), CPU 사용률(`cpu_usage`), 예약된 실행 개수(`scheduled_count` — 예약된 지연 명령 목록이 `scheduled_list` 속성으로 함께 노출됨).
- **에이전트 실시간 상태**: 데몬 상태(`daemon_status`), 에이전트 작업 상태(`agent_activity` — 대기 중 / 추론 중 / 파일 작업 중 / 도구 실행 중).

### 스위치 (Switches)
- **리모트 제어 데몬** (`remote_control`): `agy remote-control` 데몬을 켜고 끌 수 있습니다. 에이전트가 추론 중이거나 파일 작업 중일 때는 안전을 위해 **끄기 락(Lock)**이 작동하여 스위치 끄기가 방지됩니다.
- **리모트 데몬 자동 시작** (`auto_start_remote_control`): 애드온 시작 시 리모트 데몬 자동 실행 여부를 설정합니다.
- **웹 터미널** (`enable_terminal`): 웹 터미널 기능 활성화 여부를 설정합니다.

### 선택 (Select)
- **채팅 작동 모드** (`chat_mode`): 애드온의 대화 처리 모드를 전환합니다.
  - `full`: 자율 에이전트 전체 기능 활성화
  - `fast_only`: 로컬 고속 제어 전용 (LLM 비활성화)
  - `monitoring`: 모니터링 전용 (채팅 요청 차단)

### 서비스 / 액션 (Services / Actions)
- **`antigravity_cli.chat`**: 스크립트나 자동화에서 모드, chat_id, 모델, 메시지를 지정하여 직접 챗을 수행하고 결과 응답을 반환받을 수 있습니다.
  - `message`: 보낼 메시지 / 프롬프트
  - `mode`: 처리 모드 (`hybrid`: 자율 에이전트, `llm_mcp`: LLM 도구 호출, `fast_local`: 로컬 고속 제어)
  - `chat_id`: 이어갈 세션 ID (선택사항)
  - `model`: 사용할 모델명 (선택사항, 예: `gemini-2.5-flash`)
  - 반환값: `response` (답변 텍스트), `conversation_id`, `success`

### 버튼 (Buttons)
- **상태 강제 동기화** (`sync_status`): 코디네이터를 즉시 새로고침해 센서 값을 갱신합니다.

### 다국어 지원
한국어 / 영어.

---

## 🔗 애드온 연동 (Requires the `antigravity-cli` add-on)

이 통합구성요소는 [`antigravity-cli` Home Assistant 애드온](https://github.com/dugurs/homeassistant-addons/tree/main/addons/antigravity-cli)이 **같은 네트워크에서 실행 중이어야** 동작합니다. 애드온을 먼저 설치·실행한 뒤 이 통합구성요소를 추가하세요.

연결에 쓰이는 애드온 API 엔드포인트:
- `GET /api/status` — 센서 폴링 (코디네이터가 기본 30초마다 호출)
- `POST /api/chat` — Assist 대화 에이전트가 모든 명령을 위임하는 곳 (SSE 스트림 응답 중 첫 `text` 이벤트만 사용)

애드온의 기본 포트는 `8000`이며, HA와 애드온이 같은 Supervisor 호스트에 있으면 보통 호스트를 `localhost`(또는 애드온 슬러그 호스트명)로 두면 됩니다. 애드온에 API 키를 설정했다면 아래 설정 단계에서 동일한 키를 입력해야 합니다.

---

## 📦 설치 방법 (Installation)

### 방법 1: HACS 수동 등록 (Recommended)
1. Home Assistant에서 **HACS > Integrations**로 이동합니다.
2. 우측 상단 메뉴에서 **Custom repositories**를 선택합니다.
3. 이 리포지토리 URL을 입력하고 범주로 **Integration**을 선택 후 추가합니다.
4. `Antigravity CLI`를 검색하여 다운로드합니다.
5. Home Assistant를 재시작합니다.

### 방법 2: 수동 설치
1. `custom_components/antigravity_cli` 폴더를 Home Assistant의 `config/custom_components/` 디렉터리로 복사합니다.
2. Home Assistant를 재시작합니다.

> **참고**: `conversation.py`처럼 이 통합구성요소의 파일을 수정한 뒤에는 Home Assistant를 **완전히 재시작**해야 반영됩니다 — 커스텀 컴포넌트는 코어 시작 시점에만 로드되고, 애드온처럼 리빌드/업데이트만으로는 다시 읽어들이지 않습니다.

---

## ⚙️ 설정 방법 (Configuration)

1. Home Assistant **설정 > 기기 및 서비스 > 통합구성요소 추가**로 이동합니다.
2. `Antigravity CLI`를 검색하여 선택합니다.
3. 애드온의 호스트, 포트(기본 `8000`), API 키(선택사항), Gemini API 키(선택사항)를 입력합니다.
4. 등록 후 통합구성요소의 **구성/옵션(Configure)** 화면에서 포트, 폴링 주기, API 키뿐만 아니라 **Gemini API 키**(`gemini_api_key`), **Gemini 모델**(`gemini_model`, 기본값: `gemini-2.5-flash`), 그리고 **대화 처리 동작 모드**를 언제든지 자유롭게 설정할 수 있습니다.
   - **초고속 모드 (로컬 + Gemini API)** *(기본값 / 권장)*: 0.05초 로컬 제어와 1초대 직결 Gemini API만 사용하여, 음성 비서로서 가장 쾌적하고 빠른 반응 속도를 제공합니다 (느린 MCP 대기 완전 배제).
   - **풀 하이브리드 모드 (로컬 + Gemini + 애드온 MCP)**: 로컬 및 Gemini로 처리되지 않는 복합 작업이나 접두사(`/agy`) 명령을 애드온의 강력한 ha-mcp 88개 도구로 끝까지 처리합니다.
   - **로컬 전용 모드 (로컬 매칭 전용)**: 외부 통신이나 AI 호출 없이 HA 로컬 기기 제어/센서 조회만 0.05초로 안전하게 수행합니다.

### Assist에서 기본 대화 에이전트로 지정하기
1. **설정 > 음성 지원(Voice Assistants)**로 이동합니다.
2. 사용할 파이프라인(또는 새 파이프라인)을 열고 **대화 에이전트**를 `Antigravity CLI`로 지정합니다.
3. 이후 그 파이프라인으로 들어오는 음성/텍스트 명령이 전부 애드온으로 위임됩니다.

---

## 🧪 로컬 개발 및 테스트

```bash
# 개발 의존성 설치
pip install -e ".[test]"

# 린트 검사
ruff check .

# 테스트 실행
pytest
```
