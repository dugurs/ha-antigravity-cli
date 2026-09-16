"""DataUpdateCoordinator for antigravity_cli."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_API_KEY,
    CONF_HOST,
    CONF_POLL_INTERVAL,
    CONF_PORT,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class AntigravityDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching data from Antigravity CLI service."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self.config_entry = entry
        self.host = entry.options.get(CONF_HOST, entry.data[CONF_HOST])
        self.port = entry.options.get(CONF_PORT, entry.data[CONF_PORT])
        self.api_key = entry.options.get(CONF_API_KEY, entry.data.get(CONF_API_KEY))
        self.session = async_get_clientsession(hass)

        poll_interval = entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{self.host}_{self.port}",
            update_interval=timedelta(seconds=poll_interval),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Antigravity CLI."""
        host_candidates = [self.host]
        for fallback in ["local-antigravity-cli", "127.0.0.1", "localhost"]:
            if fallback not in host_candidates:
                host_candidates.append(fallback)

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        last_err = None
        for host in host_candidates:
            url = f"http://{host}:{self.port}/api/status"
            try:
                async with asyncio.timeout(5):
                    async with self.session.get(url, headers=headers) as response:
                        if response.status == 200:
                            # Remember working host
                            self.host = host
                            return await response.json()
                        elif response.status == 401:
                            raise UpdateFailed("Antigravity CLI authentication failed")
            except (TimeoutError, aiohttp.ClientError) as err:
                last_err = err
                continue

        # Fallback data if server is offline or unreachable
        _LOGGER.debug("Antigravity CLI offline or unreachable on all endpoints: %s", last_err)
        return {
            "status": "offline",
            "version": "unknown",
            "active_sessions": 0,
            "uptime": 0,
            "remote_control_running": False,
            "activity": {
                "state": "offline",
                "is_busy": False,
                "reason": None,
                "current_tool": None,
                "target_file": None,
            },
            "options": {
                "auto_start_remote_control": False,
                "enable_terminal": True,
                "chat_mode": "full",
            },
            "usage": {
                "available": False,
                "gemini_weekly_remaining": None,
                "gemini_5h_remaining": None,
                "claude_weekly_remaining": None,
                "claude_5h_remaining": None,
            },
            "scheduled_count": 0,
            "scheduled_list": [],
        }
