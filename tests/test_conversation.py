"""Test antigravity_cli conversation entity."""

from unittest.mock import AsyncMock, patch
from homeassistant.components import conversation
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.antigravity_cli.const import (
    CONF_HOST,
    CONF_PORT,
    DOMAIN,
)


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

    with patch(
        "custom_components.antigravity_cli.coordinator.AntigravityDataUpdateCoordinator._async_update_data",
        return_value={"status": "online", "version": "1.1.0", "active_sessions": 1, "uptime": 100},
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # Verify conversation platform is loaded
    state = hass.states.get("conversation.antigravity_cli_assistant")
    # Entity ID could be conversation.antigravity_cli_assistant or similar
