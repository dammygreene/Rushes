"""Process-wide singletons: the MCP session and one shared HTTP client.

Kept in its own module so tools can reach them without importing the FastAPI app
(and without each tool opening its own connection pool).
"""

from __future__ import annotations

import logging

import httpx

from .clickhouse import ClickHouseMcpClient
from .config import get_settings

logger = logging.getLogger(__name__)

USER_AGENT = "Rushes/0.1 (agentic video search; +https://github.com/rushes-app)"

_mcp_client: ClickHouseMcpClient | None = None
_http: httpx.AsyncClient | None = None


def get_mcp_client() -> ClickHouseMcpClient:
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = ClickHouseMcpClient(get_settings())
    return _mcp_client


def get_http() -> httpx.AsyncClient:
    global _http
    if _http is None or _http.is_closed:
        _http = httpx.AsyncClient(
            timeout=httpx.Timeout(12.0, connect=5.0),
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
    return _http


async def shutdown() -> None:
    global _http, _mcp_client
    if _http is not None and not _http.is_closed:
        await _http.aclose()
    _http = None
    if _mcp_client is not None:
        await _mcp_client.stop()
    _mcp_client = None
