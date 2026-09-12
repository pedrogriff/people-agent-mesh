"""
Model Context Protocol (MCP) Server for PeopleAgentMesh.
Standardized JSON-RPC 2.0 tool and resource endpoints for LLM agents,
Claude Desktop, Cursor, and enterprise AI orchestration.
"""

from people_agent_mesh.mcp.protocol import (
    JSONRPCError,
    JSONRPCRequest,
    JSONRPCResponse,
    ToolCallResult,
    ToolDefinition,
)
from people_agent_mesh.mcp.server import PeopleMeshMCPServer
from people_agent_mesh.mcp.stdio import run_stdio_server

__all__ = [
    "JSONRPCError",
    "JSONRPCRequest",
    "JSONRPCResponse",
    "PeopleMeshMCPServer",
    "ToolCallResult",
    "ToolDefinition",
    "run_stdio_server",
]
