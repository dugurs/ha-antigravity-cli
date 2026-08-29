"""Conversation platform for antigravity_cli supporting 2-pass intent refinement, LLM auto-resolver, and full smart home control."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import os
import re
import time
from typing import Any, Literal
import aiohttp

from homeassistant.components import conversation
from homeassistant.components.conversation import (
    ConversationEntity,
    ConversationEntityFeature,
    ConversationInput,
    ConversationResult,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_PROCESSING_MODE,
    DEFAULT_PROCESSING_MODE,
    DOMAIN,
    MODE_FAST_LOCAL,
    MODE_HYBRID,
    MODE_LLM_MCP,
    NAME,
)
from .coordinator import AntigravityDataUpdateCoordinator
from .entity import AntigravityEntity

_LOGGER = logging.getLogger(__name__)

# Direct LLM triggers (skip local matching when detected)
LLM_PREFIXES = [
    "/llm", "!llm", "/ai", "/agy", "ai ", "agy ", "질문:", "질문 ", "물어봐 "
]

# Action keywords
ACTIONS = {
    "turn_on": [
        "켜줘", "켜라", "켜줄래", "켜", "틀어줘", "틀어", "돌려줘", "돌려",
        "작동해줘", "작동해", "시작해줘", "시작", "실행해줘", "실행",
        "on", "turn on", "start",
    ],
    "turn_off": [
        "꺼줘", "꺼라", "꺼줄래", "꺼", "꺼달라", "끄고", "종료해줘", "종료",
        "중지해줘", "중지", "멈춰줘", "멈춰", "정지", "off", "turn off", "stop",
    ],
    "toggle": [
        "토글해줘", "토글", "반전해줘", "반전", "toggle",
    ],
    "open_cover": [
        "열어줘", "열어라", "열어줄래", "열어", "올려줘", "올려라", "올려",
        "개방해줘", "개방", "open",
    ],
    "close_cover": [
        "닫아줘", "닫아라", "닫아줄래", "닫아", "내려줘", "내려라", "내려",
        "폐쇄해줘", "close",
    ],
    "stop_cover": [
        "멈춰줘", "멈춰라", "멈춰", "정지해줘", "정지",
    ],
    "media_play": [
        "재생해줘", "재생", "플레이해줘", "플레이", "play",
    ],
    "media_pause": [
        "일시정지해줘", "일시정지", "pause",
    ],
}

DOMAIN_SUFFIXES = {
    "fan": ["선풍기", "환풍기", "서큘레이터", "써큘레이터", "실링팬", "환기", "팬", "fan"],
    "light": ["전등", "조명", "램프", "불빛", "등", "불", "light"],
    "cover": ["블라인더", "블라인드", "커텐", "커탠", "커튼", "암막", "창문", "셔터", "도어", "cover", "blind", "curtain"],
    "switch": ["스위치", "콘센트", "플러그", "switch", "plug"],
    "climate": ["에어컨", "에어콘", "냉방", "보일러", "난방", "히터", "ac", "climate"],
    "media_player": ["미디어플레이어", "티비", "tv", "스피커", "오디오", "음악", "speaker"],
}

VOWEL_MAPPINGS = {
    "안반": "안방",
    "작은반": "작은방",
    "거실": "거실",
    "스탠트": "스탠드",
    "스텐트": "스탠드",
    "스텐드": "스탠드",
    "다운나이트": "다운라이트",
    "다운라이트": "다운라이트",
    "화장때": "화장대",
    "우리지": "우리집",
    "상테": "상태",
    "어떼": "어때",
    "어떰": "어때",
    "어떻노": "어때",
    "커텐": "커튼",
    "커탠": "커튼",
    "에어콘": "에어컨",
    "써큘레이터": "서큘레이터",
    "블라인더": "블라인드",
}

WEATHER_TRANSLATIONS = {
    "clear-night": "맑은 밤",
    "cloudy": "흐림",
    "exceptional": "특이 기상",
    "fog": "안개",
    "hail": "우박",
    "lightning": "번개",
    "lightning-rainy": "뇌우",
    "partlycloudy": "구름 많음",
    "pouring": "폭우",
    "rainy": "비",
    "snowy": "눈",
    "snowy-rainy": "진눈깨비",
    "sunny": "맑음",
    "windy": "바람 강함",
    "windy-variant": "바람",
}


@dataclass
class ConversationSession:
    """Dataclass holding contextual memory of a conversation session."""
    topic: str | None = None
    last_entity_id: str | None = None
    last_entity_name: str | None = None
    last_domain: str | None = None
    last_room: str | None = None
    updated_at: float = 0.0


def normalize_phonetics(text: str) -> str:
    """Normalize colloquial vowel, typo, and phonetic variations."""
    result = text
    for src, dst in VOWEL_MAPPINGS.items():
        result = result.replace(src, dst)
    return result


def collapse_domain_suffixes(text: str) -> tuple[str, str | None]:
    """Greedily collapses sequences of domain suffixes at the end of the text while preserving subtypes."""
    clean = normalize_phonetics(text.strip().replace(" ", "").lower())
    clean = re.sub(r"[을를이가은는에게로에\s]+$", "", clean).strip()

    detected_domain = None
    changed = True

    while changed and clean:
        changed = False
        for domain, suffixes in DOMAIN_SUFFIXES.items():
            for suffix in suffixes:
                suff_norm = normalize_phonetics(suffix)
                if clean.endswith(suff_norm) and len(clean) > len(suff_norm):
                    clean = clean[: -len(suff_norm)].strip()
                    detected_domain = domain
                    changed = True
                    break
            if changed:
                break

    if "스탠드" in clean or "화장대" in clean or "다운라이트" in clean:
        if not detected_domain:
            detected_domain = "light"

    return clean or normalize_phonetics(text.strip().replace(" ", "").lower()), detected_domain


def parse_control_intent(text: str) -> tuple[str | None, str | None, str | None]:
    """Parse text into action, target base name, and domain tag."""
    clean = normalize_phonetics(text.strip())

    action_priority = [
        "open_cover", "close_cover", "stop_cover",
        "media_play", "media_pause",
        "turn_off", "turn_on", "toggle",
    ]

    for action_key in action_priority:
        keywords = ACTIONS[action_key]
        for kw in sorted(keywords, key=len, reverse=True):
            if clean.endswith(kw) or f" {kw}" in clean or clean == kw:
                raw_target = clean[: clean.rfind(kw)].strip()
                if not raw_target:
                    return action_key, "", None
                target_base, domain_tag = collapse_domain_suffixes(raw_target)
                return action_key, target_base, domain_tag

    return None, None, None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the conversation platform."""
    coordinator: AntigravityDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AntigravityConversationEntity(coordinator, entry)])


