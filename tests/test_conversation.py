from unittest.mock import MagicMock, patch

from homeassistant.components.conversation import ConversationEntityFeature
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.antigravity_cli.const import (
    CONF_HOST,
    CONF_PORT,
    DOMAIN,
)
from custom_components.antigravity_cli.conversation import (
    AntigravityConversationEntity,
    async_setup_entry,
)
from custom_components.antigravity_cli.coordinator import AntigravityDataUpdateCoordinator


async def test_conversation_agent(hass: HomeAssistant) -> None:
    """Test conversation agent processing."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Antigravity CLI (127.0.0.1:8000)",
        data={
            CONF_HOST: "127.0.0.1",
            CONF_PORT: 8000,
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.antigravity_cli.coordinator.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.antigravity_cli.conversation.async_get_clientsession",
            return_value=MagicMock(),
        ),
    ):
        coordinator = AntigravityDataUpdateCoordinator(hass, entry)
        coordinator.data = {
            "status": "online",
            "version": "1.1.0",
            "active_sessions": 1,
            "uptime": 100,
            "remote_control_running": False,
            "scheduled_count": 0,
            "scheduled_list": [],
        }
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

        entities: list[AntigravityConversationEntity] = []
        await async_setup_entry(hass, entry, entities.extend)

    assert len(entities) == 1
    entity = entities[0]
    assert isinstance(entity, AntigravityConversationEntity)
    assert entity.supported_features == ConversationEntityFeature.CONTROL
    assert entity.unique_id == f"{entry.entry_id}_assistant"


async def test_process_fast_local_matching(hass: HomeAssistant) -> None:
    """Test fast local matching handles known device commands in 0.05s."""
    from homeassistant.components.conversation import ConversationInput
    from homeassistant.core import Context

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Antigravity CLI (127.0.0.1:8000)",
        data={CONF_HOST: "127.0.0.1", CONF_PORT: 8000},
    )
    entry.add_to_hass(hass)

    hass.states.async_set("light.living_room", "off", {"friendly_name": "거실 조명"})
    service_calls = []

    async def _mock_light_service(call):
        service_calls.append(call)

    hass.services.async_register("light", "turn_on", _mock_light_service)

    with (
        patch(
            "custom_components.antigravity_cli.coordinator.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.antigravity_cli.conversation.async_get_clientsession",
            return_value=MagicMock(),
        ),
    ):
        coordinator = AntigravityDataUpdateCoordinator(hass, entry)
        entity = AntigravityConversationEntity(coordinator, entry)
        entity.hass = hass

        user_input = ConversationInput(
            text="거실 조명 켜줘",
            context=Context(),
            conversation_id="conv_local",
            device_id=None,
            language="ko",
        )

        with patch.object(entity, "_call_addon_chat") as mock_addon:
            result = await entity.async_process(user_input)
            assert not mock_addon.called

    assert "켰습니다" in result.response.speech["plain"]["speech"]
    assert len(service_calls) == 1
    assert service_calls[0].data["entity_id"] == "light.living_room"


async def test_process_gemini_direct_text(hass: HomeAssistant) -> None:
    """Test un-patterned natural language query routed directly to Gemini API."""
    from homeassistant.components.conversation import ConversationInput
    from homeassistant.core import Context

    from custom_components.antigravity_cli.const import CONF_GEMINI_API_KEY

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Antigravity CLI (127.0.0.1:8000)",
        data={
            CONF_HOST: "127.0.0.1",
            CONF_PORT: 8000,
            CONF_GEMINI_API_KEY: "AIzaSyFakeKey123",
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.antigravity_cli.coordinator.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.antigravity_cli.conversation.async_get_clientsession",
            return_value=MagicMock(),
        ),
    ):
        coordinator = AntigravityDataUpdateCoordinator(hass, entry)
        entity = AntigravityConversationEntity(coordinator, entry)
        entity.hass = hass

        user_input = ConversationInput(
            text="달의 지름은 얼마인가요?",
            context=Context(),
            conversation_id="conv_gemini",
            device_id=None,
            language="ko",
        )

        with (
            patch(
                "custom_components.antigravity_cli.conversation.async_call_gemini_api",
                return_value=("달의 지름은 약 3,474km입니다.", None, None),
            ) as mock_gemini,
            patch.object(entity, "_call_addon_chat") as mock_addon,
        ):
            result = await entity.async_process(user_input)
            assert mock_gemini.called
            assert not mock_addon.called

    assert result.response.speech["plain"]["speech"] == "달의 지름은 약 3,474km입니다."


async def test_process_gemini_direct_tool_call(hass: HomeAssistant) -> None:
    """Test un-patterned query resulting in Gemini device control tool execution."""
    from homeassistant.components.conversation import ConversationInput
    from homeassistant.core import Context

    from custom_components.antigravity_cli.const import CONF_GEMINI_API_KEY

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Antigravity CLI (127.0.0.1:8000)",
        data={
            CONF_HOST: "127.0.0.1",
            CONF_PORT: 8000,
            CONF_GEMINI_API_KEY: "AIzaSyFakeKey123",
        },
    )
    entry.add_to_hass(hass)

    hass.states.async_set("light.living_room", "off", {"friendly_name": "거실 조명"})
    service_calls = []

    async def _mock_light_service(call):
        service_calls.append(call)

    hass.services.async_register("light", "turn_on", _mock_light_service)

    with (
        patch(
            "custom_components.antigravity_cli.coordinator.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.antigravity_cli.conversation.async_get_clientsession",
            return_value=MagicMock(),
        ),
    ):
        coordinator = AntigravityDataUpdateCoordinator(hass, entry)
        entity = AntigravityConversationEntity(coordinator, entry)
        entity.hass = hass

        user_input = ConversationInput(
            text="영화를 볼 건데 거실 조명 낮춰줘",
            context=Context(),
            conversation_id="conv_gemini_tool",
            device_id=None,
            language="ko",
        )

        gemini_func_call = [
            {
                "name": "control_device",
                "args": {
                    "domain": "light",
                    "service": "turn_on",
                    "entity_id": "light.living_room",
                    "speech": "거실 조명을 어둡게 조절했습니다.",
                },
            }
        ]

        with patch(
            "custom_components.antigravity_cli.conversation.async_call_gemini_api",
            return_value=(None, gemini_func_call, None),
        ):
            result = await entity.async_process(user_input)

    assert result.response.speech["plain"]["speech"] == "거실 조명을 어둡게 조절했습니다."
    assert len(service_calls) == 1
    assert service_calls[0].data["entity_id"] == ["light.living_room"]


async def test_process_gemini_fallback_to_addon(hass: HomeAssistant) -> None:
    """Test fallback to addon /api/chat when Gemini API fails."""
    from homeassistant.components.conversation import ConversationInput
    from homeassistant.core import Context

    from custom_components.antigravity_cli.const import CONF_GEMINI_API_KEY

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Antigravity CLI (127.0.0.1:8000)",
        data={
            CONF_HOST: "127.0.0.1",
            CONF_PORT: 8000,
            CONF_GEMINI_API_KEY: "AIzaSyFakeKey123",
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.antigravity_cli.coordinator.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.antigravity_cli.conversation.async_get_clientsession",
            return_value=MagicMock(),
        ),
    ):
        coordinator = AntigravityDataUpdateCoordinator(hass, entry)
        entity = AntigravityConversationEntity(coordinator, entry)
        entity.hass = hass

        user_input = ConversationInput(
            text="아인슈타인은 누구야?",
            context=Context(),
            conversation_id="conv_fallback",
            device_id=None,
            language="ko",
        )

        with (
            patch(
                "custom_components.antigravity_cli.conversation.async_call_gemini_api",
                return_value=(None, None, "Quota exceeded 429"),
            ),
            patch.object(
                entity,
                "_call_addon_chat",
                return_value=("애드온에서 생성한 응답입니다.", "conv_fallback", None),
            ) as mock_addon,
        ):
            result = await entity.async_process(user_input)
            assert mock_addon.called

    assert result.response.speech["plain"]["speech"] == "애드온에서 생성한 응답입니다."


async def test_process_explicit_cli_prefix(hass: HomeAssistant) -> None:
    """Test explicit CLI prefix routes directly to addon."""
    from homeassistant.components.conversation import ConversationInput
    from homeassistant.core import Context

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Antigravity CLI (127.0.0.1:8000)",
        data={CONF_HOST: "127.0.0.1", CONF_PORT: 8000},
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.antigravity_cli.coordinator.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.antigravity_cli.conversation.async_get_clientsession",
            return_value=MagicMock(),
        ),
    ):
        coordinator = AntigravityDataUpdateCoordinator(hass, entry)
        entity = AntigravityConversationEntity(coordinator, entry)
        entity.hass = hass

        user_input = ConversationInput(
            text="agy 시스템 에러 로그 자세히 분석해줘",
            context=Context(),
            conversation_id="conv_cli",
            device_id=None,
            language="ko",
        )

        with patch.object(
            entity,
            "_call_addon_chat",
            return_value=("CLI 자율 분석 완료.", "conv_cli", None),
        ) as mock_addon:
            result = await entity.async_process(user_input)
            assert mock_addon.called
            assert mock_addon.call_args[0][0] == "시스템 에러 로그 자세히 분석해줘"

    assert result.response.speech["plain"]["speech"] == "CLI 자율 분석 완료."


async def test_process_mode_fast_local(hass: HomeAssistant) -> None:
    """Test fast_local mode only processes local intents without external LLM."""
    from homeassistant.components.conversation import ConversationInput
    from homeassistant.core import Context

    from custom_components.antigravity_cli.const import (
        CONF_PROCESSING_MODE,
        MODE_FAST_LOCAL,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Antigravity CLI (127.0.0.1:8000)",
        data={CONF_HOST: "127.0.0.1", CONF_PORT: 8000},
        options={CONF_PROCESSING_MODE: MODE_FAST_LOCAL},
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.antigravity_cli.coordinator.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.antigravity_cli.conversation.async_get_clientsession",
            return_value=MagicMock(),
        ),
    ):
        coordinator = AntigravityDataUpdateCoordinator(hass, entry)
        entity = AntigravityConversationEntity(coordinator, entry)
        entity.hass = hass

        user_input = ConversationInput(
            text="양자역학의 불확정성 원리가 뭐야?",
            context=Context(),
            conversation_id="conv_fast_local",
            device_id=None,
            language="ko",
        )

        with patch.object(entity, "_call_addon_chat") as mock_addon:
            result = await entity.async_process(user_input)
            assert not mock_addon.called

    assert "로컬 고속 모드" in result.response.speech["plain"]["speech"]
