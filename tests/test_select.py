"""Test the antigravity_cli select platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.antigravity_cli.const import (
    CHAT_MODE_FAST_ONLY,
    CHAT_MODE_FULL,
    CHAT_MODE_MONITORING,
    CHAT_MODES,
    CONF_HOST,
    CONF_PORT,
    DOMAIN,
)
from custom_components.antigravity_cli.coordinator import AntigravityDataUpdateCoordinator
from custom_components.antigravity_cli.select import (
    AntigravityChatModeSelect,
    async_setup_entry,
)


class MockResponse:
    """Mock aiohttp response."""

    def __init__(self, status: int = 200, json_data: dict | None = None) -> None:
        self.status = status
        self._json_data = json_data or {}

    async def json(self) -> dict:
        return self._json_data

    async def __aenter__(self) -> MockResponse:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        pass


async def test_select_setup_and_control(hass: HomeAssistant) -> None:
    """Test select entity setup, state, and option changes."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Antigravity CLI (127.0.0.1:8000)",
        data={
            CONF_HOST: "127.0.0.1",
            CONF_PORT: 8000,
        },
    )
    entry.add_to_hass(hass)

    mock_session = MagicMock()
    mock_session.post.return_value = MockResponse(200, {"ok": True})

    with patch(
        "custom_components.antigravity_cli.coordinator.async_get_clientsession",
        return_value=mock_session,
    ):
        coordinator = AntigravityDataUpdateCoordinator(hass, entry)
        coordinator.data = {
            "status": "online",
            "options": {
                "chat_mode": CHAT_MODE_FULL,
            },
        }
        coordinator.async_request_refresh = AsyncMock()
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

        entities: list[AntigravityChatModeSelect] = []
        await async_setup_entry(hass, entry, entities.extend)

        assert len(entities) == 1
        select = entities[0]
        assert isinstance(select, AntigravityChatModeSelect)
        assert select.unique_id == f"{entry.entry_id}_chat_mode"
        assert select.options == CHAT_MODES
        assert select.current_option == CHAT_MODE_FULL

        # Select fast_only
        await select.async_select_option(CHAT_MODE_FAST_ONLY)
        assert mock_session.post.call_count == 1
        url_called = mock_session.post.call_args[0][0]
        json_called = mock_session.post.call_args[1]["json"]
        assert url_called.endswith("/api/options")
        assert json_called == {"chat_mode": CHAT_MODE_FAST_ONLY}
        assert coordinator.async_request_refresh.await_count == 1

        # Select monitoring
        await select.async_select_option(CHAT_MODE_MONITORING)
        assert mock_session.post.call_count == 2
        json_called = mock_session.post.call_args[1]["json"]
        assert json_called == {"chat_mode": CHAT_MODE_MONITORING}

        # Select invalid option
        with pytest.raises(ValueError) as excinfo:
            await select.async_select_option("invalid_mode")
        assert "Invalid option" in str(excinfo.value)
        assert mock_session.post.call_count == 2

        # Error response handling
        mock_session.post.return_value = MockResponse(500, {"error": "Internal error"})
        with pytest.raises(HomeAssistantError):
            await select.async_select_option(CHAT_MODE_FULL)

        # When data is None
        coordinator.data = None
        assert select.current_option is None
