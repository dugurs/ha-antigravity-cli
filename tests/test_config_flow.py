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
