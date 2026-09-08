"""The four search tools the agent fans out to.

Each is a plain async function with a typed signature and a docstring, which is
all ADK needs to expose it as a tool. Each returns the same envelope shape (see
`_common.envelope`) so the fan-out step can treat them identically.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from ..models import Source
from .archive import search_archive
from .archive_org import search_archive_org
from .pexels import search_pexels
from .youtube import search_youtube

ToolFn = Callable[..., Awaitable[dict[str, Any]]]

# Source -> tool. The agent walks this to decide what to call in parallel.
TOOLS: dict[Source, ToolFn] = {
    Source.ARCHIVE: search_archive,
    Source.YOUTUBE: search_youtube,
    Source.PUBLIC_DOMAIN: search_archive_org,
    Source.STOCK: search_pexels,
}

ALL_TOOLS: tuple[ToolFn, ...] = (
    search_archive,
    search_youtube,
    search_archive_org,
    search_pexels,
)

__all__ = [
    "ALL_TOOLS",
    "TOOLS",
    "ToolFn",
    "search_archive",
    "search_archive_org",
    "search_pexels",
    "search_youtube",
]
