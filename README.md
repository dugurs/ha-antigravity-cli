# Antigravity CLI Integration for Home Assistant (`antigravity_cli`)

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/default)
[![Validate with hassfest](https://img.shields.io/badge/hassfest-passing-green.svg)](https://github.com/home-assistant/actions/tree/master/hassfest)

Home Assistant의 기본 음성/텍스트 어시스턴트인 **Assist**를 [`antigravity-cli` 애드온](https://github.com/dugurs/homeassistant-addons/tree/main/addons/antigravity-cli)의 자연어 스마트홈 제어 엔진과 연결해 주는 커스텀 통합구성요소입니다. 애드온 없이는 동작하지 않는 **얇은 클라이언트**이며, 실제 기기 제어·문답 로직은 대부분 애드온 쪽에 있습니다.

---

## 🚀 주요 기능

### Assist 대화 에이전트 (핵심 기능)
- HA의 **설정 > 음성 지원(Voice Assistants)**에서 이 통합구성요소를 대화 에이전트로 지정하면, 음성이든 텍스트든 Assist로 들어오는 모든 명령을 애드온의 `/api/chat`(고속 제어 엔진)으로 그대로 위임합니다.
- 방 스코핑, 다중 기기 후보 되묻기, 위험 기기(보일러/히터 등) 끄기 확인 게이트, 복합 명령("안방 등하고 선풍기 켜줘"), 온도·밝기·팬속도 지정, Music Assistant 플레이리스트 재생 등 애드온이 지원하는 모든 고속 제어 명령을 Assist에서 그대로 쓸 수 있습니다. 전체 명령어 목록은 [고속 제어 모드 명령어 가이드](https://dugurs.github.io/homeassistant-addons/fast-control-guide/) 참고.
- `/llm`, `!llm`, `/ai`, `ai `, `agy ` 등의 접두사를 붙이면 고속 매칭을 건너뛰고 애드온의 LLM(Antigravity CLI 본체 + ha-mcp) 추론 모드로 바로 넘어갑니다.

### 로컬 폴백 (애드온이 응답하지 않을 때만)
- 애드온이 다운되었거나 재시작 중이라 `/api/chat`이 완전히 응답하지 않는 경우에만, 이 통합구성요소에 내장된 경량 로컬 처리로 자동 전환됩니다. 애드온이 정상이면 이 경로는 전혀 실행되지 않습니다.
- 로컬 처리는 애드온만큼 정교하지 않지만 안전장치는 유지합니다: 방/기기 후보가 여러 개면 되묻고, 위험 기기(보일러/히터/온열기/전기스토브/콘센트/플러그)는 "그거 꺼" 같은 대명사 후속 명령을 포함해 항상 확인을 거친 뒤에만 끕니다. 보일러/에어컨/선풍기·환풍기 같은 기기는 집마다 실제 도메인(switch/climate/fan)이 달라서, 한 도메인에서 못 찾으면 다른 후보 도메인도 이어서 검색합니다.
- 복합 명령, %지정도 로컬 폴백에서 지원됩니다. 다만 Music Assistant 재생, 지연 명령("10분 후에 꺼줘") 등 애드온 전용 기능은 로컬 폴백 범위 밖입니다 — 애드온이 복구될 때까지 기다려야 합니다.
- 로컬 폴백으로 처리된 응답에는 항상 **"⚠️ (애드온 응답 없음, 로컬로 처리)"** 표시가 붙어서 어느 경로로 답했는지 구분할 수 있습니다.

### 센서 (Sensors)
애드온의 `/api/status`를 주기적으로 폴링해(기본 30초) 6개 센서로 노출합니다: 상태(`status`), 활성 세션 수(`active_sessions`), 가동 시간(`uptime`), 메모리 사용량(`memory_usage`), CPU 사용률(`cpu_usage`), 예약된 실행 개수(`scheduled_count` — 예약된 지연 명령 목록이 `scheduled_list` 속성으로 함께 노출됨).

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
3. 애드온의 호스트, 포트(기본 `8000`), API 키(설정했다면)를 입력합니다 — 등록 시 애드온의 `/api/status`에 실제로 접속해보고 성공해야 등록이 완료됩니다.
4. 등록 후 통합구성요소의 **옵션**에서 포트/폴링 주기/API 키를 다시 조정할 수 있습니다. "처리 모드(하이브리드/순수 AI/로컬 고속)" 항목도 옵션 화면에 남아 있지만, 현재 Assist 대화 에이전트는 항상 애드온을 우선 시도하고 실패할 때만 로컬로 전환하는 고정된 동작이라 **이 항목은 대화 에이전트 동작에 영향을 주지 않습니다**.

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
