"""Test the antigravity_cli switch platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.antigravity_cli.const import (
    CONF_HOST,
    CONF_PORT,
    DOMAIN,
)
from custom_components.antigravity_cli.coordinator import AntigravityDataUpdateCoordinator
from custom_components.antigravity_cli.switch import (
    AntigravitySwitch,
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


async def test_switch_setup_and_control(hass: HomeAssistant) -> None:
    """Test switch entity setup, state, and controls."""
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
            "version": "1.1.0",
            "active_sessions": 1,
            "uptime": 100,
            "remote_control_running": False,
            "activity": {
                "state": "idle",
                "is_busy": False,
                "current_tool": None,
                "target_file": None,
            },
            "scheduled_count": 0,
            "scheduled_list": [],
        }
        coordinator.async_request_refresh = AsyncMock()
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

        entities: list[AntigravitySwitch] = []
        await async_setup_entry(hass, entry, entities.extend)

        assert len(entities) == 1
        switch = entities[0]
        assert isinstance(switch, AntigravitySwitch)
        assert switch.unique_id == f"{entry.entry_id}_remote_control_running"
        assert switch.is_on is False

        # Turn on
        await switch.async_turn_on()
        assert mock_session.post.call_count == 1
        url_called = mock_session.post.call_args[0][0]
        assert url_called.endswith("/api/remote_control/start")
        assert coordinator.async_request_refresh.await_count == 1

        # Turn off while idle (should succeed)
        await switch.async_turn_off()
        assert mock_session.post.call_count == 2
        url_called = mock_session.post.call_args[0][0]
        assert url_called.endswith("/api/remote_control/stop")
        assert coordinator.async_request_refresh.await_count == 2

        # Turn off lock: when coordinator reports busy (file_working)
        coordinator.data["activity"] = {
            "state": "file_working",
            "is_busy": True,
            "current_tool": "replace_file_content",
            "target_file": "config.yaml",
        }
        with pytest.raises(HomeAssistantError) as excinfo:
            await switch.async_turn_off()
        assert "끄기 락" in str(excinfo.value)
        assert "파일 작업" in str(excinfo.value)
        assert "config.yaml" in str(excinfo.value)
        # Verify no network call was made because local lock blocked it
        assert mock_session.post.call_count == 2

        # Turn off lock: when coordinator cache was idle but server responds with 409 Conflict
        coordinator.data["activity"] = {"state": "idle", "is_busy": False}
        mock_session.post.return_value = MockResponse(
            409,
            {"ok": False, "error": "busy", "message": "서버가 현재 추론 중입니다."},
        )
        with pytest.raises(HomeAssistantError) as excinfo_server:
            await switch.async_turn_off()
        assert "추론" in str(excinfo_server.value)
        assert mock_session.post.call_count == 3

        # When daemon is running
        coordinator.data["remote_control_running"] = True
        assert switch.is_on is True

        # When data is None
        coordinator.data = None
        assert switch.is_on is None
