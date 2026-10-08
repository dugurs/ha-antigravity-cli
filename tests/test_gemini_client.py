"""Test the Gemini client module."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from custom_components.antigravity_cli.gemini_client import (
    TOOL_CONTROL_DEVICE,
    async_call_gemini_api,
)


class MockClientResponse:
    """Mock aiohttp response."""

    def __init__(self, status: int = 200, json_data: dict | None = None) -> None:
        self.status = status
        self._json_data = json_data or {}

    async def json(self) -> dict:
        return self._json_data

    async def text(self) -> str:
        return str(self._json_data)

    async def __aenter__(self) -> MockClientResponse:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        pass


async def test_gemini_client_missing_key() -> None:
    """Test calling Gemini client without API key."""
    session = MagicMock()
    text, tools, err = await async_call_gemini_api(
        session=session,
        api_key="",
        model="gemini-2.5-flash",
        prompt="안녕하세요",
        system_instruction="지침",
    )
    assert text is None
    assert tools is None
    assert "not configured" in (err or "")


async def test_gemini_client_success_text() -> None:
    """Test successful Gemini API text generation."""
    session = MagicMock()
    session.post.return_value = MockClientResponse(
        200,
        {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "안녕하세요! 무엇을 도와드릴까요?"}],
                        "role": "model",
                    }
                }
            ]
        },
    )

    text, tools, err = await async_call_gemini_api(
        session=session,
        api_key="AIzaSyTest",
        model="gemini-2.5-flash",
        prompt="안녕",
        system_instruction="지침",
        history=[{"role": "user", "parts": [{"text": "이전 대화"}]}],
        tools=TOOL_CONTROL_DEVICE,
    )

    assert text == "안녕하세요! 무엇을 도와드릴까요?"
    assert tools is None
    assert err is None


async def test_gemini_client_success_function_call() -> None:
    """Test successful Gemini API function calling."""
    session = MagicMock()
    session.post.return_value = MockClientResponse(
        200,
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "name": "control_device",
                                    "args": {
                                        "domain": "light",
                                        "service": "turn_on",
                                        "entity_id": "light.living_room",
                                        "speech": "거실 불을 켰습니다.",
                                    },
                                }
                            }
                        ],
                        "role": "model",
                    }
                }
            ]
        },
    )

    text, tools, err = await async_call_gemini_api(
        session=session,
        api_key="AIzaSyTest",
        model=None,
        prompt="불 켜줘",
        system_instruction="지침",
    )

    assert text is None
    assert tools is not None
    assert len(tools) == 1
    assert tools[0]["name"] == "control_device"
    assert tools[0]["args"]["entity_id"] == "light.living_room"
    assert err is None


async def test_gemini_client_error_response() -> None:
    """Test non-200 HTTP response from Gemini API."""
    session = MagicMock()
    session.post.return_value = MockClientResponse(
        400,
        {"error": {"code": 400, "message": "API_KEY_INVALID"}},
    )

    text, tools, err = await async_call_gemini_api(
        session=session,
        api_key="BadKey",
        model=None,
        prompt="안녕",
        system_instruction="지침",
    )

    assert text is None
    assert tools is None
    assert "400" in (err or "")
    assert "API_KEY_INVALID" in (err or "")


async def test_gemini_client_timeout() -> None:
    """Test timeout when calling Gemini API."""
    session = MagicMock()

    class TimeoutPost:
        async def __aenter__(self):
            await asyncio.sleep(2)

        async def __aexit__(self, exc_type, exc, tb):
            pass

    session.post.return_value = TimeoutPost()

    text, tools, err = await async_call_gemini_api(
        session=session,
        api_key="AIzaSyTest",
        model=None,
        prompt="안녕",
        system_instruction="지침",
        timeout_sec=0.01,
    )

    assert text is None
    assert tools is None
    assert "timed out" in (err or "").lower()
