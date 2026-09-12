"""
Comprehensive Test Suite for Model Context Protocol (MCP) Server.
Tests JSON-RPC 2.0 handshake, tool schemas & execution, resources, prompts,
stdio transport loop, and FastAPI SSE / HTTP endpoints.
"""

from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient

from people_agent_mesh.mcp.protocol import (
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
)
from people_agent_mesh.mcp.server import PeopleMeshMCPServer
from people_agent_mesh.mcp.stdio import run_stdio_server
from people_agent_mesh.server import app


@pytest.fixture
def mcp_server() -> PeopleMeshMCPServer:
    return PeopleMeshMCPServer()


def test_mcp_handshake_and_ping(mcp_server: PeopleMeshMCPServer) -> None:
    # 1. Initialize
    init_msg = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"},
        },
    }
    resp = mcp_server.handle_message(init_msg)
    assert resp is not None
    assert resp["id"] == 1
    assert resp["result"]["protocolVersion"] == "2024-11-05"
    assert "tools" in resp["result"]["capabilities"]
    assert "resources" in resp["result"]["capabilities"]
    assert "prompts" in resp["result"]["capabilities"]
    assert resp["result"]["serverInfo"]["name"] == "people-agent-mesh-mcp"

    # 2. Notification (no response expected)
    notif_msg = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    assert mcp_server.handle_message(notif_msg) is None

    # 3. Ping
    ping_msg = {"jsonrpc": "2.0", "id": 2, "method": "ping"}
    ping_resp = mcp_server.handle_message(ping_msg)
    assert ping_resp is not None
    assert ping_resp["id"] == 2
    assert ping_resp["result"] == {}


def test_mcp_tools_list_and_schema(mcp_server: PeopleMeshMCPServer) -> None:
    list_msg = {"jsonrpc": "2.0", "id": 10, "method": "tools/list"}
    resp = mcp_server.handle_message(list_msg)
    assert resp is not None
    tools = resp["result"]["tools"]
    tool_names = {t["name"] for t in tools}

    expected_tools = {
        "validate_clt_compliance",
        "resolve_salary_band",
        "calculate_compa_ratio",
        "evaluate_merit_proposal",
        "tokenize_pii",
        "detokenize_pii",
        "shred_pii_vault",
    }
    assert expected_tools.issubset(tool_names)

    # Verify input schema structure
    for t in tools:
        assert "name" in t
        assert "description" in t
        assert "inputSchema" in t
        assert t["inputSchema"]["type"] == "object"


def test_mcp_tool_validate_clt_compliance(mcp_server: PeopleMeshMCPServer) -> None:
    # A. Compliant Merit Increase
    ok_call = {
        "jsonrpc": "2.0",
        "id": 20,
        "method": "tools/call",
        "params": {
            "name": "validate_clt_compliance",
            "arguments": {
                "current_base": 240000.0,
                "proposed_base": 260000.0,
                "is_on_parental_leave": False,
            },
        },
    }
    ok_resp = mcp_server.handle_message(ok_call)
    assert ok_resp is not None
    assert ok_resp["result"]["isError"] is False
    payload = json.loads(ok_resp["result"]["content"][0]["text"])
    assert payload["passed"] is True
    assert len(payload["violations"]) == 0

    # B. CLT Article 468 Salary Reduction Violation
    viol_call = {
        "jsonrpc": "2.0",
        "id": 21,
        "method": "tools/call",
        "params": {
            "name": "validate_clt_compliance",
            "arguments": {
                "current_base": 300000.0,
                "proposed_base": 250000.0,
                "is_on_parental_leave": False,
            },
        },
    }
    viol_resp = mcp_server.handle_message(viol_call)
    assert viol_resp is not None
    assert viol_resp["result"]["isError"] is True
    viol_payload = json.loads(viol_resp["result"]["content"][0]["text"])
    assert viol_payload["passed"] is False
    assert any("CLT Article 468" in v for v in viol_payload["violations"])


