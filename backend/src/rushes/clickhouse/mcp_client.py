"""Live connection to the official `mcp-clickhouse` MCP server.

Every archive read in Rushes goes through this: we spawn the real MCP server as
a subprocess, speak MCP over stdio, and call its query tool. Nothing here
simulates ClickHouse.

The session is owned by a single worker task. anyio cancel scopes (used inside
stdio_client and ClientSession) must be entered and exited in the same task, so
request handlers hand jobs to the worker over a queue instead of touching the
session themselves. That also serialises calls, which is fine — one archive
query per search.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, TextContent

from ..config import REPO_ROOT, Settings
from .queries import build_count_sql, build_vector_search_sql, parse_tool_payload

logger = logging.getLogger(__name__)

# mcp-clickhouse renamed its SELECT tool (run_select_query -> run_query in
# 0.6.0), so resolve it from the server's own tool list at startup.
_QUERY_TOOL_CANDIDATES = ("run_query", "run_select_query", "run_chdb_select_query")


class McpUnavailable(RuntimeError):
    """The MCP server could not be started or has died."""


class ClickHouseMcpClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._queue: asyncio.Queue[tuple[str, dict[str, Any], asyncio.Future] | None] = (
            asyncio.Queue()
        )
        self._worker: asyncio.Task[None] | None = None
        self._ready: asyncio.Future[dict[str, Any]] | None = None
        self._lock = asyncio.Lock()
        self.query_tool: str = ""
        self.tool_names: list[str] = []
        self.server_info: dict[str, Any] = {}

    # ------------------------------------------------------------------ public
    @property
    def running(self) -> bool:
        return self._worker is not None and not self._worker.done()

    async def start(self) -> dict[str, Any]:
        """Spawn the server (idempotent) and return its handshake info."""
        async with self._lock:
            if self.running and self._ready is not None and self._ready.done():
                return self._ready.result()
            if self._worker is not None and self._worker.done():
                self._worker = None  # previous session died; start a fresh one
            if self._worker is None:
                loop = asyncio.get_running_loop()
                self._ready = loop.create_future()
                self._worker = loop.create_task(self._run(), name="clickhouse-mcp")
            assert self._ready is not None
            try:
                return await asyncio.wait_for(
                    asyncio.shield(self._ready), self._settings.mcp_startup_timeout
                )
            except asyncio.TimeoutError as exc:
                raise McpUnavailable(
                    f"mcp-clickhouse did not start within "
                    f"{self._settings.mcp_startup_timeout:.0f}s"
                ) from exc

    async def stop(self) -> None:
        worker, self._worker = self._worker, None
        if worker is None:
            return
        await self._queue.put(None)
        try:
            await asyncio.wait_for(worker, timeout=10)
        except asyncio.TimeoutError:
            worker.cancel()
        except Exception as exc:  # noqa: BLE001 - the session already failed
            logger.debug("mcp-clickhouse worker exited with %s", exc)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        await self.start()
        loop = asyncio.get_running_loop()
        future: asyncio.Future[CallToolResult] = loop.create_future()
        await self._queue.put((name, arguments, future))
        result = await asyncio.wait_for(future, self._settings.mcp_call_timeout + 5)
        return _payload_of(result)

    async def run_query(self, sql: str) -> list[dict[str, Any]]:
        """Run one SELECT through MCP and return rows as dicts."""
        await self.start()
        tool = self.query_tool or _QUERY_TOOL_CANDIDATES[0]
        return parse_tool_payload(await self.call_tool(tool, {"query": sql}))

    async def vector_search(self, embedding: list[float], limit: int) -> list[dict[str, Any]]:
        sql = build_vector_search_sql(
            self._settings.qualified_table, embedding, limit=limit
        )
        return await self.run_query(sql)

    async def count_clips(self) -> int:
        rows = await self.run_query(build_count_sql(self._settings.qualified_table))
        if not rows:
            return 0
        return int(next(iter(rows[0].values())))

    # ------------------------------------------------------------------ worker
    async def _run(self) -> None:
        command, args = self._settings.mcp_command()
        params = StdioServerParameters(
            command=command,
            args=args,
            env=self._settings.mcp_env(),
            cwd=str(REPO_ROOT),
        )
        logger.info("starting mcp-clickhouse: %s %s", command, " ".join(args))
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    init = await session.initialize()
                    listing = await session.list_tools()
                    self.tool_names = [tool.name for tool in listing.tools]
                    self.query_tool = next(
                        (n for n in _QUERY_TOOL_CANDIDATES if n in self.tool_names), ""
                    )
                    if not self.query_tool:
                        raise McpUnavailable(
                            f"no query tool exposed by the MCP server; saw {self.tool_names}"
                        )
                    self.server_info = {
                        "server": getattr(init.serverInfo, "name", "mcp-clickhouse"),
                        "version": getattr(init.serverInfo, "version", ""),
                        "protocol": getattr(init, "protocolVersion", ""),
                        "tools": self.tool_names,
                        "query_tool": self.query_tool,
                    }
                    self._settle(self.server_info)
                    await self._serve(session)
        except Exception as exc:  # noqa: BLE001 - surfaced to callers below
            logger.error("mcp-clickhouse session ended: %s", exc)
            self._settle_error(exc)
            self._drain(exc)
            raise

    async def _serve(self, session: ClientSession) -> None:
        timeout = timedelta(seconds=self._settings.mcp_call_timeout)
        while True:
            job = await self._queue.get()
            if job is None:
                return
            name, arguments, future = job
            if future.cancelled():
                continue
            try:
                result = await session.call_tool(name, arguments, read_timeout_seconds=timeout)
            except Exception as exc:  # noqa: BLE001 - handed to the caller
                if not future.cancelled():
                    future.set_exception(exc)
            else:
                if not future.cancelled():
                    future.set_result(result)

    # ------------------------------------------------------------- bookkeeping
    def _settle(self, info: dict[str, Any]) -> None:
        if self._ready is not None and not self._ready.done():
            self._ready.set_result(info)

    def _settle_error(self, exc: BaseException) -> None:
        if self._ready is not None and not self._ready.done():
            self._ready.set_exception(
                McpUnavailable(f"could not start mcp-clickhouse: {exc}")
            )

    def _drain(self, exc: BaseException) -> None:
        while not self._queue.empty():
            job = self._queue.get_nowait()
            if job is None:
                continue
            _, _, future = job
            if not future.done():
                future.set_exception(McpUnavailable(str(exc)))


def _payload_of(result: CallToolResult) -> Any:
    """Pull the useful body out of an MCP tool result."""
    texts = [block.text for block in result.content if isinstance(block, TextContent)]
    body: Any = "\n".join(texts) if texts else result.structuredContent
    if result.isError:
        raise RuntimeError(f"ClickHouse MCP tool error: {str(body)[:500]}")
    return body
