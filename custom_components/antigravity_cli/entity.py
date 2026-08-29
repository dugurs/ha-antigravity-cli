"""Base entity for antigravity_cli."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME
from .coordinator import AntigravityDataUpdateCoordinator


class AntigravityEntity(CoordinatorEntity[AntigravityDataUpdateCoordinator]):
    """Defines a base Antigravity CLI entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AntigravityDataUpdateCoordinator,
        key: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            name=NAME,
            manufacturer="Google DeepMind / Antigravity",
            model="CLI Agent Hub",
            sw_version=coordinator.data.get("version", "1.0.0") if coordinator.data else "1.0.0",
        )