def test_mcp_tool_resolve_salary_band_and_compa(mcp_server: PeopleMeshMCPServer) -> None:
    # 1. Resolve Band
    band_call = {
        "jsonrpc": "2.0",
        "id": 30,
        "method": "tools/call",
        "params": {
            "name": "resolve_salary_band",
            "arguments": {
                "job_family": "SOFTWARE_ENGINEERING",
                "level": "IC5",
                "location_tier": "BR_SP",
            },
        },
    }
    band_resp = mcp_server.handle_message(band_call)
    assert band_resp is not None
    assert band_resp["result"]["isError"] is False
    band_data = json.loads(band_resp["result"]["content"][0]["text"])
    assert band_data["currency"] == "BRL"
    assert band_data["band_mid"] == 300000.0

    # 2. Calculate Compa-Ratio (Within Target Band)
    compa_call = {
        "jsonrpc": "2.0",
        "id": 31,
        "method": "tools/call",
        "params": {
            "name": "calculate_compa_ratio",
            "arguments": {
                "base_salary": 285000.0,
                "band_midpoint": 300000.0,
                "band_min": 240000.0,
                "band_max": 360000.0,
            },
        },
    }
    compa_resp = mcp_server.handle_message(compa_call)
    assert compa_resp is not None
    assert compa_resp["result"]["isError"] is False
    compa_data = json.loads(compa_resp["result"]["content"][0]["text"])
    assert compa_data["compa_ratio"] == 0.95
    assert compa_data["classification"] == "WITHIN_TARGET_BAND"

    # 3. Compa-Ratio (Green Circle Low)
    low_call = {
        "jsonrpc": "2.0",
        "id": 32,
        "method": "tools/call",
        "params": {
            "name": "calculate_compa_ratio",
            "arguments": {
                "base_salary": 210000.0,
                "band_midpoint": 300000.0,
            },
        },
    }
    low_resp = mcp_server.handle_message(low_call)
    assert low_resp is not None
    low_data = json.loads(low_resp["result"]["content"][0]["text"])
    assert low_data["classification"] == "GREEN_CIRCLE_LOW"


def test_mcp_tool_evaluate_merit_proposal(mcp_server: PeopleMeshMCPServer) -> None:
    merit_call = {
        "jsonrpc": "2.0",
        "id": 40,
        "method": "tools/call",
        "params": {
            "name": "evaluate_merit_proposal",
            "arguments": {
                "current_base": 250000.0,
                "performance_rating": "EXCEEDS",
                "level": "IC5",
                "jurisdiction": "BRAZIL",
                "compa_ratio": 0.83,
            },
        },
    }
    resp = mcp_server.handle_message(merit_call)
    assert resp is not None
    assert resp["result"]["isError"] is False
    data = json.loads(resp["result"]["content"][0]["text"])
    assert data["proposed_base"] > 250000.0
    assert data["calculated_bonus"] > 0
    assert data["equity_grant_shares"] == 500


def test_mcp_privacy_tokenization_and_vault_lifecycle(mcp_server: PeopleMeshMCPServer) -> None:
    session_id = "tenant-test-session-101"
    raw_text = "Review for employee CPF 123.456.789-00 with salary R$ 250.000,00 and contact test@enterprise.internal"

    # 1. Tokenize
    tok_call = {
        "jsonrpc": "2.0",
        "id": 50,
        "method": "tools/call",
        "params": {
            "name": "tokenize_pii",
            "arguments": {"text": raw_text, "session_id": session_id},
        },
    }
    tok_resp = mcp_server.handle_message(tok_call)
    assert tok_resp is not None
    assert tok_resp["result"]["isError"] is False
    tok_data = json.loads(tok_resp["result"]["content"][0]["text"])
    tokenized_text = tok_data["tokenized_text"]
    assert "123.456.789-00" not in tokenized_text
    assert "[TOKEN_CPF_" in tokenized_text
    assert "[TOKEN_COMP_" in tokenized_text

    # 2. Detokenize
    detok_call = {
        "jsonrpc": "2.0",
        "id": 51,
        "method": "tools/call",
        "params": {
            "name": "detokenize_pii",
            "arguments": {"tokenized_text": tokenized_text, "session_id": session_id},
        },
    }
    detok_resp = mcp_server.handle_message(detok_call)
    assert detok_resp is not None
    detok_data = json.loads(detok_resp["result"]["content"][0]["text"])
    assert "123.456.789-00" in detok_data["detokenized_text"]

    # 3. Cryptographic Vault Shredding (LGPD Art. 18)
    shred_call = {
        "jsonrpc": "2.0",
        "id": 52,
        "method": "tools/call",
        "params": {
            "name": "shred_pii_vault",
            "arguments": {"session_id": session_id},
        },
    }
    shred_resp = mcp_server.handle_message(shred_call)
    assert shred_resp is not None
    shred_data = json.loads(shred_resp["result"]["content"][0]["text"])
    assert shred_data["status"] == "CRYPTOGRAPHICALLY_DESTROYED"
    assert shred_data["shredded_tokens_count"] >= 2


