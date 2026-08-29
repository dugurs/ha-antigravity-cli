# Antigravity CLI Integration for Home Assistant (`antigravity_cli`)

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/default)
[![Validate with hassfest](https://img.shields.io/badge/hassfest-passing-green.svg)](https://github.com/home-assistant/actions/tree/master/hassfest)

Home Assistant 커스텀 통합구성요소(Custom Integration)인 **Antigravity CLI** 연동 패키지입니다.

---

## 🚀 주요 기능

- **UI Config Flow 지원**: 설정 UI에서 호스트 IP, 포트, 인증 API 키를 간편하게 설정
- **DataUpdateCoordinator 패턴**: 주기적 상태 폴링 및 효율적인 엔터티 업데이트
- **센서(Sensors)**:
  - 에이전트 서비스 상태 (`sensor.antigravity_cli_status`)
  - 활성 세션 수 (`sensor.antigravity_cli_active_sessions`)
  - 가동 시간 (`sensor.antigravity_cli_uptime`)
- **버튼(Buttons)**:
  - 상태 강제 동기화 (`button.antigravity_cli_sync_status`)
  - 에이전트 재시작 트리거 (`button.antigravity_cli_restart_agent`)
- **커스텀 서비스(Services)**:
  - `antigravity_cli.run_command`: CLI 에이전트에 명령어 전달 및 실행
- **다국어 지원**: 한국어 / 영어 지원

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

---

## ⚙️ 설정 방법 (Configuration)

1. Home Assistant **설정 > 기기 및 서비스 > 통합구성요소 추가**로 이동합니다.
2. `Antigravity CLI`를 검색하여 선택합니다.
3. 안내에 따라 호스트, 포트, API 키를 입력하고 등록을 완료합니다.

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
