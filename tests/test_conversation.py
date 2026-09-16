from unittest.mock import MagicMock, patch

from homeassistant.components.conversation import ConversationEntityFeature
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.antigravity_cli.const import (
    CONF_HOST,
    CONF_PORT,
    DOMAIN,
)
from custom_components.antigravity_cli.conversation import (
    AntigravityConversationEntity,
    async_setup_entry,
)
from custom_components.antigravity_cli.coordinator import AntigravityDataUpdateCoordinator


async def test_conversation_agent(hass: HomeAssistant) -> None:
    """Test conversation agent processing."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Antigravity CLI (127.0.0.1:8000)",
        data={
            CONF_HOST: "127.0.0.1",
            CONF_PORT: 8000,
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.antigravity_cli.coordinator.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.antigravity_cli.conversation.async_get_clientsession",
            return_value=MagicMock(),
        ),
    ):
        coordinator = AntigravityDataUpdateCoordinator(hass, entry)
        coordinator.data = {
            "status": "online",
            "version": "1.1.0",
            "active_sessions": 1,
            "uptime": 100,
            "remote_control_running": False,
            "scheduled_count": 0,
            "scheduled_list": [],
        }
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

        entities: list[AntigravityConversationEntity] = []
        await async_setup_entry(hass, entry, entities.extend)

    assert len(entities) == 1
    entity = entities[0]
    assert isinstance(entity, AntigravityConversationEntity)
    assert entity.supported_features == ConversationEntityFeature.CONTROL
    assert entity.unique_id == f"{entry.entry_id}_assistant"
