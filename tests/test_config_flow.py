"""Test the antigravity_cli config flow."""

from unittest.mock import patch
from homeassistant import config_entries, data_entry_flow
from homeassistant.core import HomeAssistant

from custom_components.antigravity_cli.const import (
    CONF_HOST,
    CONF_PORT,
    DOMAIN,
)


async def test_form(hass: HomeAssistant) -> None:
    """Test we get the form and create entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {}

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
    assert result2["data"] == {
        CONF_HOST: "127.0.0.1",
        CONF_PORT: 8000,
    }
