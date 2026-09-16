"""Custom services for the antigravity_cli integration."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    ATTR_CHAT_ID,
    ATTR_CONVERSATION_ID,
    ATTR_MESSAGE,
    ATTR_MODE,
    ATTR_MODEL,
    ATTR_PROMPT,
    DOMAIN,
    SERVICE_CHAT,
)
from .coordinator import AntigravityDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

CHAT_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_MESSAGE): cv.string,
        vol.Optional(ATTR_PROMPT): cv.string,
        vol.Optional(ATTR_MODE, default="hybrid"): cv.string,
        vol.Optional(ATTR_CHAT_ID): cv.string,
        vol.Optional(ATTR_CONVERSATION_ID): cv.string,
        vol.Optional(ATTR_MODEL): cv.string,
        vol.Optional("entry_id"): cv.string,
    }
)


def _resolve_stream_mode(mode_str: str) -> int:
    """Map mode string to stream_mode integer for add-on API."""
    m = str(mode_str).strip().lower()
    if m in ("1", "fast_local", "fast", "local", "fast_only"):
        return 1
    if m in ("2", "llm_mcp", "mcp"):
        return 2
    return 3  # default: Mode 3 (hybrid / full CLI autonomous agent)


def parse_sse_chat_response(raw_text: str) -> tuple[str, str | None]:
    """Extract answer text and conversation_id from add-on SSE stream."""
    response_text_parts: list[str] = []
    final_text: str | None = None
    conversation_id: str | None = None

    for block in raw_text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        for line in block.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            data_str = line[len("data:") :].strip()
            if not data_str:
                continue
            try:
                event = json.loads(data_str)
            except Exception:
                continue

            event_type = event.get("type")
            content = event.get("content", "")
            if event_type == "session_init" and content:
                conversation_id = str(content)
            elif event_type in ("text", "answer", "final"):
                if content:
                    final_text = str(content)
            elif event_type == "chunk" and content:
                response_text_parts.append(str(content))

    if final_text:
        return final_text.strip(), conversation_id
    if response_text_parts:
        return "".join(response_text_parts).strip(), conversation_id
    return "", conversation_id


async def async_register_services(hass: HomeAssistant) -> None:
    """Register antigravity_cli services."""

    async def async_chat(call: ServiceCall) -> ServiceResponse:
        """Handle antigravity_cli.chat service call."""
        data = call.data
        prompt = (data.get(ATTR_MESSAGE) or data.get(ATTR_PROMPT) or "").strip()
        if not prompt:
            raise HomeAssistantError("Message or prompt cannot be empty.")

        mode_str = str(data.get(ATTR_MODE, "hybrid")).strip()
        stream_mode = _resolve_stream_mode(mode_str)
        chat_id = data.get(ATTR_CHAT_ID) or data.get(ATTR_CONVERSATION_ID)
        model = data.get(ATTR_MODEL)
        target_entry_id = data.get("entry_id")

        domain_data: dict[str, AntigravityDataUpdateCoordinator] = hass.data.get(DOMAIN, {})
        if not domain_data:
            raise HomeAssistantError("Antigravity CLI integration is not configured or ready.")

        coordinator: AntigravityDataUpdateCoordinator | None = None
        if target_entry_id and target_entry_id in domain_data:
            coordinator = domain_data[target_entry_id]
        else:
            coordinator = next(iter(domain_data.values()))

        if not coordinator:
            raise HomeAssistantError("No active Antigravity CLI coordinator found.")

        host_candidates = [coordinator.host]
        for fallback in ["local-antigravity-cli", "127.0.0.1", "localhost"]:
            if fallback not in host_candidates:
                host_candidates.append(fallback)

        headers = {"Content-Type": "application/json"}
        if coordinator.api_key:
            headers["Authorization"] = f"Bearer {coordinator.api_key}"

        payload: dict[str, Any] = {
            "prompt": prompt,
            "stream_mode": stream_mode,
        }
        if chat_id:
            payload["conversation_id"] = str(chat_id).strip()
        if model:
            payload["model"] = str(model).strip()

        http_session = async_get_clientsession(hass)
        last_err = None

        for host in host_candidates:
            url = f"http://{host}:{coordinator.port}/api/chat"
            try:
                async with asyncio.timeout(90):
                    async with http_session.post(url, json=payload, headers=headers) as response:
                        if response.status == 200:
                            raw_body = await response.text()
                            answer, resolved_cid = parse_sse_chat_response(raw_body)
                            return {
                                "response": answer,
                                "conversation_id": resolved_cid or chat_id,
                                "success": True,
                            }
                        elif response.status == 401:
                            raise HomeAssistantError(
                                "Antigravity CLI authentication failed (invalid API key)."
                            )
                        elif response.status == 403:
                            err_msg = (
                                "Chat is disabled in add-on configuration (chat_mode=monitoring)."
                            )
                            try:
                                res_json = await response.json()
                                err_msg = res_json.get("error", err_msg)
                            except Exception:
                                pass
                            raise HomeAssistantError(err_msg)
                        else:
                            last_err = f"HTTP {response.status}"
            except (TimeoutError, aiohttp.ClientError) as err:
                last_err = err
                continue

        raise HomeAssistantError(f"Failed to communicate with Antigravity CLI service: {last_err}")

    hass.services.async_register(
        DOMAIN,
        SERVICE_CHAT,
        async_chat,
        schema=CHAT_SERVICE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )


async def async_unregister_services(hass: HomeAssistant) -> None:
    """Unregister antigravity_cli services."""
    if hass.services.has_service(DOMAIN, SERVICE_CHAT):
        hass.services.async_remove(DOMAIN, SERVICE_CHAT)
