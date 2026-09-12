"""
JSON-RPC 2.0 and Model Context Protocol (MCP) data specifications.
Adheres strictly to the Anthropic MCP specification (protocolVersion: 2024-11-05).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# Protocol Constants
LATEST_PROTOCOL_VERSION = "2024-11-05"
SUPPORTED_PROTOCOL_VERSIONS = ["2024-11-05", "0.1.0"]

# Standard JSON-RPC 2.0 Error Codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class JSONRPCError(BaseModel):
    code: int
    message: str
    data: Any | None = None


class JSONRPCRequest(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str | None = None
    method: str
    params: dict[str, Any] | None = None


class JSONRPCResponse(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str | None = None
    result: Any | None = None
    error: JSONRPCError | None = None

    def model_dump_clean(self) -> dict[str, Any]:
        """Dumps dictionary omitting None for result/error according to JSON-RPC 2.0 spec."""
        d: dict[str, Any] = {"jsonrpc": self.jsonrpc, "id": self.id}
        if self.error is not None:
            d["error"] = self.error.model_dump(exclude_none=True)
        else:
            d["result"] = self.result
        return d


class ToolDefinition(BaseModel):
    name: str
    description: str
    inputSchema: dict[str, Any]


class ToolCallResult(BaseModel):
    content: list[dict[str, Any]]
    isError: bool = False


class ResourceDefinition(BaseModel):
    uri: str
    name: str
    description: str | None = None
    mimeType: str | None = "text/plain"


class ResourceContent(BaseModel):
    uri: str
    mimeType: str | None = "text/plain"
    text: str | None = None
    blob: str | None = None


class PromptArgument(BaseModel):
    name: str
    description: str | None = None
    required: bool = False


class PromptDefinition(BaseModel):
    name: str
    description: str | None = None
    arguments: list[PromptArgument] = Field(default_factory=list)


class PromptMessage(BaseModel):
    role: str = "user"
    content: dict[str, Any]
