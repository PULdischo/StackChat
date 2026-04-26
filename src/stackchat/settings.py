"""Runtime configuration loaded from environment variables.

All settings have sensible defaults so the server works out-of-the-box
without any configuration. Override via environment variables or a `.env` file
(loaded automatically by pydantic-settings).

Environment variables
---------------------
STACKCHAT_CATALOG_URL       Base URL of the Blacklight catalog instance.
                            Default: https://catalog.princeton.edu
STACKCHAT_USER_AGENT        User-Agent header sent with every request.
                            Include a contact URL so the catalog operators can
                            reach you if needed.
                            Default: stackchat/0.1 (+https://github.com/apjanco/StackChat)
STACKCHAT_HTTP_TIMEOUT      Request timeout in seconds.  Default: 15
STACKCHAT_CACHE_MAX_SIZE    Maximum number of cached responses.  Default: 512
STACKCHAT_CACHE_TTL         Cache time-to-live in seconds.  Default: 300
STACKCHAT_RETRY_ATTEMPTS    Max HTTP retry attempts on 429/5xx.  Default: 3
STACKCHAT_TRANSPORT         MCP transport: "stdio" (local) or "streamable-http"
                            (Cloud Run / remote).  Default: stdio
PORT                        Port to bind when using streamable-http transport.
                            Cloud Run injects this automatically.  Default: 8080
"""

from __future__ import annotations

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="STACKCHAT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    catalog_url: str = "https://catalog.princeton.edu"
    user_agent: str = "stackchat/0.1 (+https://github.com/apjanco/StackChat)"
    http_timeout: float = 15.0
    cache_max_size: int = 512
    cache_ttl: int = 300
    retry_attempts: int = 3
    # "stdio" for local use; "streamable-http" for Cloud Run / remote deployments.
    transport: str = "stdio"


def get_port() -> int:
    """Return the port to bind.

    Cloud Run injects PORT (not STACKCHAT_PORT), so we read it directly from
    the environment rather than going through pydantic-settings.
    """
    return int(os.environ.get("PORT", 8080))


# Module-level singleton — import this everywhere.
settings = Settings()
