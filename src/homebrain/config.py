"""Runtime settings, read once from environment variables.

Every setting has a safe local default, so `make run` works with no .env file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum


class Env(StrEnum):
    LOCAL = "local"
    AWS = "aws"


class Auth401Style(StrEnum):
    # Alexa+ expects 401 without WWW-Authenticate; the MCP spec requires it.
    ALEXA = "alexa"
    SPEC = "spec"


@dataclass(frozen=True, slots=True)
class Settings:
    env: Env
    host: str
    port: int
    public_base_url: str
    log_level: str
    auth_401_style: Auth401Style
    dynamodb_table: str
    dynamodb_endpoint_url: str | None

    @property
    def is_local(self) -> bool:
        return self.env is Env.LOCAL

    @property
    def mcp_resource_uri(self) -> str:
        """Canonical MCP URI. Tokens must carry this as `aud` (RFC 8707)."""
        return f"{self.public_base_url.rstrip('/')}/mcp"


def load_settings(environ: dict[str, str] | None = None) -> Settings:
    e = os.environ if environ is None else environ
    env = Env(e.get("HB_ENV", Env.LOCAL))
    return Settings(
        env=env,
        host=e.get("HB_HOST", "127.0.0.1"),
        port=int(e.get("HB_PORT", "8080")),
        public_base_url=e.get("HB_PUBLIC_BASE_URL", "http://localhost:8080"),
        log_level=e.get("HB_LOG_LEVEL", "INFO"),
        auth_401_style=Auth401Style(
            e.get("AUTH_401_STYLE", Auth401Style.SPEC if env is Env.LOCAL else Auth401Style.ALEXA)
        ),
        dynamodb_table=e.get("HB_DYNAMODB_TABLE", "homebrain"),
        dynamodb_endpoint_url=e.get("HB_DYNAMODB_ENDPOINT_URL") or None,
    )
