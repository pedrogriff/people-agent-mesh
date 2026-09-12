"""
Stdio Transport Runner for Model Context Protocol (MCP).
Enables local process integration with Claude Desktop, Cursor, and IDE coding agents.
Writes strictly valid JSON-RPC 2.0 frames to stdout; all logging directed to stderr.
"""

from __future__ import annotations

import json
import sys
from typing import TextIO

from people_agent_mesh.mcp.server import PeopleMeshMCPServer


def run_stdio_server(
    server: PeopleMeshMCPServer | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> None:
    """
    Runs the MCP JSON-RPC 2.0 event loop over standard input/output streams.
    """
    server = server or PeopleMeshMCPServer()
    inp_stream = stdin or sys.stdin
    out_stream = stdout or sys.stdout
    err_stream = stderr or sys.stderr

    err_stream.write(f"[{server.SERVER_NAME}] Initialized stdio transport (PID {sys.platform}).\n")
    err_stream.flush()

    try:
        for line in inp_stream:
            line_str = line.strip()
            if not line_str:
                continue

            try:
                msg = json.loads(line_str)
            except json.JSONDecodeError as jde:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {jde}"},
                }
                out_stream.write(json.dumps(err_resp) + "\n")
                out_stream.flush()
                continue

            try:
                resp = server.handle_message(msg)
                if resp is not None:
                    out_stream.write(json.dumps(resp) + "\n")
                    out_stream.flush()
            except Exception as ex:
                err_stream.write(f"[{server.SERVER_NAME}] Unhandled server exception: {ex}\n")
                err_stream.flush()
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": msg.get("id") if isinstance(msg, dict) else None,
                    "error": {"code": -32603, "message": f"Internal server error: {ex}"},
                }
                out_stream.write(json.dumps(err_resp) + "\n")
                out_stream.flush()

    except (KeyboardInterrupt, EOFError):
        err_stream.write(f"[{server.SERVER_NAME}] Stdio transport terminated gracefully.\n")
        err_stream.flush()


def main() -> None:
    run_stdio_server()


if __name__ == "__main__":
    main()
