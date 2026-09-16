"""Conversation platform for antigravity_cli supporting 2-pass intent refinement, LLM auto-resolver, and full smart home control."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Literal

import aiohttp
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
    NAME,
)
from .coordinator import AntigravityDataUpdateCoordinator
from .entity import AntigravityEntity

_LOGGER = logging.getLogger(__name__)

# Direct LLM triggers (skip local matching when detected)
LLM_PREFIXES = ["/llm", "!llm", "/ai", "/agy", "ai ", "agy ", "질문:", "질문 ", "물어봐 "]

ROOMS = ["거실", "안방", "작은방", "옷방", "주방", "화장실", "세탁실", "현관", "베란다"]

# Each device-type category names 1+ candidate HA domains, checked in no
# particular priority order -- which domain a given appliance actually lives
# under varies by house (a boiler might be a switch relay or a real climate
# entity; a bathroom fan might be fan/climate/switch), so resolution below
# scores every domain in the tuple instead of assuming just one.
DEVICE_CATEGORIES: dict[str, dict[str, Any]] = {
    "light": {
        "suffixes": ["전등", "조명", "램프", "불빛", "등", "불", "light"],
        "domains": ("light",),
    },
    "fan": {
        "suffixes": ["선풍기", "환풍기", "서큘레이터", "써큘레이터", "실링팬", "환기", "팬", "fan"],
        "domains": ("fan", "climate", "switch"),
    },
    "cover": {
        "suffixes": [
            "블라인더",
            "블라인드",
            "커텐",
            "커탠",
            "커튼",
            "암막",
            "창문",
            "셔터",
            "도어",
            "cover",
            "blind",
            "curtain",
        ],
        "domains": ("cover",),
    },
    "climate": {
        "suffixes": ["에어컨", "에어콘", "냉방", "난방", "ac", "climate"],
        "domains": ("climate", "switch"),
    },
    "humidifier": {"suffixes": ["가습기", "제습기"], "domains": ("humidifier", "switch")},
    # Turning one of these OFF always goes through the confirmation gate
    # below (see _execute_domain_control) -- boiler/heater/outlet mishaps
    # have real consequences, unlike a light or fan.
    "appliance": {
        "suffixes": ["보일러", "히터", "온열기", "전기스토브", "콘센트", "플러그"],
        "domains": ("switch", "climate"),
    },
    "switch": {"suffixes": ["스위치", "switch"], "domains": ("switch",)},
    "media_player": {
        "suffixes": ["미디어플레이어", "티비", "tv", "스피커", "오디오", "음악", "speaker"],
        "domains": ("media_player",),
    },
}

_WHOLE_HOUSE_WORDS = ("전체", "다", "모두", "모든")

# Only these domains are ever real control targets -- excludes a device's own
# diagnostic/helper entities (update/button/number/select/sensor), which
# routinely share the exact same friendly_name as the actual controllable
# entity (e.g. update.dress_plug and switch.dress_plug both "옷방 플러그").
_CONTROLLABLE_DOMAINS = (
    "light",
    "switch",
    "cover",
    "fan",
    "climate",
    "media_player",
    "humidifier",
    "automation",
    "scene",
    "script",
)

_AFFIRMATIVE_WORDS = ("응", "네", "예", "그래", "오케이", "ok", "yes")
_NEGATIVE_WORDS = ("아니", "아니오", "아니요", "no", "취소")

_TEMPERATURE_RE = re.compile(r"(\d{1,2})\s*도")
_PERCENT_RE = re.compile(r"(\d{1,3})\s*(?:퍼센트|%)")

# Compound commands share one action across 2+ device types in one sentence
# ("안방 등하고 선풍기 켜줘") -- split on the first connector found.
_COMPOUND_CONNECTORS = ["하고", "이랑", "랑", "그리고", ","]

# Action keywords
ACTIONS = {
    "turn_on": [
        "켜줘",
        "켜라",
        "켜줄래",
        "켜",
        "틀어줘",
        "틀어",
        "돌려줘",
        "돌려",
        "작동해줘",
        "작동해",
        "시작해줘",
        "시작",
        "실행해줘",
        "실행",
        "on",
        "turn on",
        "start",
    ],
    "turn_off": [
        "꺼줘",
        "꺼라",
        "꺼줄래",
        "꺼",
        "꺼달라",
        "끄고",
        "종료해줘",
        "종료",
        "중지해줘",
        "중지",
        "멈춰줘",
        "멈춰",
        "정지",
        "off",
        "turn off",
        "stop",
    ],
    "toggle": [
        "토글해줘",
        "토글",
        "반전해줘",
        "반전",
        "toggle",
    ],
    "open_cover": [
        "열어줘",
        "열어라",
        "열어줄래",
        "열어",
        "올려줘",
        "올려라",
        "올려",
        "개방해줘",
        "개방",
        "open",
    ],
    "close_cover": [
        "닫아줘",
        "닫아라",
        "닫아줄래",
        "닫아",
        "내려줘",
        "내려라",
        "내려",
        "폐쇄해줘",
        "close",
    ],
    "stop_cover": [
        "멈춰줘",
        "멈춰라",
        "멈춰",
        "정지해줘",
        "정지",
    ],
    "media_play": [
        "재생해줘",
        "재생",
        "플레이해줘",
        "플레이",
        "play",
    ],
    "media_pause": [
        "일시정지해줘",
        "일시정지",
        "pause",
    ],
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
    """Local-fallback-only contextual memory.

    The addon's own conversation_id-based session (session_manager.py) is
    authoritative whenever the addon is reachable -- this exists purely so
    the local fallback path (see async_process()) has continuity across
    turns during an addon outage: a bare follow-up ("그거 꺼"), a pending
    dangerous-appliance confirmation, or a remembered room for "습도는?".
    """

    topic: str | None = None
    last_entity_id: str | None = None
    last_room: str | None = None
    pending_confirm: dict | None = None
    updated_at: float = 0.0


def normalize_phonetics(text: str) -> str:
    """Normalize colloquial vowel, typo, and phonetic variations."""
    result = text
    for src, dst in VOWEL_MAPPINGS.items():
        result = result.replace(src, dst)
    return result


def collapse_domain_suffixes(text: str) -> tuple[str, str | None]:
    """Greedily collapses sequences of device-category suffixes at the end
    of the text while preserving subtypes; returns (remaining_text, category)."""
    clean = normalize_phonetics(text.strip().replace(" ", "").lower())
    clean = re.sub(r"[을를이가은는에게로에\s]+$", "", clean).strip()

    detected_category = None
    changed = True

    while changed and clean:
        changed = False
        for category, spec in DEVICE_CATEGORIES.items():
            for suffix in spec["suffixes"]:
                suff_norm = normalize_phonetics(suffix)
                if clean.endswith(suff_norm) and len(clean) > len(suff_norm):
                    clean = clean[: -len(suff_norm)].strip()
                    detected_category = category
                    changed = True
                    break
            if changed:
                break

    if "스탠드" in clean or "화장대" in clean or "다운라이트" in clean:
        if not detected_category:
            detected_category = "light"

    return clean or normalize_phonetics(text.strip().replace(" ", "").lower()), detected_category


def _strip_setting_words(text: str) -> str:
    """Remove trailing "맞춰줘"/"설정"/particle fragments left after pulling
    a number (temperature or percentage) out of a control phrase."""
    for w in [
        "으로맞춰줘",
        "으로맞춰",
        "으로설정해줘",
        "으로설정",
        "으로해줘",
        "맞춰줘",
        "맞춰",
        "설정해줘",
        "설정",
        "해줘",
        "으로",
        "로",
    ]:
        text = text.replace(w, "")
    return text


def _split_compound_target(raw_target: str) -> list[str]:
    """Split a compound target phrase on the first connector found
    ("안방 등하고 선풍기" -> ["안방 등", "선풍기"]), propagating a leading
    room name from the first clause to the second if the second doesn't
    name its own room -- compound commands usually share one room, stated
    only once. Falls back to a single-item list when no connector is found.
    """
    for conn in _COMPOUND_CONNECTORS:
        idx = raw_target.find(conn)
        if idx > 0:
            left = raw_target[:idx].strip()
            right = raw_target[idx + len(conn) :].strip()
            if left and right:
                left_flat = left.replace(" ", "")
                right_flat = right.replace(" ", "")
                shared_room = next((r for r in ROOMS if left_flat.startswith(r)), None)
                if shared_room and not any(right_flat.startswith(r) for r in ROOMS):
                    right = f"{shared_room} {right}"
                return [left, right]
    return [raw_target]


# A relative-delay expression ("5초 후에", "10분 뒤", "1시간 있다가") means the
# addon's scheduler needs to handle this command, not an instant local
# turn_on/turn_off match -- without this guard "안방 등 5초 후에 꺼줘" matched
# "꺼줘" and executed turn_off immediately, silently dropping the delay.
_DELAY_PHRASE_RE = re.compile(r"\d+\s*(?:초|분|시간)\s*(?:뒤|후|있다가|있으면|있다)")

# "예약 실행 목록 보여줘" (list pending scheduled commands) is a QUESTION, but
# the keyword check below isn't anchored to the end of the sentence, so this
# guard keeps such questions from being treated as a control command.
_SCHEDULE_QUERY_WORDS = (
    "목록",
    "리스트",
    "몇개",
    "몇 개",
    "개수",
    "뭐있",
    "뭐 있",
    "보여줘",
    "알려줘",
    "확인",
)


def _is_schedule_query(text: str) -> bool:
    clean = text.replace(" ", "")
    if "예약" not in clean:
        return False
    if any(w.replace(" ", "") in clean for w in _SCHEDULE_QUERY_WORDS):
        return True
    return text.rstrip().endswith("?")


def _is_entity_on(state) -> bool:
    """State-aware "is this currently on" check used by toggle -- a cover's
    `state` is open/closed, a climate/media_player's is its own mode string
    (hvac mode, playing/idle/...), never literally "on"."""
    if state.domain == "cover":
        return state.state == "open"
    if state.domain in ("media_player", "climate"):
        return state.state not in ("off", "unavailable", "unknown")
    return state.state == "on"


def _service_for_action(domain: str, action: str) -> tuple[str | None, str | None, str | None]:
    """Map (domain, action) to (service_domain, service, speech_verb)."""
    if action == "turn_on":
        if domain == "cover":
            return "cover", "open_cover", "열었습니다"
        if domain in (
            "scene",
            "script",
            "light",
            "switch",
            "fan",
            "climate",
            "media_player",
            "automation",
            "humidifier",
        ):
            verb = (
                "켰습니다"
                if domain in ("light", "switch", "fan", "climate", "media_player", "humidifier")
                else "실행했습니다"
            )
            return domain, "turn_on", verb
        return "homeassistant", "turn_on", "켰습니다"
    if action == "turn_off":
        if domain == "cover":
            return "cover", "close_cover", "닫았습니다"
        if domain in (
            "light",
            "switch",
            "fan",
            "climate",
            "media_player",
            "automation",
            "humidifier",
        ):
            return domain, "turn_off", "껐습니다"
        return "homeassistant", "turn_off", "껐습니다"
    if action == "open_cover":
        return "cover", "open_cover", "열었습니다"
    if action == "close_cover":
        return "cover", "close_cover", "닫았습니다"
    if action == "stop_cover":
        return "cover", "stop_cover", "멈췄습니다"
    if action == "media_play":
        return "media_player", "media_play", "재생합니다"
    if action == "media_pause":
        return "media_player", "media_pause", "일시정지했습니다"
    return None, None, None


def _parse_sse_chat_response(raw_text: str) -> tuple[str | None, str | None]:
    """Extract (final speech text, conversation id) from the addon's
    /api/chat body.

    That endpoint always streams Server-Sent Events -- a bare
    `await response.json()` against it raises aiohttp.ContentTypeError
    every time. The payload here always comes from stream_mode's default
    (1, the fast dispatcher: no `stream_mode` key is ever put in the
    request payload below), which yields exactly one "text" event already
    holding the complete answer -- so reading the whole body at once and
    taking that event is equivalent to a real incremental stream for this
    single conversation turn.
    """
    response_text = None
    conversation_id = None
    for block in raw_text.split("\n\n"):
        block = block.strip()
        if not block.startswith("data:"):
            continue
        try:
            event = json.loads(block[len("data:") :].strip())
        except (json.JSONDecodeError, ValueError):
            continue
        event_type = event.get("type")
        if event_type == "text" and event.get("content"):
            response_text = event["content"]
        elif event_type == "session_init" and event.get("content"):
            conversation_id = event["content"]
    return response_text, conversation_id


def parse_control_intent(text: str) -> tuple[str | None, list[tuple[str, str | None]]]:
    """Parse text into (action, clauses), where clauses is one or more
    (target_base, category) pairs sharing the same trailing action verb --
    2+ only for a compound command ("안방 등하고 선풍기 켜줘")."""
    if _DELAY_PHRASE_RE.search(text) or _is_schedule_query(text):
        return None, []
    clean = normalize_phonetics(text.strip())

    action_priority = [
        "open_cover",
        "close_cover",
        "stop_cover",
        "media_play",
        "media_pause",
        "turn_off",
        "turn_on",
        "toggle",
    ]

    for action_key in action_priority:
        keywords = ACTIONS[action_key]
        for kw in sorted(keywords, key=len, reverse=True):
            if clean.endswith(kw) or f" {kw}" in clean or clean == kw:
                raw_target = clean[: clean.rfind(kw)].strip()
                if not raw_target:
                    return action_key, [("", None)]
                segments = _split_compound_target(raw_target)
                clauses = [collapse_domain_suffixes(seg) for seg in segments]
                return action_key, clauses

    return None, []


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

    def _resolve_target(
        self, target_base: str, category: str | None, action: str
    ) -> tuple[list[Any], str | None]:
        """Resolve a target phrase to 0+ matching entities.

        Domain is a SOFT signal, not a hard filter: a category names every
        plausible domain (see DEVICE_CATEGORIES), and every one of them is
        searched, since the same device type can live under different
        domains from house to house. Room scoping is implicit in the name
        matching below (a room name is normally part of the entity's own
        friendly_name), but is backed by explicit tie-disambiguation: if
        multiple entities score equally best, this asks which one instead
        of silently guessing -- the "제어기기 스코핑" safety net.
        """
        all_states = self.hass.states.async_all()
        whole_house = target_base in _WHOLE_HOUSE_WORDS

        if category:
            domains = DEVICE_CATEGORIES[category]["domains"]
        elif action in ("open_cover", "close_cover", "stop_cover"):
            domains = ("cover",)
        elif action in ("media_play", "media_pause"):
            domains = ("media_player",)
        else:
            domains = None

        preferred_domains = domains or _CONTROLLABLE_DOMAINS

        if whole_house:
            return [s for s in all_states if s.domain in preferred_domains], None

        query_raw = target_base.replace(" ", "").lower()
        candidates = []
        for state in all_states:
            domain = state.domain
            if domain not in _CONTROLLABLE_DOMAINS:
                # A physical device's helper entities (update/button/number/
                # select/sensor for the same plug or bulb) often share its
                # exact friendly_name -- e.g. update.dress_plug and
                # switch.dress_plug both named "옷방 플러그" (confirmed live:
                # this caused a false "which one?" tie before this filter).
                # None of them are controllable anyway, so exclude the whole
                # class up front instead of trying to out-score them.
                continue
            fn = state.attributes.get("friendly_name") or ""
            eid = state.entity_id.lower()

            if not fn and not eid:
                continue

            fn_base, fn_category = collapse_domain_suffixes(fn)
            fn_raw = fn.replace(" ", "").lower()

            if domains:
                domain_bonus = 40 if (domain in domains or fn_category == category) else -30
            elif domain in preferred_domains:
                domain_bonus = 15
            else:
                domain_bonus = 0

            subtype_bonus = 0
            for subtype in ["스탠드", "화장대", "다운라이트", "선풍기", "환풍기", "실링팬"]:
                if subtype in target_base and subtype in fn_base:
                    subtype_bonus = 50
                elif subtype in target_base and subtype not in fn_base:
                    subtype_bonus = -50

            if target_base and fn_base and target_base == fn_base:
                candidates.append((100 + domain_bonus + subtype_bonus, state))
            elif query_raw and query_raw == fn_raw:
                candidates.append((90 + domain_bonus + subtype_bonus, state))
            elif target_base and fn_base and (target_base in fn_base or fn_base in target_base):
                candidates.append((75 + domain_bonus + subtype_bonus, state))
            elif query_raw and (query_raw in fn_raw or fn_raw in query_raw):
                candidates.append((65 + domain_bonus + subtype_bonus, state))
            elif target_base and target_base in eid.replace("_", ""):
                candidates.append((50 + domain_bonus + subtype_bonus, state))

        if not candidates:
            return [], None

        candidates.sort(key=lambda x: -x[0])
        top_score = candidates[0][0]
        if top_score <= 50:
            return [], None

        top_matches = [s for score, s in candidates if score == top_score]
        if len(top_matches) == 1:
            return top_matches, None

        names = [s.attributes.get("friendly_name") or s.entity_id for s in top_matches[:6]]
        return (
            [],
            f"어느 것을 말씀하시는 걸까요? ({', '.join(names)} 중 하나로, 또는 '전체'라고 말씀해 주세요.)",
        )

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
                if (
                    (dc == "temperature" or "온도" in fn)
                    and not temp_val
                    and s.state not in ("unavailable", "unknown")
                ):
                    temp_val = f"{s.state}{s.attributes.get('unit_of_measurement', '°C')}"
                if (
                    (dc == "humidity" or "습도" in fn)
                    and not hum_val
                    and s.state not in ("unavailable", "unknown")
                ):
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
        appliance_text = (
            ", ".join(appliance_parts) if appliance_parts else "가전 대기 중 (세탁/건조 완료)"
        )

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

                if any(
                    ex in fn
                    for ex in [
                        "플러그",
                        "버튼",
                        "스위치",
                        "재실",
                        "도어",
                        "창문",
                        "문",
                        "배터리",
                        "세탁기",
                        "건조기",
                        "장치",
                    ]
                ):
                    continue

                match_env = False
                if is_temp:
                    if dc == "temperature" or (
                        "온도" in fn
                        and "습도" not in fn
                        and "설정" not in fn
                        and "최고" not in fn
                        and "최저" not in fn
                    ):
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
                    with open(p, encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                    errors = [
                        line_entry.strip()
                        for line_entry in lines
                        if " ERROR " in line_entry or " CRITICAL " in line_entry
                    ]
                    if errors:
                        recent = errors[-3:]
                        formatted = []
                        for e in recent:
                            parts = e.split(" ERROR ", 1)
                            formatted.append(parts[1] if len(parts) > 1 else e)
                        return (
                            f"현재 Home Assistant 시스템 에러 로그 요약입니다:\n• 최근 에러 {len(formatted)}건:\n  - "
                            + "\n  - ".join(formatted)
                        )
                    return "현재 Home Assistant 시스템에 기록된 에러가 없습니다. (정상 동작 중)"
                except Exception:
                    pass
        return "현재 시스템에 기록된 치명적인 에러는 없습니다."

    async def _handle_special_macros(self, text: str, session: ConversationSession) -> str | None:
        """Handle batch controls, modes, radio, and special macro commands.

        Temperature is deliberately NOT handled here anymore -- see
        _handle_percent_or_temperature(), which applies room scoping
        instead of grabbing the first climate entity in the house.
        """
        clean = normalize_phonetics(text.strip().replace(" ", "").lower())

        # System Error Logs Query (에러 로그, 시스템 로그, 오류 확인)
        if any(
            w in clean
            for w in [
                "에러로그",
                "오류로그",
                "에러확인",
                "오류확인",
                "시스템로그",
                "최근에러",
                "로그확인",
            ]
        ):
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

        # 1. Broad Home Status / Situation / Summary Intent
        if any(
            w in clean
            for w in [
                "상태",
                "상황",
                "현황",
                "요약",
                "브리핑",
                "분위기",
                "어때",
                "어떠",
                "어떻",
                "집안",
                "우리집",
                "모습",
            ]
        ):
            if not any(
                ctrl in clean
                for ctrl in ["켜", "꺼", "틀어", "시작", "정지", "닫아", "열어", "작동", "돌려"]
            ):
                session.topic = "summary"
                return self._generate_home_summary()

        # 2. Batch Light Control (불 다 꺼, 모든 조명 꺼, 집안 불 끄기)
        if any(
            w in clean
            for w in ["불다꺼", "조명다꺼", "전등다꺼", "모든불꺼", "모든조명꺼", "다꺼", "전체꺼"]
        ):
            on_lights = [
                s.entity_id
                for s in self.hass.states.async_all()
                if s.domain == "light" and s.state == "on"
            ]
            if on_lights:
                await self.hass.services.async_call(
                    "light", "turn_off", {"entity_id": on_lights}, blocking=True
                )
                session.topic = "device"
                return f"켜져 있던 {len(on_lights)}개의 조명을 모두 껐습니다."
            else:
                return "현재 켜져 있는 조명이 없습니다."

        if any(
            w in clean for w in ["불다켜", "조명다켜", "모든불켜", "모든조명켜", "다켜", "전체켜"]
        ):
            await self.hass.services.async_call(
                "light", "turn_on", {"entity_id": "all"}, blocking=True
            )
            session.topic = "device"
            return "집안의 모든 조명을 켰습니다."

        # 3. Outing Mode (나 나갈게, 외출 모드, 외출할게)
        if any(w in clean for w in ["나나갈게", "외출할게", "외출모드", "외출", "나간다"]):
            session.topic = "mode"
            for domain, s_id in [("script", "outing_mode"), ("automation", "oeculmodeu_silhaeng")]:
                if self.hass.states.get(f"{domain}.{s_id}"):
                    await self.hass.services.async_call(
                        domain,
                        "turn_on" if domain == "script" else "trigger",
                        {"entity_id": f"{domain}.{s_id}"},
                        blocking=True,
                    )
                    return "외출 모드를 실행했습니다. 안전하게 다녀오세요!"
            await self.hass.services.async_call(
                "light", "turn_off", {"entity_id": "all"}, blocking=True
            )
            return "외출 모드로 전환하여 조명을 모두 껐습니다."

        # 4. Sleep Mode (잘 자, 취침 모드, 수면 모드, 잘자)
        if any(w in clean for w in ["잘자", "취침모드", "수면모드", "자러갈게", "안녕히주무세요"]):
            session.topic = "mode"
            for domain, s_id in [("script", "sub_sleep_mode")]:
                if self.hass.states.get(f"{domain}.{s_id}"):
                    await self.hass.services.async_call(
                        domain, "turn_on", {"entity_id": f"{domain}.{s_id}"}, blocking=True
                    )
                    return "취침 모드를 실행했습니다. 안녕히 주무세요!"
            return "취침 모드를 실행했습니다. 편안한 밤 되세요!"

        # 5. Korea Radio Control (라디오 틀어줘, 라디오 재생, 라디오 꺼)
        if "라디오" in clean:
            session.topic = "media"
            if any(w in clean for w in ["틀어", "켜", "재생", "플레이", "start", "on"]):
                for s_id in ["automation.radio_jaesaeng", "automation.radio_jaesaeng2"]:
                    if self.hass.states.get(s_id):
                        await self.hass.services.async_call(
                            "automation", "trigger", {"entity_id": s_id}, blocking=True
                        )
                        return "라디오를 재생합니다."
            elif any(w in clean for w in ["꺼", "멈춰", "중지", "그만", "off", "stop"]):
                for s in self.hass.states.async_all():
                    if s.domain == "media_player" and s.state in ("playing", "paused"):
                        await self.hass.services.async_call(
                            "media_player", "media_stop", {"entity_id": s.entity_id}, blocking=True
                        )
                return "라디오 재생을 중지했습니다."

        return None

    async def _handle_percent_or_temperature(
        self, text: str, session: ConversationSession
    ) -> str | None:
        """Number-bearing settings that carry no on/off verb at all
        ("26도로 맞춰줘", "50%로 해줘") -- checked before the verb-keyword
        gate below, same as the addon's own ordering, and routed through
        _resolve_target() so these get the same room scoping as everything
        else instead of grabbing the first matching entity in the house.
        """
        clean = normalize_phonetics(text.strip().replace(" ", "").lower())

        temp_match = _TEMPERATURE_RE.search(text)
        if temp_match and any(
            w in clean for w in ["에어컨", "에어콘", "난방", "냉방", "온도", "맞춰", "설정"]
        ):
            target_temp = float(temp_match.group(1))
            stripped = _strip_setting_words(clean.replace(f"{temp_match.group(1)}도", ""))
            target_base, _ = collapse_domain_suffixes(stripped)
            targets, err = self._resolve_target(target_base, "climate", "turn_on")
            if err:
                return err
            if not targets:
                return None
            for t in targets:
                await self.hass.services.async_call(
                    "climate",
                    "set_temperature",
                    {"entity_id": t.entity_id, "temperature": target_temp},
                    blocking=True,
                )
                session.last_entity_id = t.entity_id
            names = [t.attributes.get("friendly_name") or t.entity_id for t in targets]
            return f"{', '.join(names)} 목표 온도를 {int(target_temp)}도로 설정했습니다."

        pct_match = _PERCENT_RE.search(clean)
        if pct_match:
            is_fan = any(w in clean for w in DEVICE_CATEGORIES["fan"]["suffixes"])
            is_light = any(w in clean for w in DEVICE_CATEGORIES["light"]["suffixes"])
            if is_fan or is_light:
                pct = int(pct_match.group(1))
                category = "fan" if is_fan else "light"
                stripped = _strip_setting_words(
                    clean[: pct_match.start()] + clean[pct_match.end() :]
                )
                target_base, _ = collapse_domain_suffixes(stripped)
                targets, err = self._resolve_target(target_base, category, "turn_on")
                if err:
                    return err
                if not targets:
                    return None
                for t in targets:
                    if t.domain == "fan":
                        await self.hass.services.async_call(
                            "fan",
                            "set_percentage",
                            {"entity_id": t.entity_id, "percentage": pct},
                            blocking=True,
                        )
                    else:
                        await self.hass.services.async_call(
                            "light",
                            "turn_on",
                            {"entity_id": t.entity_id, "brightness_pct": pct},
                            blocking=True,
                        )
                    session.last_entity_id = t.entity_id
                names = [t.attributes.get("friendly_name") or t.entity_id for t in targets]
                return f"{', '.join(names)}을(를) {pct}%로 설정했습니다."

        return None

    def _handle_info_query(self, text: str, session: ConversationSession) -> str | None:
        """Handle information, sensory (더워/추워/환기), and sensor queries with contextual continuation."""
        clean = normalize_phonetics(text.strip().lower())
        clean_no_space = clean.replace(" ", "")
        all_states = self.hass.states.async_all()

        # Sensory Query 1: 더위 / 폭염 ("오늘 더워?", "더워?", "덥나", "더울까", "에어컨 틀까")
        if any(
            w in clean
            for w in ["더워", "덥나", "덥냐", "더운가", "더울까", "더운", "폭염", "열대야"]
        ):
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
        if any(
            w in clean for w in ["문열린", "문 열린", "창문열린", "창문 열린", "열린문", "열린 문"]
        ):
            open_sensors = []
            for s in all_states:
                if s.domain == "binary_sensor":
                    dc = s.attributes.get("device_class")
                    fn = s.attributes.get("friendly_name") or s.entity_id
                    if (
                        dc in ("door", "window", "opening") or any(k in fn for k in ["문", "창문"])
                    ) and s.state == "on":
                        open_sensors.append(fn)
            if open_sensors:
                return f"현재 열려 있는 곳은 {', '.join(open_sensors)} 입니다."
            return "현재 모든 문과 창문이 닫혀 있습니다."

        # Contextual Follow-up 1: "내일은?", "내일 날씨"
        is_followup_tomorrow = clean_no_space in (
            "내일은",
            "내일은?",
            "내일날씨",
            "내일날씨는",
            "내일날씨는?",
            "내일도비와",
            "내일도비와?",
            "내일도비오나",
        ) or (session.topic == "weather" and "내일" in clean)
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
                if (
                    "weather_briefing" in eid or "날씨 보고" in fn or "날씨보고" in fn
                ) and state.state not in ("unavailable", "unknown"):
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
            if any(
                w in clean
                for w in [
                    "애드온별",
                    "애드온 별",
                    "각 애드온",
                    "모든 애드온",
                    "애드온 목록",
                    "앱별",
                    "애드온들",
                ]
            ):
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
                    with open("/proc/meminfo") as f:
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
                addon_info = (
                    f"Antigravity CLI 애드온 메모리는 약 {addon_mem}MB 이며, "
                    if addon_mem > 0
                    else ""
                )
                return f"현재 {addon_info}시스템 전체 메모리는 {used_gb}GB / {total_gb}GB ({pct}%) 사용 중입니다."

            for s in all_states:
                fn = s.attributes.get("friendly_name") or ""
                if "memory" in s.entity_id or "메모리" in fn:
                    if s.state not in ("unavailable", "unknown"):
                        return f"현재 시스템 메모리 사용량은 {s.state}{s.attributes.get('unit_of_measurement', '')} 입니다."

        # Humidity query
        if "습도" in clean:
            target_room, _ = collapse_domain_suffixes(
                clean.replace("습도", "").replace("어때", "").replace("몇", "")
            )
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
            target_room, _ = collapse_domain_suffixes(
                clean.replace("온도", "").replace("몇도", "").replace("몇 도", "")
            )
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
                if any(w in fn for w in ["미세먼지", "대기", "공기질"]) and state.state not in (
                    "unavailable",
                    "unknown",
                ):
                    unit = state.attributes.get("unit_of_measurement") or ""
                    return f"{fn} 상태는 {state.state}{unit} 입니다."

        return None

    async def _execute_domain_control(
        self, action: str, clauses: list[tuple[str, str | None]], session: ConversationSession
    ) -> str | None:
        """Execute one shared action across 1+ resolved device clauses (2+
        only for a compound command like "안방 등하고 선풍기 켜줘").

        Safety: a dangerous appliance (see DEVICE_CATEGORIES["appliance"])
        is NEVER turned off immediately, regardless of how it was resolved
        (named directly, or via a bare "그거" follow-up) -- its category is
        re-derived straight from the resolved entity's own friendly_name
        right before executing, so a follow-up can't accidentally skip the
        gate a direct command would have hit. It's queued on
        session.pending_confirm and only runs after an explicit "응" on the
        next turn, mirroring the confirmation gate the addon itself
        enforces on its primary path.
        """
        resolved: list[Any] = []
        errors: list[str] = []

        for target_base, category in clauses:
            if not target_base or target_base in ("그거", "그것도", "다시", "그거꺼", "그거켜"):
                if session.last_entity_id:
                    matched_state = self.hass.states.get(session.last_entity_id)
                    if matched_state:
                        resolved.append(matched_state)
                continue
            targets, err = self._resolve_target(target_base, category, action)
            if err:
                errors.append(err)
                continue
            resolved.extend(targets)

        if not resolved:
            return "\n".join(errors) if errors else None

        to_confirm = []
        messages = []

        for matched_state in resolved:
            domain = matched_state.domain
            entity_id = matched_state.entity_id
            friendly_name = matched_state.attributes.get("friendly_name") or entity_id
            _, entity_category = collapse_domain_suffixes(friendly_name)

            real_action = action
            if action == "toggle":
                real_action = "turn_off" if _is_entity_on(matched_state) else "turn_on"

            service_domain, service, speech_verb = _service_for_action(domain, real_action)
            if not service:
                continue

            session.last_entity_id = entity_id
            for room in ROOMS:
                if room in friendly_name:
                    session.last_room = room
                    break

            if entity_category == "appliance" and real_action == "turn_off":
                to_confirm.append(
                    {
                        "domain": service_domain,
                        "service": service,
                        "entity_id": entity_id,
                        "name": friendly_name,
                    }
                )
                continue

            try:
                await self.hass.services.async_call(
                    service_domain, service, {"entity_id": entity_id}, blocking=True
                )
                messages.append(f"{friendly_name}을(를) {speech_verb}.")
            except Exception as ex:
                _LOGGER.error(
                    "Local fallback failed to execute %s.%s on %s: %s",
                    service_domain,
                    service,
                    entity_id,
                    ex,
                )
                continue

        if to_confirm:
            session.pending_confirm = {
                "calls": [
                    {"domain": c["domain"], "service": c["service"], "entity_id": c["entity_id"]}
                    for c in to_confirm
                ],
                "names": [c["name"] for c in to_confirm],
            }
            names = [c["name"] for c in to_confirm]
            messages.append(
                f"⚠️ {', '.join(names)}을(를) 정말 끄시겠어요? "
                f'끄면 불편이 생길 수 있는 기기입니다. 계속하시려면 "응"이라고 답해주세요.'
            )

        return "\n".join(messages) if messages else None

    async def _handle_local_fallback(self, text: str, session: ConversationSession) -> str | None:
        """Second line of defense -- only ever called once the addon's own
        /api/chat has failed on every host this turn (see async_process()).
        A best-effort substitute, not a replacement: less thorough than the
        addon's own engine, but a dangerous appliance still never turns off
        without an explicit "응".
        """
        clean = normalize_phonetics(text.strip().replace(" ", "").lower())

        if session.pending_confirm:
            pending = session.pending_confirm
            session.pending_confirm = None
            if any(clean == w or clean.startswith(w) for w in _AFFIRMATIVE_WORDS):
                for call in pending["calls"]:
                    await self.hass.services.async_call(
                        call["domain"],
                        call["service"],
                        {"entity_id": call["entity_id"]},
                        blocking=True,
                    )
                names = pending["names"]
                return f"확인했습니다 -- {', '.join(names)}을(를) 껐습니다."
            if any(clean == w or clean.startswith(w) for w in _NEGATIVE_WORDS):
                names = pending["names"]
                return f"취소했습니다. {', '.join(names)} 그대로 두겠습니다."
            # Not a yes/no -- treat as a brand-new command instead (matches
            # the addon's own pending-confirmation semantics: an unrelated
            # reply silently drops the stale confirmation rather than
            # blocking it).

        macro_speech = await self._handle_special_macros(text, session)
        if macro_speech:
            return macro_speech

        pct_or_temp_speech = await self._handle_percent_or_temperature(text, session)
        if pct_or_temp_speech:
            return pct_or_temp_speech

        action, clauses = parse_control_intent(text)
        if action:
            speech = await self._execute_domain_control(action, clauses, session)
            if speech:
                return speech

        return None

    async def async_process(self, user_input: ConversationInput) -> ConversationResult:
        """Try the addon's own /api/chat first -- its fast-dispatch engine
        covers room-scoped control, confirmation gates, and every info
        query with more rigor than this integration can match locally.
        Local processing (_handle_local_fallback / _handle_info_query)
        only ever runs as a second line of defense, when the addon is
        completely unreachable this turn.
        """
        intent_response = intent.IntentResponse(language=user_input.language)

        raw_text = user_input.text.strip()
        force_llm = False
        target_prompt = raw_text

        # Check explicit LLM triggers (/llm, !llm, ai, agy)
        for prefix in LLM_PREFIXES:
            if raw_text.lower().startswith(prefix.lower()):
                force_llm = True
                target_prompt = raw_text[len(prefix) :].strip()
                break

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
            "is_direct_llm": force_llm,
        }

        last_error = None
        for host in host_candidates:
            url = f"http://{host}:{self.coordinator.port}/api/chat"
            try:
                async with asyncio.timeout(65):
                    async with http_session.post(url, json=payload, headers=headers) as response:
                        if response.status == 200:
                            raw_body = await response.text()
                            response_text, conv_id = _parse_sse_chat_response(raw_body)
                            intent_response.async_set_speech(
                                response_text or "답변을 생성할 수 없습니다."
                            )
                            return ConversationResult(
                                response=intent_response,
                                conversation_id=conv_id or user_input.conversation_id,
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

        # Addon unreachable on every host this turn -- second line of defense.
        _LOGGER.warning(
            "Antigravity CLI addon unreachable (%s) -- falling back to local processing for: %s",
            last_error,
            target_prompt,
        )
        session = self._get_or_create_session(user_input.conversation_id)
        local_speech = await self._handle_local_fallback(target_prompt, session)
        if not local_speech:
            local_speech = (
                self._handle_info_query(target_prompt, session) or self._generate_home_summary()
            )
        intent_response.async_set_speech(f"⚠️ (애드온 응답 없음, 로컬로 처리) {local_speech}")
        return ConversationResult(
            response=intent_response,
            conversation_id=user_input.conversation_id,
        )
