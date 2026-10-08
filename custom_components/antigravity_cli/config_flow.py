"""Config flow for antigravity_cli integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_API_KEY,
    CONF_GEMINI_API_KEY,
    CONF_GEMINI_MODEL,
    CONF_HOST,
    CONF_POLL_INTERVAL,
    CONF_PORT,
    CONF_PROCESSING_MODE,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_HOST,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_PROCESSING_MODE,
    DOMAIN,
    GEMINI_MODELS,
    MODE_FAST_LOCAL,
    MODE_FULL_HYBRID,
    MODE_HYBRID,
    NAME,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_API_KEY, default=""): str,
        vol.Optional(CONF_GEMINI_API_KEY, default=""): str,
        vol.Optional(CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL): int,
    }
)


class AntigravityConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for antigravity_cli."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            api_key = user_input.get(CONF_API_KEY, "")

            # Prevent duplicate entries for the same host:port
            unique_id = f"{host}:{port}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            # Test connection to the Antigravity API status endpoint
            session = async_get_clientsession(self.hass)
            url = f"http://{host}:{port}/api/status"
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            try:
                async with session.get(
                    url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        return self.async_create_entry(
                            title=f"{NAME} ({host}:{port})",
                            data=user_input,
                        )
                    elif resp.status == 401:
                        errors["base"] = "invalid_auth"
                    else:
                        errors["base"] = "cannot_connect"
            except (aiohttp.ClientError, TimeoutError):
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception during config flow")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> AntigravityOptionsFlowHandler:
        """Get the options flow for this handler."""
        return AntigravityOptionsFlowHandler(config_entry)


class AntigravityOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for antigravity_cli."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_mode = self._config_entry.options.get(
            CONF_PROCESSING_MODE,
            self._config_entry.data.get(CONF_PROCESSING_MODE, DEFAULT_PROCESSING_MODE),
        )
        if current_mode == "llm_mcp":
            current_mode = MODE_FULL_HYBRID
        elif current_mode not in [MODE_HYBRID, MODE_FULL_HYBRID, MODE_FAST_LOCAL]:
            current_mode = MODE_HYBRID

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_PROCESSING_MODE,
                        default=current_mode,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(
                                    value=MODE_HYBRID,
                                    label="초고속 모드 (로컬 + Gemini API)",
                                ),
                                selector.SelectOptionDict(
                                    value=MODE_FULL_HYBRID,
                                    label="풀 하이브리드 모드 (로컬 + Gemini + 애드온 MCP)",
                                ),
                                selector.SelectOptionDict(
                                    value=MODE_FAST_LOCAL,
                                    label="로컬 전용 모드 (로컬 매칭 전용)",
                                ),
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(
                        CONF_PORT,
                        default=self._config_entry.options.get(
                            CONF_PORT, self._config_entry.data.get(CONF_PORT, DEFAULT_PORT)
                        ),
                    ): int,
                    vol.Optional(
                        CONF_POLL_INTERVAL,
                        default=self._config_entry.options.get(
                            CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
                        ),
                    ): int,
                    vol.Optional(
                        CONF_API_KEY,
                        default=self._config_entry.options.get(
                            CONF_API_KEY, self._config_entry.data.get(CONF_API_KEY, "")
                        ),
                    ): str,
                    vol.Optional(
                        CONF_GEMINI_API_KEY,
                        default=self._config_entry.options.get(
                            CONF_GEMINI_API_KEY,
                            self._config_entry.data.get(CONF_GEMINI_API_KEY, ""),
                        ),
                    ): str,
                    vol.Optional(
                        CONF_GEMINI_MODEL,
                        default=self._config_entry.options.get(
                            CONF_GEMINI_MODEL,
                            self._config_entry.data.get(CONF_GEMINI_MODEL, DEFAULT_GEMINI_MODEL),
                        ),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(
                                    value=model,
                                    label=model,
                                )
                                for model in GEMINI_MODELS
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
        )
