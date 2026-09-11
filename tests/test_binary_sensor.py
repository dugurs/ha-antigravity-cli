"""Test the antigravity_cli binary_sensor platform."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.antigravity_cli.binary_sensor import (
    AntigravityBinarySensor,
    async_setup_entry,
)
from custom_components.antigravity_cli.const import (
    CONF_HOST,
    CONF_PORT,
    DOMAIN,
)
from custom_components.antigravity_cli.coordinator import AntigravityDataUpdateCoordinator


async def test_binary_sensor_setup_and_values(hass: HomeAssistant) -> None:
    """Test binary_sensor entities setup, is_on, and availability."""
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
        coordinator.data = {
            "status": "online",
            "remote_control_running": True,
        }
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

        entities: list[AntigravityBinarySensor] = []
        await async_setup_entry(hass, entry, entities.extend)

        assert len(entities) == 1
        sensor = entities[0]

        assert sensor.entity_description.key == "remote_control_daemon"
        assert sensor.device_class == BinarySensorDeviceClass.RUNNING
        assert sensor.is_on is True
        assert sensor.available is True

        # When daemon is stopped
        coordinator.data["remote_control_running"] = False
        assert sensor.is_on is False
        assert sensor.available is True

        # When server is offline
        coordinator.data["status"] = "offline"
        assert sensor.available is False
