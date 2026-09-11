"""Binary sensor platform for antigravity_cli."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AntigravityDataUpdateCoordinator
from .entity import AntigravityEntity

BINARY_SENSOR_TYPES: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key="remote_control_daemon",
        translation_key="remote_control_daemon",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:remote-desktop",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""
    coordinator: AntigravityDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        AntigravityBinarySensor(coordinator, description)
        for description in BINARY_SENSOR_TYPES
    )


class AntigravityBinarySensor(AntigravityEntity, BinarySensorEntity):
    """Antigravity binary sensor entity."""

    entity_description: BinarySensorEntityDescription

    def __init__(
        self,
        coordinator: AntigravityDataUpdateCoordinator,
        description: BinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        if not self.coordinator.data:
            return None
        if self.entity_description.key == "remote_control_daemon":
            return bool(self.coordinator.data.get("remote_control_running", False))
        return None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return (
            super().available
            and self.coordinator.data is not None
            and self.coordinator.data.get("status") != "offline"
        )
