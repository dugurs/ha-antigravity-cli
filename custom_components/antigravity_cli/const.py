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
    "button",
    "conversation",
]
