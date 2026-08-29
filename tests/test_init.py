"""Test antigravity_cli setup and unload."""

from pytest_homeassistant_custom_component.common import MockConfigEntry
from homeassistant.core import HomeAssistant

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

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert DOMAIN in hass.data
    assert entry.entry_id in hass.data[DOMAIN]

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.entry_id not in hass.data[DOMAIN]
