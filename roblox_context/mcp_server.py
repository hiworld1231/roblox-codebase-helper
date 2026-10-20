"""Seven compact tools. No Studio write or playtest endpoints."""
from __future__ import annotations

import asyncio
import json
from mcp.types import TextContent
from typing import Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .store import ContextError


def create_server(service):
    server = FastMCP("Roblox Context", log_level="WARNING", instructions=(
        "Resume with project_overview(resume=True) for an explicit session, then relevant project map. "
        "Select an explicit session; search metadata, then request targeted graph/context and necessary source ranges. "
        "Unindexed source means unknown dependencies, especially reverse impact. "
        "Use the existing official Studio MCP for edits and runtime tests. "
        "Expand context and verification when correctness needs it. Keep checkpoints concise."
    ))

    async def call(fn, *args):
        try:
            value = await asyncio.to_thread(fn, *args)
        except ContextError as error:
            value = {"error": {"code": error.code, "message": error.message}}
        return [TextContent(type="text", text=json.dumps(value, ensure_ascii=False, separators=(",", ":")))]

    @server.tool(structured_output=False)
    async def project_overview(session_id: str | None = None, resume: bool = False,
                               limit: int = Field(default=20, ge=1, le=100), cursor: str | None = None,
                               budget_tokens: int = Field(default=4000, ge=256, le=24000)) -> list[TextContent]:
        """List sessions or selected identity. resume=True adds recorded checkpoint and coalesced changes, no source. Continuation omits checkpoint."""
        return await call(service.overview, session_id, resume, limit, cursor, budget_tokens)

    @server.tool(structured_output=False)
    async def project_search(session_id: str, text: str, kind: str | None = None,
                             limit: int = Field(default=20, ge=1, le=100), cursor: str | None = None,
                             budget_tokens: int = Field(default=4000, ge=256, le=24000),
                             search_in: Literal["metadata", "source"] = "metadata", scope_id: str | None = None) -> list[TextContent]:
        """Default metadata/symbol search. Source mode requires scope_id; literal case-insensitive text, max 20 scripts/page. Text hits are navigation, not dependency proof."""
        return await call(service.search, session_id, text, kind, limit, cursor, budget_tokens, search_in, scope_id)

    @server.tool(structured_output=False)
    async def graph_query(session_id: str, action: Literal["dependencies", "references", "impact", "diagnostics"],
                          object_id: str, analyze_ids: list[str] = Field(default_factory=list, max_length=19),
                          depth: int = Field(default=1, ge=0, le=3),
                          limit: int = Field(default=20, ge=1, le=100), cursor: str | None = None,
                          budget_tokens: int = Field(default=4000, ge=256, le=24000)) -> list[TextContent]:
        """Analyze selected roots only. For reverse links, explicitly include candidate callers in analyze_ids."""
        return await call(service.query, session_id, action, object_id, analyze_ids, depth, limit, cursor, budget_tokens)

    @server.tool(structured_output=False)
    async def get_context(session_id: str, object_ids: list[str] = Field(min_length=1, max_length=20),
                          budget_tokens: int = Field(default=4000, ge=256, le=24000),
                          depth: int = Field(default=1, ge=0, le=3), include_source: bool = False, cursor: str | None = None) -> list[TextContent]:
        """Selected nodes/dependencies first, optional source lines last. Explicit truncation; no hidden full scan."""
        return await call(service.context, session_id, object_ids, budget_tokens, depth, include_source, cursor)

    @server.tool(structured_output=False)
    async def read_source(session_id: str, object_id: str,
                          start_line: int = Field(ge=1), end_line: int = Field(ge=1),
                          expected_revision: int | None = None,
                          budget_tokens: int = Field(default=4000, ge=256, le=24000), known_view: dict | None = None) -> list[TextContent]:
        """Read up to 500 lines. known_view: session/objectId/sourceHash/startLine/endLine from text STILL in agent context; matching covered text yields unchanged. Old-chat/cache hashes do not establish retained text."""
        return await call(service.read, session_id, object_id, start_line, end_line, expected_revision, budget_tokens, known_view)

    @server.tool(structured_output=False)
    async def changed_context(session_id: str, since_revision: int = Field(ge=0),
                              limit: int = Field(default=20, ge=1, le=100), cursor: str | None = None,
                              budget_tokens: int = Field(default=4000, ge=256, le=24000)) -> list[TextContent]:
        """Durable revision changes, IDs only. Source is fetched separately."""
        return await call(service.changed, session_id, since_revision, limit, cursor, budget_tokens)

    @server.tool(structured_output=False)
    async def task_checkpoint(session_id: str, record: dict | None = None) -> list[TextContent]:
        """Read/save task, decisions, changedFiles, checks, issues, nextSteps. Local workspace only; works offline."""
        return await call(service.checkpoint, session_id, record)

    return server
