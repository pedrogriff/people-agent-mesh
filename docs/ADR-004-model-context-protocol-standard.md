# ADR-004: Standardizing Multi-Jurisdiction People Operations Tools on Model Context Protocol (MCP)

## Status
**ACCEPTED** (2025-Q1)

## Context & Problem Statement
Modern enterprise AI agent platforms must interact with a diverse ecosystem of reasoning models (Claude 3.5 Sonnet, GPT-4o, Gemini 1.5 Pro) and client runtime environments (Claude Desktop, Cursor, Antigravity CLI, custom LangChain/LlamaIndex agents, and internal Kubernetes microservices).

Historically, tool definitions were siloed into proprietary JSON function-calling specifications (e.g. OpenAI function schemas, Anthropic tool definitions). This resulted in:
1. **Tool Schema Fragmentation**: Writing redundant wrapper code for each client runtime.
2. **Inconsistent Validation**: Loose input validation leading to silent type coercion or unhandled schema drifts.
3. **Lack of Standardized Resources & Prompts**: No unified way to distribute statutory legal references (CLT Art. 468, US FLSA, Canada Pay Equity) and verified prompt templates alongside the tools.

## Decision
We standardize all deterministic People Operations, compensation modeling, labor compliance verifications, and privacy tokenization mechanisms on the **Model Context Protocol (MCP)** specification (`protocolVersion: 2024-11-05`).

We implement a dual-transport native MCP engine within `people_agent_mesh.mcp`:
1. **Stdio Transport**: A lightweight, zero-dependency JSON-RPC 2.0 loop over stdin/stdout for local integration with Claude Desktop, Cursor, and developer IDEs.
2. **HTTP / Server-Sent Events (SSE) Transport**: A high-concurrency streaming endpoint mounted directly on the existing FastAPI service (`GET /mcp/sse`, `POST /mcp/messages`) for distributed microservice deployments.

### Exposed MCP Primitives
- **Tools**:
  - `validate_clt_compliance`: Enforces Brazilian labor law invariants (unilateral salary reduction prohibition, parental leave compensation protection).
  - `resolve_salary_band`: Resolves benchmark minimum, midpoint, and maximum salaries across São Paulo, New York, and Toronto.
  - `calculate_compa_ratio`: Formally computes compa-ratio and range penetration with green/red circle governance.
  - `evaluate_merit_proposal`: Deterministic merit matrix evaluation and formulaic bonus calculation ($B = \text{Base} \times \text{Target\%} \times \text{IPF} \times \text{CPF}$).
  - `tokenize_pii`: Intercepts and replaces CPFs, SSNs, SINs, compensation figures, and corporate emails with reversible surrogate tokens.
  - `detokenize_pii`: Restores surrogate tokens inside the trusted perimeter.
  - `shred_pii_vault`: Cryptographically destroys token mappings in compliance with LGPD Article 18 / GDPR "Right to be Forgotten".
- **Resources**:
  - `policy://brazil/clt-article-468`: Complete statutory legal invariant specification.
  - `policy://us/flsa-exemption`: Fair Labor Standards Act minimum annual salary requirements ($58,656 USD).
  - `policy://canada/pay-equity`: Canadian Pay Equity Act compliance guidelines.
  - `bands://software-engineering`: 2025 engineering compensation benchmarks.
- **Prompts**:
  - `audit_compensation_proposal`: Multi-jurisdiction audit prompt with systematic tool invocation steps.
  - `pii_scrub_and_evaluate`: Zero-retention privacy preprocessing and synthesis prompt.

## Consequences

### Positive
- **Client Agnosticism**: Any MCP-compliant client (Claude Desktop, Cursor, VS Code Copilot, Antigravity) connects immediately with zero code changes.
- **Zero Overhead**: Implemented with standard library + Pydantic v2 without bloated external dependencies.
- **Deterministic Separation**: Keeps sensitive arithmetic and legal rules in verified Python code while models handle natural language orchestration.
- **Auditability**: Every tool call produces a structured JSON-RPC frame that flows directly into OpenTelemetry distributed traces.

### Negative / Trade-offs
- **Stdio Stream Hygiene**: Stdio transport requires strict discipline—logging must exclusively output to `stderr` to prevent JSON-RPC stream corruption.
