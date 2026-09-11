# RFC-001: Nubank Enterprise Agent Standards & Tool Contract Specification

**Author**: Pedro Griff Marcincowski (Staff Software Engineer, AI Agents)  
**Target Audience**: All Engineering Teams building or adopting AI Agents across Nubank  
**Status**: Adopted as Engineering Standard  

---

## 1. Abstract & Motivation

As AI-powered capabilities scale across Nubank, we must transition from bespoke prompt scripts to enterprise agent products. This RFC establishes the **Nubank Agent Architecture Standard**, defining mandatory engineering baselines for:
1. **Agent Declarative Specifications (`AgentSpec`)**
2. **Strict Tool Contracts (`ToolSpec`)**
3. **Resilience & Fault Isolation (Circuit Breakers & Idempotency)**
4. **Continuous Integration Quality Gates (`EvalSpec`)**

---

## 2. Core Architectural Standards

### 2.1 Agent Specification Contract (`AgentSpec`)
Every production agent deployed in the Nubank ecosystem must implement the declarative contract:
- **`Identity & Purpose`**: Unique system name, domain ownership, and versioned semantic prompt.
- **`Scope & Authorization`**: Declared ABAC permission boundary and maximum data classification (`PUBLIC`, `INTERNAL`, `RESTRICTED_SPII`).
- **`Failure Modes & Degraded Behavior`**: Explicit fallback callable when upstream models experience degradation or latency spikes.
- **`Human Escalation Triggers`**: Quantitative risk thresholds (e.g. monetary threshold $\ge \$10,000$, confidence score $< 0.80$) that mandate halting for human approval.

### 2.2 Tool Contract Specification (`ToolSpec`)
Direct unconstrained function calling is deprecated. All agent tools must satisfy:
1. **Strict Type Validation**: Tool arguments must be defined as Pydantic v2 schemas with explicit field constraints (`ge`, `le`, `regex`).
2. **Declared Risk Classification**:
   - `READ_ONLY`: Idempotent, safe for automatic retries.
   - `WRITE_IDEMPOTENT`: Mutating operations requiring client-supplied idempotency keys.
   - `WRITE_MUTATING`: High-stakes mutations requiring human approval gate.
3. **Circuit Breaking**: Every external service integration must wrap calls in a sliding-window circuit breaker with predefined failure thresholds.

### 2.3 Continuous Integration Quality Gates (`EvalSpec`)
No agent code or prompt modification may be merged without passing automated CI evaluations:
- **Invariant Tests**: 100% pass rate on mathematical calculations and regulatory constraints.
- **Faithfulness Score**: $\ge 95\%$ groundedness against retrieved context documents.
- **Zero PII Leakage**: 100% pass rate on automated privacy scrubbers across simulated payloads.
- **Latency Budget**: $p95 \le 500\text{ms}$ for non-blocking nodes.

---

## 3. Review & Operational Checklist
Before shipping an agent to production, teams must complete the cross-functional sign-off:
- [x] InfoSec: Verified Zero-Retention Gateway and PII Tokenizer.
- [x] Legal / Compliance: Verified multi-jurisdiction labor compliance rules.
- [x] FinOps: OpenTelemetry spans instrumented with departmental cost attribution tags.
- [x] People Ops: Verified human escalation routing and Slack approval webhooks.
