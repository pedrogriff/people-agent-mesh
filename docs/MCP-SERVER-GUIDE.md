# Model Context Protocol (MCP) Server Integration Guide

The `people-agent-mesh` system exposes its core deterministic engines—Brazilian CLT compliance checking, compensation band resolution, compa-ratio calculations, and zero-retention PII tokenization—as a standardized **Model Context Protocol (MCP)** server.

This allows any MCP-compatible agent or client (**Claude Desktop**, **Cursor**, **Antigravity CLI**, **LangChain**, or custom agents) to invoke verified compensation tools and read statutory labor policies.

---

## 1. Quickstart: Claude Desktop Integration

Add `people-agent-mesh` to your Claude Desktop configuration file:

### macOS / Linux
File: `~/.config/Claude/claude_desktop_config.json` (or `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS)

```json
{
  "mcpServers": {
    "people-mesh": {
      "command": "people-mesh",
      "args": ["--mcp"]
    }
  }
}
```

Or via direct Python execution:

```json
{
  "mcpServers": {
    "people-mesh": {
      "command": "python3",
      "args": ["-m", "people_agent_mesh.mcp"]
    }
  }
}
```

Restart Claude Desktop. You will see a hammer icon 🔨 with 7 available tools, 4 resources, and 2 prompts!

---

## 2. Cursor IDE Integration

In Cursor:
1. Open **Settings** $\to$ **Features** $\to$ **MCP Servers**.
2. Click **+ Add New MCP Server**.
3. Fill in:
   - **Name**: `people-mesh`
   - **Type**: `command`
   - **Command**: `people-mesh --mcp`

Or configure `.cursor/mcp.json` directly in your workspace:

```json
{
  "mcpServers": {
    "people-mesh": {
      "command": "people-mesh",
      "args": ["--mcp"]
    }
  }
}
```

---

## 3. Remote / Kubernetes Deployment via HTTP & Server-Sent Events (SSE)

For cloud microservices and distributed multi-agent clusters:

```bash
# Launch FastAPI server with MCP SSE endpoint enabled
people-mesh --mcp-sse --port 8080
```

### Endpoints
- **SSE Stream**: `GET http://localhost:8080/mcp/sse`
- **JSON-RPC Dispatcher**: `POST http://localhost:8080/mcp/messages?session_id=<UUID>`
- **Health & Catalog**: `GET http://localhost:8080/mcp/status`

### Remote Client Configuration
```json
{
  "mcpServers": {
    "people-mesh-remote": {
      "url": "http://mesh.internal:8080/mcp/sse"
    }
  }
}
```

---

## 4. MCP Primitives Catalog

### 🛠️ Tools

| Tool Name | Parameters | Description |
| :--- | :--- | :--- |
| `validate_clt_compliance` | `current_base`, `proposed_base`, `is_on_parental_leave`, `employee_id` | Verifies CLT Art. 468 & CF Art. 7 irreducibility invariants. Returns violations and legal citations. |
| `resolve_salary_band` | `job_family`, `level`, `location_tier` | Resolves min, mid, max, currency, and spread across SP (BRL), NYC (USD), and Toronto (CAD). |
| `calculate_compa_ratio` | `base_salary`, `band_midpoint`, `band_min?`, `band_max?` | Formally calculates compa-ratio, range penetration, and green/red circle zone classification. |
| `evaluate_merit_proposal` | `current_base`, `performance_rating`, `level`, `jurisdiction`, `compa_ratio` | Computes merit percentage, new base, formulaic annual bonus, equity guidelines, and HITL flags. |
| `tokenize_pii` | `text`, `session_id?` | Replaces CPF, SSN, SIN, compensation amounts, and emails with surrogate tokens for Zero-Retention LLM inference. |
| `detokenize_pii` | `tokenized_text`, `session_id?` | Restores surrogate tokens back to original plaintext inside the trusted perimeter. |
| `shred_pii_vault` | `session_id?` | Cryptographically destroys token mapping vault in compliance with LGPD Art. 18 / GDPR "Right to be Forgotten". |

### 📚 Read-Only Resources

| URI | Name | MIME Type | Summary |
| :--- | :--- | :--- | :--- |
| `policy://brazil/clt-article-468` | Brazil CLT Article 468 Labor Invariants | `text/markdown` | Statutory rules prohibiting unilateral adverse contract changes and base salary cuts. |
| `policy://us/flsa-exemption` | US FLSA Exemption Thresholds | `text/markdown` | Fair Labor Standards Act salary threshold ($58,656 USD) and Title VII equity boundaries. |
| `policy://canada/pay-equity` | Canada Pay Equity Act | `text/markdown` | Pay equity guidelines and 30% discretionary review boundaries. |
| `bands://software-engineering` | Global Engineering Salary Bands | `application/json` | Structured JSON benchmark ranges across IC4, IC5, and IC6 levels. |

### 💬 Prompts

| Prompt Name | Arguments | Description |
| :--- | :--- | :--- |
| `audit_compensation_proposal` | `employee_id`, `jurisdiction`, `current_base`, `proposed_base`, `performance_rating` | Formats a structured audit prompt guiding the agent through sequential tool invocation and HITL review. |
| `pii_scrub_and_evaluate` | `raw_text` | Guides the agent to tokenize sensitive text before generating an executive summary. |

---

## 5. Stdio Transport Verification via CLI

You can test the MCP JSON-RPC protocol directly from your terminal:

```bash
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "validate_clt_compliance", "arguments": {"current_base": 300000, "proposed_base": 250000}}}' | people-mesh --mcp
```

Output:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\n  \"passed\": false,\n  \"jurisdiction\": \"BRAZIL\",\n  \"violations\": [\n    \"CLT Article 468 / CF Art. 7 Violation: Unilateral reduction of base salary is strictly prohibited under Brazilian labor law.\"\n  ],\n  \"warnings\": [],\n  \"statutory_citations\": [\n    \"CLT Art. 468 (Prohibition of unilateral adverse alterations)\",\n    \"CF/88 Art. 7, VI (Irreducibility of compensation)\"\n  ]\n}"
      }
    ],
    "isError": true
  }
}
```
