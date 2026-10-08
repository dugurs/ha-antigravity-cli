"""Direct client for Google Gemini REST API."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from .const import DEFAULT_GEMINI_MODEL

_LOGGER = logging.getLogger(__name__)

# Standard function calling tools for smart home device control
TOOL_CONTROL_DEVICE: list[dict[str, Any]] = [
    {
        "functionDeclarations": [
            {
                "name": "control_device",
                "description": (
                    "Control a smart home device or service in Home Assistant when requested by the user. "
                    "Examples: turn on/off light, set air conditioner temperature, open/close cover, toggle switch."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "domain": {
                            "type": "STRING",
                            "description": "Domain of the entity: light, switch, climate, cover, fan, media_player, automation, script",
                        },
                        "service": {
                            "type": "STRING",
                            "description": "Service to call: turn_on, turn_off, toggle, open_cover, close_cover, set_temperature, media_play, media_pause",
                        },
                        "entity_id": {
                            "type": "STRING",
                            "description": "Target entity ID, comma-separated list of IDs, or 'all'",
                        },
                        "extra_data": {
                            "type": "OBJECT",
                            "description": "Optional extra parameters: e.g. {'temperature': 24} or {'brightness_pct': 80}",
                        },
                        "speech": {
                            "type": "STRING",
                            "description": "Concise, polite Korean confirmation to speak to the user, e.g. '거실 조명을 켰습니다.'",
                        },
                    },
                    "required": ["domain", "service", "entity_id", "speech"],
                },
            }
        ]
    }
]


async def async_call_gemini_api(
    session: aiohttp.ClientSession,
    api_key: str,
    model: str | None,
    prompt: str,
    system_instruction: str,
    history: list[dict[str, Any]] | None = None,
    tools: list[dict[str, Any]] | None = None,
    timeout_sec: float = 12.0,
) -> tuple[str | None, list[dict[str, Any]] | None, str | None]:
    """Call Google Gemini REST API directly with low latency (~1.0s).

    Returns:
        (text_response, function_calls, error_message)
    """
    if not api_key:
        return None, None, "Gemini API key is not configured"

    target_model = model or DEFAULT_GEMINI_MODEL
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={api_key}"

    contents: list[dict[str, Any]] = []
    if history:
        contents.extend(history)
    contents.append({"role": "user", "parts": [{"text": prompt}]})

    payload: dict[str, Any] = {
        "systemInstruction": {
            "parts": [{"text": system_instruction}],
        },
        "contents": contents,
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 800,
        },
    }

    if tools:
        payload["tools"] = tools

    try:
        async with asyncio.timeout(timeout_sec):
            async with session.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    candidates = data.get("candidates", [])
                    if not candidates:
                        return None, None, "No candidates returned from Gemini"

                    first_candidate = candidates[0]
                    content = first_candidate.get("content", {})
                    parts = content.get("parts", [])

                    text_parts = []
                    func_calls = []
                    for part in parts:
                        if "text" in part and part["text"]:
                            text_parts.append(part["text"])
                        if "functionCall" in part:
                            func_calls.append(part["functionCall"])

                    reply_text = "".join(text_parts).strip() if text_parts else None
                    return reply_text, func_calls or None, None

                # Non-200 error response
                try:
                    error_json = await response.json()
                    error_detail = error_json.get("error", {}).get("message", str(error_json))
                except Exception:
                    error_detail = await response.text()
                _LOGGER.warning("Gemini API error (HTTP %d): %s", response.status, error_detail)
                return None, None, f"HTTP {response.status}: {error_detail}"

    except TimeoutError:
        _LOGGER.warning("Gemini API call timed out after %s seconds", timeout_sec)
        return None, None, "Gemini API call timed out"
    except aiohttp.ClientError as err:
        _LOGGER.warning("Gemini API client error: %s", err)
        return None, None, f"ClientError: {err}"
    except Exception as ex:
        _LOGGER.exception("Unexpected error calling Gemini API: %s", ex)
        return None, None, str(ex)
