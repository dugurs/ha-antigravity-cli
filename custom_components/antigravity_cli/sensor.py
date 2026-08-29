"""Sensor platform for antigravity_cli."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfInformation
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AntigravityDataUpdateCoordinator
from .entity import AntigravityEntity

SENSOR_TYPES: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="status",
        translation_key="status",
        icon="mdi:robot",
    ),
    SensorEntityDescription(
        key="active_sessions",
        translation_key="active_sessions",
        icon="mdi:counter",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="uptime",
        translation_key="uptime",
        icon="mdi:clock-outline",
        native_unit_of_measurement="s",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="memory_usage",
        translation_key="memory_usage",
        icon="mdi:memory",
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="cpu_usage",
        translation_key="cpu_usage",
        icon="mdi:cpu-64-bit",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator: AntigravityDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        AntigravitySensor(coordinator, description)
        for description in SENSOR_TYPES
    )


class AntigravitySensor(AntigravityEntity, SensorEntity):
    """Antigravity sensor entity."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        coordinator: AntigravityDataUpdateCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> str | int | float | None:
        """Return the native value of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self.entity_description.key)
