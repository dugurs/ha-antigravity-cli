"""The antigravity_cli integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .const import DOMAIN, PLATFORMS
from .coordinator import AntigravityDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_RUN_COMMAND = "run_command"
SERVICE_RUN_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required("command"): cv.string,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up antigravity_cli from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = AntigravityDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register custom service
    async def handle_run_command(call: ServiceCall) -> None:
        """Handle run command service call."""
        command = call.data["command"]
        _LOGGER.info("Antigravity CLI command invoked: %s", command)
        # Service logic can be extended to dispatch commands to Antigravity CLI

    if not hass.services.has_service(DOMAIN, SERVICE_RUN_COMMAND):
        hass.services.async_register(
            DOMAIN,
            SERVICE_RUN_COMMAND,
            handle_run_command,
            schema=SERVICE_RUN_COMMAND_SCHEMA,
        )

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    if not hass.data[DOMAIN]:
        hass.services.async_remove(DOMAIN, SERVICE_RUN_COMMAND)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
