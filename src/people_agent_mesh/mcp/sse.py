"""
Server-Sent Events (SSE) Transport for Model Context Protocol (MCP).
Provides HTTP/SSE streaming endpoints compatible with MCP specification.
Enables distributed microservice and containerized deployment (e.g. Kubernetes).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse

from people_agent_mesh.mcp.server import PeopleMeshMCPServer

router = APIRouter(prefix="/mcp", tags=["Model Context Protocol"])

# Session registry for active SSE event queues: session_id -> asyncio.Queue[str]
active_sessions: dict[str, asyncio.Queue[str]] = {}

# Singleton server instance for the router
mcp_server = PeopleMeshMCPServer()


@router.get("/sse")
async def mcp_sse_endpoint(request: Request) -> StreamingResponse:
    """
    Establishes an SSE stream for MCP protocol communication.
    Emits an initial 'endpoint' event with the message dispatch URI.
    """
    session_id = str(uuid.uuid4())
    queue: asyncio.Queue[str] = asyncio.Queue()
    active_sessions[session_id] = queue

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            # Step 1: Emit initial endpoint URI as required by MCP SSE specification
            endpoint_uri = f"/mcp/messages?session_id={session_id}"
            yield f"event: endpoint\ndata: {endpoint_uri}\n\n"

            # Step 2: Stream queued JSON-RPC messages to the client
            while True:
                if await request.is_disconnected():
                    break
                try:
                    # Timeout periodically to check client connection
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"event: message\ndata: {msg}\n\n"
                except TimeoutError:
                    # Keep-alive ping comment
                    yield ": ping\n\n"
        finally:
            active_sessions.pop(session_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/messages")
async def mcp_messages_endpoint(
    request: Request,
    session_id: str | None = Query(default=None, alias="session_id"),
    session_id_camel: str | None = Query(default=None, alias="sessionId"),
) -> Response:
    """
    Receives JSON-RPC 2.0 requests from MCP clients.
    If an active SSE session exists, emits the response via the SSE stream and returns 202 Accepted.
    Otherwise, returns the JSON-RPC response directly with HTTP 200.
    """
    active_id = session_id or session_id_camel

    try:
        body: dict[str, Any] = await request.json()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON payload: {e}",
        ) from e

    response_data = mcp_server.handle_message(body)

    # If it's a notification, no response is generated
    if response_data is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    resp_json = json.dumps(response_data)

    # Route via active SSE queue if connected
    if active_id and active_id in active_sessions:
        await active_sessions[active_id].put(resp_json)
        return JSONResponse(
            content={"status": "accepted", "session_id": active_id},
            status_code=status.HTTP_202_ACCEPTED,
        )

    # Direct synchronous return for non-streaming or test callers
    return JSONResponse(content=response_data, status_code=status.HTTP_200_OK)


@router.get("/status")
async def mcp_server_status() -> dict[str, Any]:
    """Provides real-time health and metadata for the MCP server."""
    tools = mcp_server.list_tools()
    resources = mcp_server.list_resources()
    prompts = mcp_server.list_prompts()
    return {
        "status": "healthy",
        "server": mcp_server.SERVER_NAME,
        "version": mcp_server.SERVER_VERSION,
        "active_sse_sessions": len(active_sessions),
        "tools_count": len(tools),
        "resources_count": len(resources),
        "prompts_count": len(prompts),
        "tools": [t.name for t in tools],
        "resources": [r.uri for r in resources],
        "prompts": [p.name for p in prompts],
    }
