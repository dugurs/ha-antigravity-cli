"""Constants for the antigravity_cli integration."""

from typing import Final

DOMAIN: Final = "antigravity_cli"
NAME: Final = "Antigravity CLI"

# Configuration and options keys
CONF_HOST: Final = "host"
CONF_PORT: Final = "port"
CONF_API_KEY: Final = "api_key"
CONF_POLL_INTERVAL: Final = "poll_interval"
CONF_PROCESSING_MODE: Final = "processing_mode"

# Processing Modes
MODE_HYBRID: Final = "hybrid"
MODE_LLM_MCP: Final = "llm_mcp"
MODE_FAST_LOCAL: Final = "fast_local"

PROCESSING_MODES: Final = [
    MODE_HYBRID,
    MODE_LLM_MCP,
    MODE_FAST_LOCAL,
]

# Defaults
DEFAULT_HOST: Final = "localhost"
DEFAULT_PORT: Final = 8000
DEFAULT_POLL_INTERVAL: Final = 30  # seconds
DEFAULT_PROCESSING_MODE: Final = MODE_HYBRID

# Platforms
PLATFORMS: Final = [
    "sensor",
    "binary_sensor",
    "button",
    "switch",
    "select",
    "conversation",
]

# Addon Options & Chat Modes
CHAT_MODE_FULL: Final = "full"
CHAT_MODE_FAST_ONLY: Final = "fast_only"
CHAT_MODE_MONITORING: Final = "monitoring"
CHAT_MODES: Final = [
    CHAT_MODE_FULL,
    CHAT_MODE_FAST_ONLY,
    CHAT_MODE_MONITORING,
]

# Services
SERVICE_CHAT: Final = "chat"
ATTR_MESSAGE: Final = "message"
ATTR_PROMPT: Final = "prompt"
ATTR_MODE: Final = "mode"
ATTR_CHAT_ID: Final = "chat_id"
ATTR_CONVERSATION_ID: Final = "conversation_id"
ATTR_MODEL: Final = "model"
