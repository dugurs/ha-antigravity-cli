"""Test the antigravity_cli sensor platform."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.antigravity_cli.const import (
    CONF_HOST,
    CONF_PORT,
    DOMAIN,
)
from custom_components.antigravity_cli.coordinator import AntigravityDataUpdateCoordinator
from custom_components.antigravity_cli.sensor import (
    AntigravitySensor,
    async_setup_entry,
)


async def test_sensor_setup_and_values(hass: HomeAssistant) -> None:
    """Test sensor entities setup and native values."""
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
            "active_sessions": 2,
            "uptime": 3600,
            "memory_usage": 512.5,
            "cpu_usage": 15.0,
            "remote_control_running": True,
            "activity": {
                "state": "idle",
                "is_busy": False,
                "current_tool": None,
                "target_file": None,
                "reason": None,
            },
            "scheduled_count": 3,
            "scheduled_list": [{"id": 1, "action": "turn_off"}],
            "usage": {
                "gemini_weekly_remaining": 85.5,
                "claude_weekly_remaining": 92.0,
            },
        }
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

        entities: list[AntigravitySensor] = []
        await async_setup_entry(hass, entry, entities.extend)

        assert len(entities) == 10
        sensor_by_key = {entity.entity_description.key: entity for entity in entities}

        assert sensor_by_key["status"].native_value == "online"
        assert sensor_by_key["daemon_status"].native_value == "running"
        assert sensor_by_key["daemon_status"].extra_state_attributes == {
            "remote_control_running": True
        }
        assert sensor_by_key["agent_activity"].native_value == "idle"
        assert sensor_by_key["agent_activity"].icon == "mdi:sleep"
        assert sensor_by_key["agent_activity"].extra_state_attributes == {
            "is_busy": False,
            "lock_active": False,
            "current_tool": None,
            "target_file": None,
            "reason": None,
        }
        assert sensor_by_key["active_sessions"].native_value == 2
        assert sensor_by_key["uptime"].native_value == 3600
        assert sensor_by_key["memory_usage"].native_value == 512.5
        assert sensor_by_key["cpu_usage"].native_value == 15.0
        assert sensor_by_key["scheduled_count"].native_value == 3
        assert sensor_by_key["scheduled_count"].extra_state_attributes == {
            "scheduled_list": [{"id": 1, "action": "turn_off"}]
        }
        assert sensor_by_key["gemini_quota"].native_value == 85.5
        assert sensor_by_key["gemini_quota"].native_unit_of_measurement == "%"
        assert sensor_by_key["claude_quota"].native_value == 92.0
        assert sensor_by_key["claude_quota"].native_unit_of_measurement == "%"

        # Test file_working activity state
        coordinator.data["activity"] = {
            "state": "file_working",
            "is_busy": True,
            "current_tool": "replace_file_content",
            "target_file": "config.yaml",
            "reason": "writing_file",
        }
        assert sensor_by_key["agent_activity"].native_value == "file_working"
        assert sensor_by_key["agent_activity"].icon == "mdi:file-edit"
        assert sensor_by_key["agent_activity"].extra_state_attributes["lock_active"] is True
        assert (
            sensor_by_key["agent_activity"].extra_state_attributes["target_file"] == "config.yaml"
        )

        # Test thinking activity state
        coordinator.data["activity"]["state"] = "thinking"
        assert sensor_by_key["agent_activity"].native_value == "thinking"
        assert sensor_by_key["agent_activity"].icon == "mdi:brain"

        # Test executing_tool activity state
        coordinator.data["activity"]["state"] = "executing_tool"
        assert sensor_by_key["agent_activity"].native_value == "executing_tool"
        assert sensor_by_key["agent_activity"].icon == "mdi:tools"

        # Test stopped daemon state
        coordinator.data["remote_control_running"] = False
        assert sensor_by_key["daemon_status"].native_value == "stopped"
        assert sensor_by_key["daemon_status"].extra_state_attributes == {
            "remote_control_running": False
        }

        # Test offline state
        coordinator.data["status"] = "offline"
        assert sensor_by_key["daemon_status"].native_value == "offline"
        assert sensor_by_key["agent_activity"].native_value == "offline"
        assert sensor_by_key["agent_activity"].icon == "mdi:cloud-off-outline"
