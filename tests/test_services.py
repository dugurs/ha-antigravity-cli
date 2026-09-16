"""Test antigravity_cli services."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.antigravity_cli.const import (
    ATTR_CHAT_ID,
    ATTR_MESSAGE,
    ATTR_MODE,
    ATTR_MODEL,
    CONF_HOST,
    CONF_PORT,
    DOMAIN,
    SERVICE_CHAT,
)
from custom_components.antigravity_cli.coordinator import AntigravityDataUpdateCoordinator
from custom_components.antigravity_cli.services import (
    _resolve_stream_mode,
    async_register_services,
    async_unregister_services,
    parse_sse_chat_response,
)


class MockResponse:
    """Mock aiohttp response."""

    def __init__(
        self,
        status: int = 200,
        text_data: str = "",
        json_data: dict | None = None,
    ) -> None:
        self.status = status
        self._text_data = text_data
        self._json_data = json_data or {}

    async def text(self) -> str:
        return self._text_data

    async def json(self) -> dict:
        return self._json_data

    async def __aenter__(self) -> MockResponse:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        pass


def test_resolve_stream_mode() -> None:
    """Test mapping mode string to integer."""
    assert _resolve_stream_mode("1") == 1
    assert _resolve_stream_mode("fast_local") == 1
    assert _resolve_stream_mode("fast") == 1
    assert _resolve_stream_mode("fast_only") == 1
    assert _resolve_stream_mode("2") == 2
    assert _resolve_stream_mode("llm_mcp") == 2
    assert _resolve_stream_mode("3") == 3
    assert _resolve_stream_mode("hybrid") == 3
    assert _resolve_stream_mode("unknown") == 3


def test_parse_sse_chat_response() -> None:
    """Test parsing SSE stream into answer and conversation_id."""
    raw_sse = (
        'data: {"type": "session_init", "content": "conv-12345"}\n\n'
        'data: {"type": "chunk", "content": "안녕하세요! "}\n\n'
        'data: {"type": "chunk", "content": "무엇을 도와드릴까요?"}\n\n'
    )
    answer, conv_id = parse_sse_chat_response(raw_sse)
    assert conv_id == "conv-12345"
    assert answer == "안녕하세요! 무엇을 도와드릴까요?"

    # With final text event
    raw_sse_final = (
        'data: {"type": "session_init", "content": "conv-999"}\n\n'
        'data: {"type": "final", "content": "최종 완료되었습니다."}\n\n'
    )
    answer, conv_id = parse_sse_chat_response(raw_sse_final)
    assert conv_id == "conv-999"
    assert answer == "최종 완료되었습니다."


async def test_chat_service_success(hass: HomeAssistant) -> None:
    """Test successful chat service invocation with response."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Antigravity CLI (127.0.0.1:8000)",
        data={
            CONF_HOST: "127.0.0.1",
            CONF_PORT: 8000,
        },
    )
    entry.add_to_hass(hass)

    sse_response_body = (
        'data: {"type": "session_init", "content": "conv-42"}\n\n'
        'data: {"type": "chunk", "content": "거실 조명을 켰습니다."}\n\n'
    )

    mock_session = MagicMock()
    mock_session.post.return_value = MockResponse(200, text_data=sse_response_body)

    with (
        patch(
            "custom_components.antigravity_cli.coordinator.async_get_clientsession",
            return_value=mock_session,
        ),
        patch(
            "custom_components.antigravity_cli.services.async_get_clientsession",
            return_value=mock_session,
        ),
    ):
        coordinator = AntigravityDataUpdateCoordinator(hass, entry)
        coordinator.data = {"status": "online"}
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

        await async_register_services(hass)
        assert hass.services.has_service(DOMAIN, SERVICE_CHAT)

        # Call service with return_response=True
        result = await hass.services.async_call(
            DOMAIN,
            SERVICE_CHAT,
            {
                ATTR_MESSAGE: "거실 불 켜줘",
                ATTR_MODE: "fast_local",
                ATTR_CHAT_ID: "conv-42",
                ATTR_MODEL: "gemini-2.5-flash",
            },
            blocking=True,
            return_response=True,
        )

        assert result is not None
        assert result.get("success") is True
        assert result.get("response") == "거실 조명을 켰습니다."
        assert result.get("conversation_id") == "conv-42"

        # Verify POST payload sent
        call_args = mock_session.post.call_args
        assert call_args is not None
        posted_json = call_args[1]["json"]
        assert posted_json["prompt"] == "거실 불 켜줘"
        assert posted_json["stream_mode"] == 1
        assert posted_json["conversation_id"] == "conv-42"
        assert posted_json["model"] == "gemini-2.5-flash"

        # Unregister service
        await async_unregister_services(hass)
        assert not hass.services.has_service(DOMAIN, SERVICE_CHAT)


async def test_chat_service_empty_message(hass: HomeAssistant) -> None:
    """Test error when message is empty."""
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
            "custom_components.antigravity_cli.services.async_get_clientsession",
            return_value=MagicMock(),
        ),
    ):
        coordinator = AntigravityDataUpdateCoordinator(hass, entry)
        coordinator.data = {"status": "online"}
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

        await async_register_services(hass)
        with pytest.raises(HomeAssistantError) as excinfo:
            await hass.services.async_call(
                DOMAIN,
                SERVICE_CHAT,
                {ATTR_MESSAGE: ""},
                blocking=True,
            )
        assert "cannot be empty" in str(excinfo.value)
        await async_unregister_services(hass)


async def test_chat_service_disabled_mode_403(hass: HomeAssistant) -> None:
    """Test error when add-on chat mode is monitoring (HTTP 403)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Antigravity CLI (127.0.0.1:8000)",
        data={CONF_HOST: "127.0.0.1", CONF_PORT: 8000},
    )
    entry.add_to_hass(hass)

    mock_session = MagicMock()
    mock_session.post.return_value = MockResponse(
        403,
        json_data={"error": "Chat is disabled in add-on configuration (chat_mode=monitoring)."},
    )

    with (
        patch(
            "custom_components.antigravity_cli.coordinator.async_get_clientsession",
            return_value=mock_session,
        ),
        patch(
            "custom_components.antigravity_cli.services.async_get_clientsession",
            return_value=mock_session,
        ),
    ):
        coordinator = AntigravityDataUpdateCoordinator(hass, entry)
        coordinator.data = {"status": "online"}
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

        await async_register_services(hass)
        with pytest.raises(HomeAssistantError) as excinfo:
            await hass.services.async_call(
                DOMAIN,
                SERVICE_CHAT,
                {ATTR_MESSAGE: "hello"},
                blocking=True,
            )
        assert "disabled in add-on configuration" in str(excinfo.value)
        await async_unregister_services(hass)
