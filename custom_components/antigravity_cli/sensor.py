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
        key="daemon_status",
        translation_key="daemon_status",
        icon="mdi:server-cog",
    ),
    SensorEntityDescription(
        key="agent_activity",
        translation_key="agent_activity",
        icon="mdi:brain",
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
    SensorEntityDescription(
        key="scheduled_count",
        translation_key="scheduled_count",
        icon="mdi:calendar-clock",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="gemini_quota",
        translation_key="gemini_quota",
        icon="mdi:google",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="gemini_5h_quota",
        translation_key="gemini_5h_quota",
        icon="mdi:google",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="claude_quota",
        translation_key="claude_quota",
        icon="mdi:creation",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="claude_5h_quota",
        translation_key="claude_5h_quota",
        icon="mdi:creation",
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

    async_add_entities(AntigravitySensor(coordinator, description) for description in SENSOR_TYPES)


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
        if self.entity_description.key == "daemon_status":
            if self.coordinator.data.get("status") == "offline":
                return "offline"
            return "running" if self.coordinator.data.get("remote_control_running") else "stopped"
        if self.entity_description.key == "agent_activity":
            if self.coordinator.data.get("status") == "offline":
                return "offline"
            activity = self.coordinator.data.get("activity") or {}
            return activity.get("state", "idle")
        if self.entity_description.key == "gemini_quota":
            usage = self.coordinator.data.get("usage") or {}
            return usage.get("gemini_weekly_remaining")
        if self.entity_description.key == "gemini_5h_quota":
            usage = self.coordinator.data.get("usage") or {}
            return usage.get("gemini_5h_remaining")
        if self.entity_description.key == "claude_quota":
            usage = self.coordinator.data.get("usage") or {}
            return usage.get("claude_weekly_remaining")
        if self.entity_description.key == "claude_5h_quota":
            usage = self.coordinator.data.get("usage") or {}
            return usage.get("claude_5h_remaining")
        return self.coordinator.data.get(self.entity_description.key)

    @property
    def icon(self) -> str | None:
        """Return the icon based on current activity state."""
        if self.entity_description.key == "agent_activity":
            val = self.native_value
            if val == "file_working":
                return "mdi:file-edit"
            if val == "thinking":
                return "mdi:brain"
            if val == "executing_tool":
                return "mdi:tools"
            if val == "offline":
                return "mdi:cloud-off-outline"
            if val == "idle":
                return "mdi:sleep"
        return self.entity_description.icon

    @property
    def extra_state_attributes(self) -> dict | None:
        """Return extra state attributes."""
        if not self.coordinator.data:
            return None
        if self.entity_description.key == "scheduled_count":
            return {"scheduled_list": self.coordinator.data.get("scheduled_list", [])}
        if self.entity_description.key == "daemon_status":
            return {
                "remote_control_running": bool(
                    self.coordinator.data.get("remote_control_running", False)
                )
            }
        if self.entity_description.key == "agent_activity":
            activity = self.coordinator.data.get("activity") or {}
            return {
                "is_busy": bool(activity.get("is_busy", False)),
                "lock_active": bool(activity.get("is_busy", False)),
                "current_tool": activity.get("current_tool"),
                "target_file": activity.get("target_file"),
                "reason": activity.get("reason"),
            }
        if self.entity_description.key == "gemini_quota":
            usage = self.coordinator.data.get("usage") or {}
            return {
                "five_hour_remaining_pct": usage.get("gemini_5h_remaining"),
            }
        if self.entity_description.key == "claude_quota":
            usage = self.coordinator.data.get("usage") or {}
            return {
                "five_hour_remaining_pct": usage.get("claude_5h_remaining"),
            }
        return None
