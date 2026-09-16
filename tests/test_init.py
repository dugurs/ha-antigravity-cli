"""Test antigravity_cli setup and unload."""

from unittest.mock import MagicMock, patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.antigravity_cli.const import (
    CONF_HOST,
    CONF_PORT,
    DOMAIN,
)


async def test_setup_and_unload_entry(hass: HomeAssistant) -> None:
    """Test setting up and unloading entry."""
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
            "custom_components.antigravity_cli.coordinator.AntigravityDataUpdateCoordinator._async_update_data",
            return_value={
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
            },
        ),
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            return_value=True,
        ) as mock_forward,
        patch.object(
            hass.config_entries,
            "async_unload_platforms",
            return_value=True,
        ) as mock_unload,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert DOMAIN in hass.data
        assert entry.entry_id in hass.data[DOMAIN]
        assert mock_forward.called
        assert hass.services.has_service(DOMAIN, "chat")

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

        assert entry.entry_id not in hass.data[DOMAIN]
        assert mock_unload.called
        assert not hass.services.has_service(DOMAIN, "chat")
