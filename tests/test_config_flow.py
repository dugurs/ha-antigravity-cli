"""Test the antigravity_cli config flow."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from homeassistant import config_entries, data_entry_flow
from homeassistant.core import HomeAssistant

from custom_components.antigravity_cli.const import (
    CONF_HOST,
    CONF_PORT,
    DOMAIN,
)


class MockResponse:
    """Mock aiohttp response."""

    def __init__(self, status: int = 200) -> None:
        self.status = status

    async def __aenter__(self) -> MockResponse:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        pass


async def test_form(hass: HomeAssistant) -> None:
    """Test we get the form and create entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {}

    mock_session = MagicMock()
    mock_session.get.return_value = MockResponse(200)

    with (
        patch(
            "custom_components.antigravity_cli.config_flow.async_get_clientsession",
            return_value=mock_session,
        ),
        patch(
            "custom_components.antigravity_cli.async_setup_entry",
            return_value=True,
        ) as mock_setup_entry,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "127.0.0.1",
                CONF_PORT: 8000,
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result2["title"] == "Antigravity CLI (127.0.0.1:8000)"
    assert result2["data"][CONF_HOST] == "127.0.0.1"
    assert result2["data"][CONF_PORT] == 8000
    assert len(mock_setup_entry.mock_calls) == 1


async def test_options_flow(hass: HomeAssistant) -> None:
    """Test options flow handles gemini settings."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.antigravity_cli.const import (
        CONF_API_KEY,
        CONF_GEMINI_API_KEY,
        CONF_GEMINI_MODEL,
        CONF_POLL_INTERVAL,
        CONF_PROCESSING_MODE,
        MODE_HYBRID,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Antigravity CLI (127.0.0.1:8000)",
        data={
            CONF_HOST: "127.0.0.1",
            CONF_PORT: 8000,
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "init"

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_PROCESSING_MODE: MODE_HYBRID,
            CONF_PORT: 8000,
            CONF_POLL_INTERVAL: 30,
            CONF_API_KEY: "",
            CONF_GEMINI_API_KEY: "AIzaSyTest123",
            CONF_GEMINI_MODEL: "gemini-2.5-flash",
        },
    )
    await hass.async_block_till_done()

    assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result2["data"][CONF_GEMINI_API_KEY] == "AIzaSyTest123"
    assert result2["data"][CONF_GEMINI_MODEL] == "gemini-2.5-flash"