def test_mcp_resources_and_prompts(mcp_server: PeopleMeshMCPServer) -> None:
    # 1. Resources List & Read
    res_list = mcp_server.handle_message({"jsonrpc": "2.0", "id": 60, "method": "resources/list"})
    assert res_list is not None
    uris = [r["uri"] for r in res_list["result"]["resources"]]
    assert "policy://brazil/clt-article-468" in uris
    assert "bands://software-engineering" in uris

    res_read = mcp_server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 61,
            "method": "resources/read",
            "params": {"uri": "policy://brazil/clt-article-468"},
        }
    )
    assert res_read is not None
    assert "CLT" in res_read["result"]["contents"][0]["text"]

    # 2. Prompts List & Get
    p_list = mcp_server.handle_message({"jsonrpc": "2.0", "id": 62, "method": "prompts/list"})
    assert p_list is not None
    prompt_names = [p["name"] for p in p_list["result"]["prompts"]]
    assert "audit_compensation_proposal" in prompt_names

    p_get = mcp_server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 63,
            "method": "prompts/get",
            "params": {
                "name": "audit_compensation_proposal",
                "arguments": {
                    "employee_id": "EMP-BR-8821",
                    "jurisdiction": "BRAZIL",
                    "current_base": "240000",
                    "proposed_base": "260000",
                    "performance_rating": "EXCEEDS",
                },
            },
        }
    )
    assert p_get is not None
    prompt_content = p_get["result"]["messages"][0]["content"]["text"]
    assert "EMP-BR-8821" in prompt_content
    assert "validate_clt_compliance" in prompt_content


def test_mcp_error_handling(mcp_server: PeopleMeshMCPServer) -> None:
    # Method not found
    err1 = mcp_server.handle_message({"jsonrpc": "2.0", "id": 70, "method": "non_existent_method"})
    assert err1 is not None
    assert err1["error"]["code"] == METHOD_NOT_FOUND

    # Missing tool name
    err2 = mcp_server.handle_message(
        {"jsonrpc": "2.0", "id": 71, "method": "tools/call", "params": {}}
    )
    assert err2 is not None
    assert err2["error"]["code"] == INVALID_PARAMS

    # Missing resource URI
    err3 = mcp_server.handle_message(
        {"jsonrpc": "2.0", "id": 72, "method": "resources/read", "params": {}}
    )
    assert err3 is not None
    assert err3["error"]["code"] == INVALID_PARAMS


def test_mcp_stdio_runner() -> None:
    # Mock stdin with newline-delimited requests
    requests = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}),
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "calculate_compa_ratio",
                    "arguments": {"base_salary": 200000, "band_midpoint": 200000},
                },
            }
        ),
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
    ]
    stdin = io.StringIO("\n".join(requests) + "\n")
    stdout = io.StringIO()
    stderr = io.StringIO()

    run_stdio_server(stdin=stdin, stdout=stdout, stderr=stderr)

    lines = [line.strip() for line in stdout.getvalue().splitlines() if line.strip()]
    assert len(lines) == 2  # 2 responses (notification emits none)

    resp1 = json.loads(lines[0])
    assert resp1["id"] == 1
    assert resp1["result"] == {}

    resp2 = json.loads(lines[1])
    assert resp2["id"] == 2
    compa_out = json.loads(resp2["result"]["content"][0]["text"])
    assert compa_out["compa_ratio"] == 1.0


def test_fastapi_mcp_http_and_sse() -> None:
    client = TestClient(app)

    # 1. MCP Health / Status Endpoint
    status_res = client.get("/mcp/status")
    assert status_res.status_code == 200
    meta = status_res.json()
    assert meta["status"] == "healthy"
    assert meta["tools_count"] >= 7

    # 2. Synchronous Direct JSON-RPC over POST /mcp/messages
    sync_res = client.post(
        "/mcp/messages",
        json={"jsonrpc": "2.0", "id": 100, "method": "tools/list"},
    )
    assert sync_res.status_code == 200
    sync_body = sync_res.json()
    assert sync_body["id"] == 100
    assert "tools" in sync_body["result"]
