"""Switch platform for antigravity_cli."""

from __future__ import annotations

import asyncio
import logging

import aiohttp
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AntigravityDataUpdateCoordinator
from .entity import AntigravityEntity

_LOGGER = logging.getLogger(__name__)

DAEMON_SWITCH_TYPES: tuple[SwitchEntityDescription, ...] = (
    SwitchEntityDescription(
        key="remote_control_running",
        translation_key="remote_control",
        icon="mdi:remote",
    ),
)

OPTION_SWITCH_TYPES: tuple[SwitchEntityDescription, ...] = (
    SwitchEntityDescription(
        key="auto_start_remote_control",
        translation_key="auto_start_remote_control",
        icon="mdi:autorenew",
    ),
    SwitchEntityDescription(
        key="enable_terminal",
        translation_key="enable_terminal",
        icon="mdi:console",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the switch platform."""
    coordinator: AntigravityDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SwitchEntity] = [
        AntigravityDaemonSwitch(coordinator, description) for description in DAEMON_SWITCH_TYPES
    ]
    entities.extend(
        AntigravityOptionSwitch(coordinator, description) for description in OPTION_SWITCH_TYPES
    )

    async_add_entities(entities)


class AntigravityDaemonSwitch(AntigravityEntity, SwitchEntity):
    """Antigravity switch entity -- controls the `agy remote-control serve`
    daemon via the addon's REST API (start()/stop() in the addon's
    core/remote_control.py), the same endpoints the addon's own web UI
    toggle uses."""

    entity_description: SwitchEntityDescription

    def __init__(
        self,
        coordinator: AntigravityDataUpdateCoordinator,
        description: SwitchEntityDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return true if the remote-control daemon is running."""
        if not self.coordinator.data:
            return None
        return bool(self.coordinator.data.get(self.entity_description.key))

    async def _async_call(self, action: str) -> None:
        """POST to /api/remote_control/<action> on the addon, reusing the
        coordinator's already-resolved host (see its own fallback-host logic
        in _async_update_data) and auth header."""
        headers = {}
        if self.coordinator.api_key:
            headers["Authorization"] = f"Bearer {self.coordinator.api_key}"

        url = f"http://{self.coordinator.host}:{self.coordinator.port}/api/remote_control/{action}"
        try:
            async with asyncio.timeout(10):
                async with self.coordinator.session.post(url, headers=headers) as response:
                    data = {}
                    try:
                        data = await response.json()
                    except Exception:
                        pass

                    if response.status == 409 or (
                        data.get("ok") is False and data.get("error") == "busy"
                    ):
                        msg = (
                            data.get("message")
                            or "에이전트가 작업 중이어서 데몬 정지가 거부되었습니다 (끄기 락)."
                        )
                        raise HomeAssistantError(msg)

                    if response.status != 200:
                        _LOGGER.error(
                            "Antigravity CLI remote-control %s failed: HTTP %s",
                            action,
                            response.status,
                        )
                        raise HomeAssistantError(
                            f"Antigravity CLI remote-control {action} failed: HTTP {response.status}"
                        )
        except (TimeoutError, aiohttp.ClientError) as err:
            _LOGGER.error("Antigravity CLI remote-control %s failed: %s", action, err)
            raise HomeAssistantError(
                f"Antigravity CLI remote-control {action} connection failed: {err}"
            ) from err

        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs) -> None:
        """Start the remote-control daemon."""
        await self._async_call("start")

    async def async_turn_off(self, **kwargs) -> None:
        """Stop the remote-control daemon, checking activity lock first."""
        if self.coordinator.data:
            activity = self.coordinator.data.get("activity") or {}
            if activity.get("is_busy") or activity.get("state") in (
                "thinking",
                "file_working",
                "executing_tool",
            ):
                state_desc = {
                    "file_working": "파일 작업",
                    "thinking": "추론/답변 생성",
                    "executing_tool": "도구 실행",
                }.get(activity.get("state"), activity.get("state", "작업"))
                target = activity.get("target_file") or activity.get("current_tool")
                detail = f" ({target})" if target else ""
                raise HomeAssistantError(
                    f"에이전트가 현재 {state_desc} 중입니다{detail}. "
                    "파일 및 데이터 손상을 방지하기 위해 끄기 락(Lock)이 활성화되어 정지할 수 없습니다."
                )

        await self._async_call("stop")


class AntigravityOptionSwitch(AntigravityEntity, SwitchEntity):
    """Switch entity to control add-on configuration options."""

    entity_description: SwitchEntityDescription

    def __init__(
        self,
        coordinator: AntigravityDataUpdateCoordinator,
        description: SwitchEntityDescription,
    ) -> None:
        """Initialize the option switch."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return true if the option is enabled."""
        if not self.coordinator.data:
            return None
        options = self.coordinator.data.get("options") or {}
        default_val = True if self.entity_description.key == "enable_terminal" else False
        return bool(options.get(self.entity_description.key, default_val))

    async def _async_set_option(self, enabled: bool) -> None:
        """Send option update to /api/options on the add-on."""
        headers = {"Content-Type": "application/json"}
        if self.coordinator.api_key:
            headers["Authorization"] = f"Bearer {self.coordinator.api_key}"

        url = f"http://{self.coordinator.host}:{self.coordinator.port}/api/options"
        payload = {self.entity_description.key: enabled}
        try:
            async with asyncio.timeout(10):
                async with self.coordinator.session.post(
                    url, json=payload, headers=headers
                ) as response:
                    if response.status != 200:
                        _LOGGER.error(
                            "Failed to update Antigravity CLI option %s: HTTP %s",
                            self.entity_description.key,
                            response.status,
                        )
                        raise HomeAssistantError(
                            f"Failed to update option {self.entity_description.key}: HTTP {response.status}"
                        )
        except (TimeoutError, aiohttp.ClientError) as err:
            _LOGGER.error(
                "Connection failed while updating Antigravity CLI option %s: %s",
                self.entity_description.key,
                err,
            )
            raise HomeAssistantError(
                f"Connection error updating option {self.entity_description.key}: {err}"
            ) from err

        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs) -> None:
        """Enable the add-on option."""
        await self._async_set_option(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Disable the add-on option."""
        await self._async_set_option(False)


# Backward compatibility alias
AntigravitySwitch = AntigravityDaemonSwitch
