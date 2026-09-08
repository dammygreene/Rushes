"""ClickHouse access: MCP for reads, direct client for seeding."""

from .mcp_client import ClickHouseMcpClient, McpUnavailable

__all__ = ["ClickHouseMcpClient", "McpUnavailable"]
