"""Test the antigravity_cli button platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.antigravity_cli.button import (
    AntigravityButton,
    async_setup_entry,
)
from custom_components.antigravity_cli.const import (
    CONF_HOST,
    CONF_PORT,
    DOMAIN,
)
from custom_components.antigravity_cli.coordinator import AntigravityDataUpdateCoordinator


async def test_button_press(hass: HomeAssistant) -> None:
    """Test button entity press triggers coordinator refresh."""
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
        "custom_components.antigravity_cli.coordinator.async_get_clientsession",
        return_value=MagicMock(),
    ):
        coordinator = AntigravityDataUpdateCoordinator(hass, entry)
        coordinator.async_request_refresh = AsyncMock()
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

        entities: list[AntigravityButton] = []
        await async_setup_entry(hass, entry, entities.extend)

        assert len(entities) == 1
        button = entities[0]
        assert isinstance(button, AntigravityButton)
        assert button.unique_id == f"{entry.entry_id}_sync_status"

        await button.async_press()
        assert coordinator.async_request_refresh.await_count == 1
