"""Typed configuration for the Rushes backend.

Every value comes from the environment (see .env.example at the repo root).
Nothing in here reaches out to the network — construct clients from these
settings instead of reading os.environ directly, so that a missing key fails
loudly and in one place.
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


def _csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


class Settings(BaseSettings):
    """Runtime configuration, loaded from <repo>/.env then the process env."""

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", REPO_ROOT / "backend" / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- app ---
    log_level: str = "INFO"
    port: int = 8080
    public_base_url: str = "http://localhost:8080"
    allowed_origins_raw: str = Field("http://localhost:3000", alias="allowed_origins")
    api_token: str = ""

    # --- Gemini ---
    google_genai_use_vertexai: bool = False
    google_api_key: str = ""
    google_cloud_project: str = ""
    google_cloud_location: str = "us-central1"
    gemini_model: str = "gemini-3.6-flash"
    gemini_embed_model: str = "gemini-embedding-001"
    embedding_dim: int = 768

    # --- ClickHouse ---
    clickhouse_host: str = ""
    clickhouse_port: int = 8443
    clickhouse_user: str = "default"
    clickhouse_password: str = ""
    clickhouse_secure: bool = True
    clickhouse_verify: bool = True
    clickhouse_database: str = "default"
    clickhouse_table: str = "archive_clips"

    # --- MCP ---
    mcp_clickhouse_command: str = ""
    mcp_clickhouse_args_raw: str = Field("", alias="mcp_clickhouse_args")
    mcp_startup_timeout: float = 90.0
    mcp_call_timeout: float = 45.0

    # --- external sources ---
    youtube_api_key: str = ""
    youtube_video_license: str = "any"
    pexels_api_key: str = ""
    archive_org_base: str = "https://archive.org"

    # --- search tuning ---
    search_top_k_archive: int = 8
    search_top_k_external: int = 6
    result_limit: int = 24
    ranking_strategy: str = "diverse"
    enable_llm_reasons: bool = True

    # ------------------------------------------------------------------ derived
    @property
    def allowed_origins(self) -> list[str]:
        return _csv(self.allowed_origins_raw)

    @property
    def clips_dir(self) -> Path:
        return REPO_ROOT / "data" / "clips"

    @property
    def qualified_table(self) -> str:
        return f"{self.clickhouse_database}.{self.clickhouse_table}"

    @property
    def gemini_configured(self) -> bool:
        if self.google_genai_use_vertexai:
            return bool(self.google_cloud_project)
        return bool(self.google_api_key)

    @property
    def clickhouse_configured(self) -> bool:
        return bool(self.clickhouse_host)

    # ------------------------------------------------------------------ genai env
    def apply_genai_env(self) -> None:
        """Mirror the resolved Gemini settings into the process environment.

        ADK constructs its own `google.genai.Client()` with no arguments (see
        `google/adk/models/google_llm.py`), so it reads `GOOGLE_API_KEY` and
        `GOOGLE_GENAI_USE_VERTEXAI` from os.environ rather than from here. A key
        that only lives in .env therefore raises "No API key was provided" the
        moment the planner runs, and the search quietly degrades to a keyword
        plan. Call this before building any ADK agent.
        """
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = (
            "true" if self.google_genai_use_vertexai else "false"
        )
        for key, value in (
            ("GOOGLE_API_KEY", self.google_api_key),
            ("GOOGLE_CLOUD_PROJECT", self.google_cloud_project),
            ("GOOGLE_CLOUD_LOCATION", self.google_cloud_location),
        ):
            if value:
                os.environ[key] = value

    # --------------------------------------------------------------------- MCP
    def mcp_command(self) -> tuple[str, list[str]]:
        """Resolve the command that starts the mcp-clickhouse server.

        Order of preference: explicit override, the isolated venv created by
        scripts/setup, then `uvx mcp-clickhouse` as a last resort. The server
        lives in its own venv on purpose: it depends on fastmcp>=4 while the
        ADK client side needs mcp<2.
        """
        if self.mcp_clickhouse_command:
            return self.mcp_clickhouse_command, _csv_args(self.mcp_clickhouse_args_raw)

        bin_dir = "Scripts" if sys.platform == "win32" else "bin"
        suffix = ".exe" if sys.platform == "win32" else ""
        local = REPO_ROOT / "mcp-server" / ".venv" / bin_dir / f"mcp-clickhouse{suffix}"
        if local.exists():
            return str(local), []
        return "uvx", ["mcp-clickhouse"]

    def mcp_env(self) -> dict[str, str]:
        """Environment for the MCP server subprocess: ClickHouse creds only."""
        env = {
            "CLICKHOUSE_HOST": self.clickhouse_host,
            "CLICKHOUSE_PORT": str(self.clickhouse_port),
            "CLICKHOUSE_USER": self.clickhouse_user,
            "CLICKHOUSE_PASSWORD": self.clickhouse_password,
            "CLICKHOUSE_SECURE": str(self.clickhouse_secure).lower(),
            "CLICKHOUSE_VERIFY": str(self.clickhouse_verify).lower(),
            "CLICKHOUSE_DATABASE": self.clickhouse_database,
            "CLICKHOUSE_MCP_SERVER_TRANSPORT": "stdio",
        }
        # Inherit just enough of the parent env for Python/TLS to work.
        for key in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME", "USERPROFILE",
                    "APPDATA", "LOCALAPPDATA", "SSL_CERT_FILE", "PYTHONUTF8"):
            value = os.environ.get(key)
            if value:
                env[key] = value
        env.setdefault("PYTHONUTF8", "1")
        return env


def _csv_args(value: str) -> list[str]:
    """Split an args string on whitespace or commas, whichever the user used."""
    if "," in value:
        return _csv(value)
    return value.split()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
