"""Select platform for antigravity_cli."""

from __future__ import annotations

import asyncio
import logging

import aiohttp
from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CHAT_MODE_FULL,
    CHAT_MODES,
    DOMAIN,
)
from .coordinator import AntigravityDataUpdateCoordinator
from .entity import AntigravityEntity

_LOGGER = logging.getLogger(__name__)

SELECT_TYPES: tuple[SelectEntityDescription, ...] = (
    SelectEntityDescription(
        key="chat_mode",
        translation_key="chat_mode",
        icon="mdi:message-cog",
        options=CHAT_MODES,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the select platform."""
    coordinator: AntigravityDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        AntigravityChatModeSelect(coordinator, description) for description in SELECT_TYPES
    )


class AntigravityChatModeSelect(AntigravityEntity, SelectEntity):
    """Select entity to control add-on chat_mode."""

    entity_description: SelectEntityDescription

    def __init__(
        self,
        coordinator: AntigravityDataUpdateCoordinator,
        description: SelectEntityDescription,
    ) -> None:
        """Initialize the chat mode select entity."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_options = description.options or CHAT_MODES

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        if not self.coordinator.data:
            return None
        options = self.coordinator.data.get("options") or {}
        return options.get("chat_mode", CHAT_MODE_FULL)

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if option not in self.options:
            raise ValueError(f"Invalid option: {option}. Expected one of {self.options}")

        headers = {"Content-Type": "application/json"}
        if self.coordinator.api_key:
            headers["Authorization"] = f"Bearer {self.coordinator.api_key}"

        url = f"http://{self.coordinator.host}:{self.coordinator.port}/api/options"
        payload = {"chat_mode": option}

        try:
            async with asyncio.timeout(10):
                async with self.coordinator.session.post(
                    url, json=payload, headers=headers
                ) as response:
                    if response.status != 200:
                        _LOGGER.error(
                            "Failed to update Antigravity CLI chat_mode to %s: HTTP %s",
                            option,
                            response.status,
                        )
                        raise HomeAssistantError(
                            f"Failed to update chat_mode to {option}: HTTP {response.status}"
                        )
        except (TimeoutError, aiohttp.ClientError) as err:
            _LOGGER.error(
                "Connection failed while updating Antigravity CLI chat_mode to %s: %s",
                option,
                err,
            )
            raise HomeAssistantError(
                f"Connection error updating chat_mode to {option}: {err}"
            ) from err

        await self.coordinator.async_request_refresh()
