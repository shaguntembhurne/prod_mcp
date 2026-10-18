"""Connection helper for the one approved data.gov.in MCP server."""

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

load_dotenv()


class MCPServiceError(RuntimeError):
    pass


@asynccontextmanager
async def open_mcp_session() -> AsyncIterator[ClientSession]:
    """Open one Streamable HTTP MCP session, initialize it, and close it cleanly."""
    url = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8002/mcp").strip()
    if not url.startswith(("http://", "https://")):
        raise MCPServiceError("MCP_SERVER_URL must be an HTTP(S) URL.")
    try:
        async with streamable_http_client(url) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session
    except MCPServiceError:
        raise
    except Exception as exc:
        raise MCPServiceError(f"Could not connect to the approved data.gov.in MCP server: {exc}") from exc