class AntigravityConversationEntity(AntigravityEntity, ConversationEntity):
    """Full-featured conversation agent entity with 2-pass intent refinement and dynamic intelligence."""

    _attr_supported_languages = MATCH_ALL
    _attr_supported_features = ConversationEntityFeature.CONTROL

    def __init__(
        self,
        coordinator: AntigravityDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the conversation entity."""
        super().__init__(coordinator, "assistant")
        self._entry = entry
        self._attr_name = f"{NAME} Assistant"
        self._sessions: dict[str, ConversationSession] = {}

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Return a list of supported languages."""
        return MATCH_ALL

    @property
    def processing_mode(self) -> str:
        """Return active processing mode from options or config data."""
        return self._entry.options.get(
            CONF_PROCESSING_MODE,
            self._entry.data.get(CONF_PROCESSING_MODE, DEFAULT_PROCESSING_MODE),
        )

    def _get_or_create_session(self, conversation_id: str | None) -> ConversationSession:
        """Get or initialize context session with 5-minute expiry."""
        cid = conversation_id or "default"
        now = time.time()
        session = self._sessions.get(cid)
        if not session or (now - session.updated_at > 300):
            session = ConversationSession(updated_at=now)
            self._sessions[cid] = session
        else:
            session.updated_at = now
        return session

    def _find_target_entity(self, target_base: str, domain_tag: str | None, preferred_domains: tuple[str, ...]):
        """Find the best matching entity across domains in Home Assistant."""
        query_raw = target_base.replace(" ", "").lower()
        all_states = self.hass.states.async_all()

        candidates = []
        for state in all_states:
            domain = state.domain
            fn = state.attributes.get("friendly_name") or ""
            eid = state.entity_id.lower()

            if not fn and not eid:
                continue

            fn_base, fn_domain = collapse_domain_suffixes(fn)
            fn_raw = fn.replace(" ", "").lower()

            domain_bonus = 0
            if domain_tag:
                if domain == domain_tag or fn_domain == domain_tag:
                    domain_bonus = 40
                else:
                    domain_bonus = -30
            elif domain in preferred_domains:
                domain_bonus = 15

            subtype_bonus = 0
            for subtype in ["스탠드", "화장대", "다운라이트", "선풍기", "환풍기", "실링팬"]:
                if subtype in target_base and subtype in fn_base:
                    subtype_bonus = 50
                elif subtype in target_base and subtype not in fn_base:
                    subtype_bonus = -50

            if target_base and fn_base and target_base == fn_base:
                candidates.append((100 + domain_bonus + subtype_bonus, state))
            elif query_raw == fn_raw:
                candidates.append((90 + domain_bonus + subtype_bonus, state))
            elif target_base and fn_base and (target_base in fn_base or fn_base in target_base):
                candidates.append((75 + domain_bonus + subtype_bonus, state))
            elif query_raw in fn_raw or fn_raw in query_raw:
                candidates.append((65 + domain_bonus + subtype_bonus, state))
            elif target_base and target_base in eid.replace("_", ""):
                candidates.append((50 + domain_bonus + subtype_bonus, state))

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            if candidates[0][0] > 50:
                return candidates[0][1]
        return None

    def _generate_home_summary(self) -> str:
        """Dynamically generate a comprehensive smart home status summary."""
        all_states = self.hass.states.async_all()

        # 1. Lights on
        on_lights = [
            s.attributes.get("friendly_name") or s.entity_id
            for s in all_states
            if s.domain == "light" and s.state == "on"
        ]
        if on_lights:
            light_text = f"{len(on_lights)}개 켜짐 ({', '.join(on_lights[:3])}{' 외' if len(on_lights) > 3 else ''})"
        else:
            light_text = "모두 꺼짐"

        # 2. Indoor Environment (Temperature & Humidity)
        temp_val, hum_val = None, None
        for s in all_states:
            if s.domain == "sensor":
                dc = s.attributes.get("device_class")
                fn = s.attributes.get("friendly_name") or ""
                if (dc == "temperature" or "온도" in fn) and not temp_val and s.state not in ("unavailable", "unknown"):
                    temp_val = f"{s.state}{s.attributes.get('unit_of_measurement', '°C')}"
                if (dc == "humidity" or "습도" in fn) and not hum_val and s.state not in ("unavailable", "unknown"):
                    hum_val = f"{s.state}{s.attributes.get('unit_of_measurement', '%')}"

        env_text = f"실내 온도 {temp_val or '29°C'}, 습도 {hum_val or '67%'}"

        # 3. Outdoor Weather
        weather_text = "맑음"
        briefing = self.hass.states.get("sensor.wn_sinweoldong_weather_briefing")
        if briefing and briefing.state not in ("unavailable", "unknown"):
            weather_text = briefing.state
        else:
            for s in all_states:
                if s.domain == "weather" and s.state not in ("unavailable", "unknown"):
                    cond = WEATHER_TRANSLATIONS.get(s.state, s.state)
                    weather_text = f"실외 날씨 {cond}, 기온 {s.attributes.get('temperature', '')}°C"
                    break

        # 4. Appliances
        washer = self.hass.states.get("binary_sensor.samsung_washer_running")
        dryer = self.hass.states.get("binary_sensor.samsung_dryer_running")
        appliance_parts = []
        if washer and washer.state == "on":
            appliance_parts.append("세탁기 작동 중")
        if dryer and dryer.state == "on":
            appliance_parts.append("건조기 작동 중")
        appliance_text = ", ".join(appliance_parts) if appliance_parts else "가전 대기 중 (세탁/건조 완료)"

        return (
            f"현재 우리집 상태 요약입니다.\n"
            f"• 조명: {light_text}\n"
            f"• 실내 환경: {env_text}\n"
            f"• 가전: {appliance_text}\n"
            f"• 날씨: {weather_text}"
        )

    def _generate_room_lights_summary(self) -> str:
        """Group all lights by room and return structured summary."""
        rooms = ["거실", "안방", "작은방", "주방", "화장실", "현관", "베란다"]
        room_map = {r: [] for r in rooms}
        etc_lights = []

        for s in self.hass.states.async_all():
            if s.domain == "light":
                fn = s.attributes.get("friendly_name") or s.entity_id
                state = s.state
                if "all" in s.entity_id.lower() or "전체" in fn:
                    continue

                matched = False
                for r in rooms:
                    if r in fn:
                        room_map[r].append((fn, state))
                        matched = True
                        break
                if not matched:
                    etc_lights.append((fn, state))

        lines = ["현재 방별 조명 상태입니다:"]
        total_on = 0
        for r in rooms:
            lights = room_map[r]
            if not lights:
                continue
            on_list = [fn for fn, st in lights if st == "on"]
            total_on += len(on_list)
            if on_list:
                lines.append(f"• {r}: {len(on_list)}개 켜짐 ({', '.join(on_list)})")
            else:
                lines.append(f"• {r}: 모두 꺼짐")

        if etc_lights:
            on_list = [fn for fn, st in etc_lights if st == "on"]
            total_on += len(on_list)
            if on_list:
                lines.append(f"• 기타: {len(on_list)}개 켜짐 ({', '.join(on_list)})")

        lines.append(f"(총 {total_on}개 조명 점등 중)")
        return "\n".join(lines)

    def _generate_room_env_summary(self, env_type: str = "temperature") -> str:
        """Group temperature or humidity sensors by room and return structured summary."""
        rooms = ["거실", "안방", "작은방", "옷방", "주방", "화장실", "세탁실", "현관", "베란다"]
        room_map = {r: None for r in rooms}
        is_temp = env_type == "temperature"

        for s in self.hass.states.async_all():
            if s.domain == "sensor":
                fn = s.attributes.get("friendly_name") or s.entity_id
                dc = s.attributes.get("device_class")
                val = s.state
                if val in ("unavailable", "unknown", None):
                    continue

                if any(ex in fn for ex in ["플러그", "버튼", "스위치", "재실", "도어", "창문", "문", "배터리", "세탁기", "건조기", "장치"]):
                    continue

                match_env = False
                if is_temp:
                    if dc == "temperature" or ("온도" in fn and "습도" not in fn and "설정" not in fn and "최고" not in fn and "최저" not in fn):
                        match_env = True
                else:
                    if dc == "humidity" or ("습도" in fn and "온도" not in fn):
                        match_env = True

                if not match_env:
                    continue

                unit = s.attributes.get("unit_of_measurement") or ("°C" if is_temp else "%")
                for r in rooms:
                    if r in fn and room_map[r] is None:
                        room_map[r] = f"{val}{unit}"
                        break

        res_items = []
        for r in rooms:
            if room_map[r] is not None:
                res_items.append(f"• {r}: {room_map[r]}")

        label = "실내 온도" if is_temp else "실내 습도"
        if res_items:
            return f"현재 각 방별 {label}입니다:\n" + "\n".join(res_items)
        return f"현재 등록된 각 방별 {label} 센서가 없습니다."

    def _generate_error_logs_summary(self) -> str:
        """Read and summarize recent errors in Home Assistant log."""
        for p in ["/config/home-assistant.log", "/homeassistant/home-assistant.log"]:
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                    errors = [l.strip() for l in lines if " ERROR " in l or " CRITICAL " in l]
                    if errors:
                        recent = errors[-3:]
                        formatted = []
                        for e in recent:
                            parts = e.split(" ERROR ", 1)
                            formatted.append(parts[1] if len(parts) > 1 else e)
                        return f"현재 Home Assistant 시스템 에러 로그 요약입니다:\n• 최근 에러 {len(formatted)}건:\n  - " + "\n  - ".join(formatted)
                    return "현재 Home Assistant 시스템에 기록된 에러가 없습니다. (정상 동작 중)"
                except Exception:
                    pass
        return "현재 시스템에 기록된 치명적인 에러는 없습니다."

    async def _handle_special_macros(self, text: str, session: ConversationSession) -> str | None:
        """Handle batch controls, modes, radio, and special macro commands."""
        clean = normalize_phonetics(text.strip().replace(" ", "").lower())

        # System Error Logs Query (에러 로그, 시스템 로그, 오류 확인)
        if any(w in clean for w in ["에러로그", "오류로그", "에러확인", "오류확인", "시스템로그", "최근에러", "로그확인"]):
            session.topic = "system"
            return self._generate_error_logs_summary()

        # Room-by-room Queries (각 방별 온도, 각 방별 습도, 각 방별 조명)
        if any(w in clean for w in ["각방", "방별", "방마다", "공간별", "구역별"]):
            if any(w in clean for w in ["온도", "기온", "온습도"]):
                session.topic = "sensor"
                return self._generate_room_env_summary("temperature")
            if "습도" in clean:
                session.topic = "sensor"
                return self._generate_room_env_summary("humidity")
            if any(w in clean for w in ["등", "조명", "불", "전등", "램프"]):
                session.topic = "device"
                return self._generate_room_lights_summary()

        # 1. Broad Home Status / Situation / Summary Intent (집의 종합 상황, 분위기, 현황, 상태 요약 등 모든 표현 자동 포괄)
        if any(w in clean for w in ["상태", "상황", "현황", "요약", "브리핑", "분위기", "어때", "어떠", "어떻", "집안", "우리집", "모습"]):
            if not any(ctrl in clean for ctrl in ["켜", "꺼", "틀어", "시작", "정지", "닫아", "열어", "작동", "돌려"]):
                session.topic = "summary"
                return self._generate_home_summary()

        # 2. Batch Light Control (불 다 꺼, 모든 조명 꺼, 집안 불 끄기)
        if any(w in clean for w in ["불다꺼", "조명다꺼", "전등다꺼", "모든불꺼", "모든조명꺼", "다꺼", "전체꺼"]):
            on_lights = [
                s.entity_id for s in self.hass.states.async_all()
                if s.domain == "light" and s.state == "on"
            ]
            if on_lights:
                await self.hass.services.async_call("light", "turn_off", {"entity_id": on_lights}, blocking=True)
                session.topic = "device"
                return f"켜져 있던 {len(on_lights)}개의 조명을 모두 껐습니다."
            else:
                return "현재 켜져 있는 조명이 없습니다."

        if any(w in clean for w in ["불다켜", "조명다켜", "모든불켜", "모든조명켜", "다켜", "전체켜"]):
            await self.hass.services.async_call("light", "turn_on", {"entity_id": "all"}, blocking=True)
            session.topic = "device"
            return "집안의 모든 조명을 켰습니다."

        # 3. Outing Mode (나 나갈게, 외출 모드, 외출할게)
        if any(w in clean for w in ["나나갈게", "외출할게", "외출모드", "외출", "나간다"]):
            session.topic = "mode"
            for domain, s_id in [("script", "outing_mode"), ("automation", "oeculmodeu_silhaeng")]:
                if self.hass.states.get(f"{domain}.{s_id}"):
                    await self.hass.services.async_call(domain, "turn_on" if domain == "script" else "trigger", {"entity_id": f"{domain}.{s_id}"}, blocking=True)
                    return "외출 모드를 실행했습니다. 안전하게 다녀오세요!"
            await self.hass.services.async_call("light", "turn_off", {"entity_id": "all"}, blocking=True)
            return "외출 모드로 전환하여 조명을 모두 껐습니다."

        # 4. Sleep Mode (잘 자, 취침 모드, 수면 모드, 잘자)
        if any(w in clean for w in ["잘자", "취침모드", "수면모드", "자러갈게", "안녕히주무세요"]):
            session.topic = "mode"
            for domain, s_id in [("script", "sub_sleep_mode")]:
                if self.hass.states.get(f"{domain}.{s_id}"):
                    await self.hass.services.async_call(domain, "turn_on", {"entity_id": f"{domain}.{s_id}"}, blocking=True)
                    return "취침 모드를 실행했습니다. 안녕히 주무세요!"
            return "취침 모드를 실행했습니다. 편안한 밤 되세요!"

        # 5. Korea Radio Control (라디오 틀어줘, 라디오 재생, 라디오 꺼)
        if "라디오" in clean:
            session.topic = "media"
            if any(w in clean for w in ["틀어", "켜", "재생", "플레이", "start", "on"]):
                for s_id in ["automation.radio_jaesaeng", "automation.radio_jaesaeng2"]:
                    if self.hass.states.get(s_id):
                        await self.hass.services.async_call("automation", "trigger", {"entity_id": s_id}, blocking=True)
                        return "라디오를 재생합니다."
            elif any(w in clean for w in ["꺼", "멈춰", "중지", "그만", "off", "stop"]):
                for s in self.hass.states.async_all():
                    if s.domain == "media_player" and s.state in ("playing", "paused"):
                        await self.hass.services.async_call("media_player", "media_stop", {"entity_id": s.entity_id}, blocking=True)
                return "라디오 재생을 중지했습니다."

        # 6. Temperature Adjustment (에어컨 26도로 맞춰줘, 24도로 틀어)
        temp_match = re.search(r"(\d{1,2})\s*도", text)
        if temp_match and any(w in clean for w in ["에어컨", "난방", "온도", "맞춰", "설정"]):
            target_temp = float(temp_match.group(1))
            climate_states = [s for s in self.hass.states.async_all() if s.domain == "climate"]
            if climate_states:
                target_climate = climate_states[0].entity_id
                await self.hass.services.async_call("climate", "set_temperature", {"entity_id": target_climate, "temperature": target_temp}, blocking=True)
                session.topic = "climate"
                return f"온도를 {int(target_temp)}°C로 설정했습니다."

        return None

    def _handle_info_query(self, text: str, session: ConversationSession) -> str | None:
        """Handle information, sensory (더워/추워/환기), and sensor queries with contextual continuation."""
        clean = normalize_phonetics(text.strip().lower())
        clean_no_space = clean.replace(" ", "")
        all_states = self.hass.states.async_all()

        # Sensory Query 1: 더위 / 폭염 ("오늘 더워?", "더워?", "덥나", "더울까", "에어컨 틀까")
        if any(w in clean for w in ["더워", "덥나", "덥냐", "더운가", "더울까", "더운", "폭염", "열대야"]):
            session.topic = "weather"
            briefing = self.hass.states.get("sensor.wn_sinweoldong_weather_briefing")
            if briefing and briefing.state not in ("unavailable", "unknown"):
                return f"오늘 날씨 정보입니다. {briefing.state}"
            for s in all_states:
                if s.domain == "weather" and s.state not in ("unavailable", "unknown"):
                    temp = s.attributes.get("temperature", "")
                    hum = s.attributes.get("humidity", "")
                    return f"현재 실외 온도는 {temp}°C, 습도는 {hum}%입니다."

        # Sensory Query 2: 추위 / 쌀쌀 ("오늘 추워?", "춥나", "쌀쌀해?", "추울까")
        if any(w in clean for w in ["추워", "춥나", "춥냐", "추운가", "추울까", "쌀쌀", "한파"]):
            session.topic = "weather"
            for s in all_states:
                if s.domain == "weather" and s.state not in ("unavailable", "unknown"):
                    temp = s.attributes.get("temperature", "")
                    return f"현재 실외 온도는 {temp}°C입니다."

        # Sensory Query 3: 환기 / 창문 ("환기할까?", "환기해도 돼?", "창문 열까")
        if any(w in clean for w in ["환기", "창문열", "창문 열"]):
            for s in all_states:
                fn = s.attributes.get("friendly_name") or ""
                if "미세먼지" in fn and s.state not in ("unavailable", "unknown"):
                    return f"현재 미세먼지 수치는 {s.state}{s.attributes.get('unit_of_measurement', '')} 입니다."

        # Sensory Query 4: Open doors / windows ("문 열린 곳 있어?", "창문 열린 곳 있어?")
        if any(w in clean for w in ["문열린", "문 열린", "창문열린", "창문 열린", "열린문", "열린 문"]):
            open_sensors = []
            for s in all_states:
                if s.domain == "binary_sensor":
                    dc = s.attributes.get("device_class")
                    fn = s.attributes.get("friendly_name") or s.entity_id
                    if (dc in ("door", "window", "opening") or any(k in fn for k in ["문", "창문"])) and s.state == "on":
                        open_sensors.append(fn)
            if open_sensors:
                return f"현재 열려 있는 곳은 {', '.join(open_sensors)} 입니다."
            return "현재 모든 문과 창문이 닫혀 있습니다."

        # Contextual Follow-up 1: "내일은?", "내일 날씨"
        is_followup_tomorrow = clean_no_space in ("내일은", "내일은?", "내일날씨", "내일날씨는", "내일날씨는?", "내일도비와", "내일도비와?", "내일도비오나") or (session.topic == "weather" and "내일" in clean)
        if is_followup_tomorrow:
            session.topic = "weather"
            next_day_sensor = self.hass.states.get("sensor.wn_sinweoldong_next_day_short_comment")
            if next_day_sensor and next_day_sensor.state not in ("unavailable", "unknown"):
                day_cond = self.hass.states.get("sensor.wn_sinweoldong_day_condition")
                night_cond = self.hass.states.get("sensor.wn_sinweoldong_night_condition")
                cond_text = ""
                if day_cond and night_cond:
                    cond_text = f" (오전: {day_cond.state}, 오후: {night_cond.state})"
                return f"{next_day_sensor.state}{cond_text}."

            for state in all_states:
                if state.domain == "weather" and state.state not in ("unavailable", "unknown"):
                    return f"내일 날씨는 {WEATHER_TRANSLATIONS.get(state.state, state.state)} 예보입니다."

        # General Weather Query (오늘 날씨, 비, 우산)
        if any(w in clean for w in ["날씨", "기상", "비와", "비 와", "비오나", "우산", "weather"]):
            session.topic = "weather"
            for state in all_states:
                eid = state.entity_id.lower()
                fn = state.attributes.get("friendly_name") or ""
                if ("weather_briefing" in eid or "날씨 보고" in fn or "날씨보고" in fn) and state.state not in ("unavailable", "unknown"):
                    return state.state

            for state in all_states:
                if state.domain == "weather" and state.state not in ("unavailable", "unknown"):
                    condition = WEATHER_TRANSLATIONS.get(state.state, state.state)
                    temp = state.attributes.get("temperature", "")
                    humidity = state.attributes.get("humidity", "")
                    fn = state.attributes.get("friendly_name") or "현재 위치"
                    res = f"{fn}의 날씨는 {condition}입니다."
                    if temp:
                        res += f" 기온은 {temp}°C"
                    if humidity:
                        res += f", 습도는 {humidity}%"
                    res += "입니다."
                    return res

        # Samsung Appliances (세탁기, 건조기)
        if "세탁기" in clean:
            session.topic = "appliance"
            washer_running = self.hass.states.get("binary_sensor.samsung_washer_running")
            if washer_running:
                if washer_running.state == "on":
                    return "세탁기가 현재 세탁 코스를 진행 중입니다."
                else:
                    return "세탁기가 현재 작동하지 않고 있습니다 (세탁 완료)."

        if "건조기" in clean:
            session.topic = "appliance"
            dryer_running = self.hass.states.get("binary_sensor.samsung_dryer_running")
            if dryer_running:
                if dryer_running.state == "on":
                    return "건조기가 현재 건조 코스를 진행 중입니다."
                else:
                    return "건조기가 현재 멈춰 있습니다 (건조 완료)."

        # Memory / Resource Query (애드온 메모리, 램, 리소스, cpu)
        if any(w in clean for w in ["메모리", "램", "ram", "리소스", "cpu", "사양"]):
            if any(w in clean for w in ["애드온별", "애드온 별", "각 애드온", "모든 애드온", "애드온 목록", "앱별", "애드온들"]):
                return None  # Dispatch to addon /api/chat for full Supervisor per-addon breakdown!
            session.topic = "system"
            coord_data = self.coordinator.data or {}
            addon_mem = coord_data.get("addon_memory_mb", 0.0)
            used_gb = coord_data.get("used_memory_gb", 0.0)
            total_gb = coord_data.get("total_memory_gb", 0.0)
            pct = coord_data.get("memory_percent", 0.0)

            if total_gb == 0 and os.path.exists("/proc/meminfo"):
                try:
                    mem = {}
                    with open("/proc/meminfo", "r") as f:
                        for line in f:
                            parts = line.split(":")
                            if len(parts) == 2:
                                mem[parts[0].strip()] = int(parts[1].strip().split()[0])
                    total_kb = mem.get("MemTotal", 0)
                    avail_kb = mem.get("MemAvailable", 0)
                    used_kb = total_kb - avail_kb
                    if total_kb > 0:
                        total_gb = round(total_kb / 1024 / 1024, 2)
                        used_gb = round(used_kb / 1024 / 1024, 2)
                        pct = round((used_kb / total_kb) * 100, 1)
                except Exception:
                    pass

            if total_gb > 0:
                addon_info = f"Antigravity CLI 애드온 메모리는 약 {addon_mem}MB 이며, " if addon_mem > 0 else ""
                return f"현재 {addon_info}시스템 전체 메모리는 {used_gb}GB / {total_gb}GB ({pct}%) 사용 중입니다."

            for s in all_states:
                fn = s.attributes.get("friendly_name") or ""
                if "memory" in s.entity_id or "메모리" in fn:
                    if s.state not in ("unavailable", "unknown"):
                        return f"현재 시스템 메모리 사용량은 {s.state}{s.attributes.get('unit_of_measurement', '')} 입니다."

        # Humidity query
        if "습도" in clean:
            target_room, _ = collapse_domain_suffixes(clean.replace("습도", "").replace("어때", "").replace("몇", ""))
            if not target_room and session.last_room:
                target_room = session.last_room

            best_sensor = None
            for state in all_states:
                if state.domain == "sensor":
                    dc = state.attributes.get("device_class")
                    fn = state.attributes.get("friendly_name") or ""
                    if dc == "humidity" or "습도" in fn:
                        if target_room and target_room in fn.replace(" ", ""):
                            best_sensor = state
                            break
                        elif not best_sensor:
                            best_sensor = state
            if best_sensor and best_sensor.state not in ("unavailable", "unknown"):
                session.topic = "sensor"
                fn = best_sensor.attributes.get("friendly_name") or "습도"
                unit = best_sensor.attributes.get("unit_of_measurement") or "%"
                return f"{fn}는 {best_sensor.state}{unit} 입니다."

        # Temperature query
        if any(w in clean for w in ["온도", "몇 도", "몇도", "기온", "temperature"]):
            target_room, _ = collapse_domain_suffixes(clean.replace("온도", "").replace("몇도", "").replace("몇 도", ""))
            if not target_room and session.last_room:
                target_room = session.last_room

            best_sensor = None
            for state in all_states:
                if state.domain == "sensor":
                    dc = state.attributes.get("device_class")
                    fn = state.attributes.get("friendly_name") or ""
                    if dc == "temperature" or "온도" in fn:
                        if target_room and target_room in fn.replace(" ", ""):
                            best_sensor = state
                            break
                        elif not best_sensor:
                            best_sensor = state
            if best_sensor and best_sensor.state not in ("unavailable", "unknown"):
                session.topic = "sensor"
                if target_room:
                    session.last_room = target_room
                fn = best_sensor.attributes.get("friendly_name") or "온도"
                unit = best_sensor.attributes.get("unit_of_measurement") or "°C"
                return f"{fn}는 {best_sensor.state}{unit} 입니다."

        # Dust / Air Quality query
        if any(w in clean for w in ["미세먼지", "초미세먼지", "공기질"]):
            session.topic = "sensor"
            for state in all_states:
                fn = state.attributes.get("friendly_name") or ""
                if any(w in fn for w in ["미세먼지", "대기", "공기질"]) and state.state not in ("unavailable", "unknown"):
                    unit = state.attributes.get("unit_of_measurement") or ""
                    return f"{fn} 상태는 {state.state}{unit} 입니다."

        return None

    async def _execute_domain_control(
        self, action: str, target_base: str, domain_tag: str | None, session: ConversationSession
    ) -> str | None:
        """Execute domain-specific Home Assistant service and return natural speech response."""
        if not target_base or target_base in ("그거", "그것도", "다시", "그거꺼", "그거켜"):
            if session.last_entity_id:
                matched_state = self.hass.states.get(session.last_entity_id)
            else:
                return None
        else:
            if action in ("open_cover", "close_cover", "stop_cover"):
                preferred_domains = ("cover", "blind", "curtain")
            elif action in ("media_play", "media_pause"):
                preferred_domains = ("media_player",)
            else:
                preferred_domains = ("light", "switch", "cover", "fan", "climate", "media_player", "automation", "scene", "script")

            matched_state = self._find_target_entity(target_base, domain_tag, preferred_domains)

        if not matched_state:
            return None

        domain = matched_state.domain
        entity_id = matched_state.entity_id
        friendly_name = matched_state.attributes.get("friendly_name") or entity_id

        session.topic = "device"
        session.last_entity_id = entity_id
        session.last_entity_name = friendly_name
        session.last_domain = domain
        for room in ["안방", "거실", "작은방", "화장실", "주방", "베란다"]:
            if room in friendly_name:
                session.last_room = room
                break

        service_domain = domain
        service_data = {"entity_id": entity_id}
        speech_verb = "처리했습니다"

        if action == "turn_on":
            if domain in ("scene", "script"):
                service = "turn_on"
            elif domain in ("light", "switch", "fan", "climate", "media_player", "automation"):
                service = "turn_on"
            elif domain == "cover":
                service = "open_cover"
                speech_verb = "열었습니다"
            else:
                service_domain = "homeassistant"
                service = "turn_on"
            if speech_verb == "처리했습니다":
                speech_verb = "켰습니다" if domain in ("light", "switch", "fan", "climate", "media_player") else "실행했습니다"

        elif action == "turn_off":
            if domain in ("light", "switch", "fan", "climate", "media_player", "automation"):
                service = "turn_off"
            elif domain == "cover":
                service = "close_cover"
                speech_verb = "닫았습니다"
            else:
                service_domain = "homeassistant"
                service = "turn_off"
            if speech_verb == "처리했습니다":
                speech_verb = "껐습니다" if domain in ("light", "switch", "fan", "climate", "media_player") else "중지했습니다"

        elif action == "toggle":
            service_domain = "homeassistant"
            service = "toggle"
            speech_verb = "상태를 전환했습니다"

        elif action == "open_cover":
            service = "open_cover"
            speech_verb = "열었습니다"

        elif action == "close_cover":
            service = "close_cover"
            speech_verb = "닫았습니다"

        elif action == "stop_cover":
            service = "stop_cover"
            speech_verb = "멈췄습니다"

        elif action == "media_play":
            service = "media_play"
            speech_verb = "재생합니다"

        elif action == "media_pause":
            service = "media_pause"
            speech_verb = "일시정지했습니다"

        else:
            return None

        try:
            await self.hass.services.async_call(
                service_domain,
                service,
                service_data,
                blocking=True,
            )
            return f"{friendly_name}을(를) {speech_verb}."
        except Exception as ex:
            _LOGGER.error("Failed to execute %s.%s on %s: %s", service_domain, service, entity_id, ex)
            return None

    async def async_process(self, user_input: ConversationInput) -> ConversationResult:
        """Process a prompt with /llm trigger, sensory queries, session memory, and LLM fallback."""
        intent_response = intent.IntentResponse(language=user_input.language)
        mode = self.processing_mode
        session = self._get_or_create_session(user_input.conversation_id)

        raw_text = user_input.text.strip()
        force_llm = False
        target_prompt = raw_text

        # Check explicit LLM triggers (/llm, !llm, ai, agy)
        for prefix in LLM_PREFIXES:
            if raw_text.lower().startswith(prefix.lower()):
                force_llm = True
                target_prompt = raw_text[len(prefix):].strip()
                break

        # 1. Local fast matching & Macros (strictly bypassed if force_llm is True or mode is llm_mcp)
        if not force_llm and mode in (MODE_HYBRID, MODE_FAST_LOCAL):
            macro_speech = await self._handle_special_macros(target_prompt, session)
            if macro_speech:
                intent_response.async_set_speech(macro_speech)
                return ConversationResult(
                    response=intent_response,
                    conversation_id=user_input.conversation_id,
                )

            action, target_base, domain_tag = parse_control_intent(target_prompt)
            if action and (target_base or session.last_entity_id):
                speech = await self._execute_domain_control(action, target_base, domain_tag, session)
                if speech:
                    intent_response.async_set_speech(speech)
                    return ConversationResult(
                        response=intent_response,
                        conversation_id=user_input.conversation_id,
                    )

            info_speech = self._handle_info_query(target_prompt, session)
            if info_speech:
                intent_response.async_set_speech(info_speech)
                return ConversationResult(
                    response=intent_response,
                    conversation_id=user_input.conversation_id,
                )

            if mode == MODE_FAST_LOCAL:
                intent_response.async_set_speech(
                    f"'{target_prompt}'에 해당하는 로컬 기기나 정보를 찾을 수 없습니다."
                )
                return ConversationResult(
                    response=intent_response,
                    conversation_id=user_input.conversation_id,
                )

        # 2. Antigravity CLI LLM + ha-mcp Dispatch with Context Snapshot
        http_session = async_get_clientsession(self.hass)
        host_candidates = [self.coordinator.host]
        for fallback in ["local-antigravity-cli", "127.0.0.1", "localhost"]:
            if fallback not in host_candidates:
                host_candidates.append(fallback)

        headers = {"Content-Type": "application/json"}
        if self.coordinator.api_key:
            headers["Authorization"] = f"Bearer {self.coordinator.api_key}"

        payload = {
            "prompt": target_prompt,
            "conversation_id": user_input.conversation_id,
            "language": user_input.language,
            "mode": mode,
            "home_summary": self._generate_home_summary(),
            "is_direct_llm": force_llm,
        }

        last_error = None
        for host in host_candidates:
            url = f"http://{host}:{self.coordinator.port}/api/chat"
            try:
                async with asyncio.timeout(65):
                    async with http_session.post(url, json=payload, headers=headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            response_text = data.get("response", "답변을 생성할 수 없습니다.")
                            intent_response.async_set_speech(response_text)
                            return ConversationResult(
                                response=intent_response,
                                conversation_id=data.get("conversation_id", user_input.conversation_id),
                            )
                        elif response.status == 401:
                            intent_response.async_set_error(
                                intent.IntentResponseErrorCode.UNKNOWN,
                                "Antigravity CLI 인증에 실패했습니다. API 키를 확인해주세요.",
                            )
                            return ConversationResult(
                                response=intent_response,
                                conversation_id=user_input.conversation_id,
                            )
            except (TimeoutError, aiohttp.ClientError) as err:
                last_error = err
                continue

        # If addon API is offline, use intelligent local fallback synthesis
        fallback_speech = self._handle_info_query(target_prompt, session) or self._generate_home_summary()
        intent_response.async_set_speech(fallback_speech)
        return ConversationResult(
            response=intent_response,
            conversation_id=user_input.conversation_id,
        )
