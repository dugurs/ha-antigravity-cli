"""Button platform for antigravity_cli."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AntigravityDataUpdateCoordinator
from .entity import AntigravityEntity

BUTTON_TYPES: tuple[ButtonEntityDescription, ...] = (
    ButtonEntityDescription(
        key="sync_status",
        translation_key="sync_status",
        icon="mdi:sync",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the button platform."""
    coordinator: AntigravityDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        AntigravityButton(coordinator, description)
        for description in BUTTON_TYPES
    )


class AntigravityButton(AntigravityEntity, ButtonEntity):
    """Antigravity button entity."""

    entity_description: ButtonEntityDescription

    def __init__(
        self,
        coordinator: AntigravityDataUpdateCoordinator,
        description: ButtonEntityDescription,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.async_request_refresh()
