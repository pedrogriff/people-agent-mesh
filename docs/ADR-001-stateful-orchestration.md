# ADR-001: Stateful Graph Orchestration vs. Autonomous ReAct Loops

**Status**: Accepted  
**Date**: September 2026  
**Author**: Pedro Griff Marcincowski (Staff Software Engineer, AI Agents)  
**Stakeholders**: Platform Engineering, People Operations, Information Security, Legal & Compliance  

---

## 1. Context & Problem Statement

In enterprise People Operations (performance reviews, compensation calibration, promotion cycles), decisions have direct financial and legal repercussions across multiple international jurisdictions (Brazil CLT/LGPD, US FLSA, Canada PIPEDA). 

Prototypical agent architectures frequently rely on unconstrained autonomous ReAct loops (Reasoning + Acting) where an LLM repeatedly decides which tool to call next until it self-determines completion. In production, this pattern introduces critical risks:
- **Infinite Looping & Non-Deterministic Latency**: ReAct agents can get caught in reasoning loops when encountering ambiguous data.
- **Lack of Durable Execution**: Real-world HR approvals require human sign-off that may take hours or days. ReAct loops cannot be paused and serialized cleanly without keeping expensive compute or stateful websockets alive.
- **Inability to Enforce Hard Security Boundaries**: Autonomous agents can inadvertently bypass required regulatory checks if the planner chooses not to invoke a compliance tool.

---

## 2. Decision Drivers

- **Deterministic Compliance**: Regulatory checks (CLT Art. 468, FLSA salary baselines) must be guaranteed to execute on every single evaluation without relying on probabilistic LLM planner compliance.
- **Asynchronous Human-in-the-Loop (HITL)**: Ability to persist the entire execution state to storage, emit Slack/webhook notifications, and resume execution days later when executive authorization is signed.
- **Auditability & Reproducibility**: Complete tamper-evident event log of every intermediate calculation, tokenization event, and sub-agent handoff.
- **Cost & Latency Controls**: Predictable upper bounds on tool calls and token consumption.

---

## 3. Considered Options

1. **Option A: Unconstrained Autonomous ReAct Loop (e.g. LangChain / CrewAI)**
   - *Pros*: Quick initial velocity, flexible for exploratory tasks.
   - *Cons*: High hallucination surface, uncontrollable token cost, non-deterministic state, inability to guarantee pause/resume across human review cycles.
2. **Option B: Deterministic Hardcoded Microservice Scripts**
   - *Pros*: Completely deterministic, zero hallucination.
   - *Cons*: Incapable of synthesizing unstructured qualitative signals (Slack praise, peer feedback, 1-on-1 notes) or dynamically adjusting across job families.
3. **Option C: Stateful Multi-Agent Supervisor Graph with Checkpointing (Chosen)**
   - *Pros*: Combines deterministic state machines and compliance verifiers with specialist AI agents for qualitative synthesis; provides native pause/resume serialization.
   - *Cons*: Requires formal schema definition and state transition modeling.

---

## 4. Decision Outcome

**Chosen Option: Option C (Stateful Multi-Agent Supervisor Graph)**.

We architected `PeopleAgentMesh` around an immutable `MeshState` snapshot pattern:
- **Supervisor-Specialist Routing**: A lightweight supervisor agent decomposes the request into parallel specialist tasks (`CompensationAgent`, `PromotionAgent`).
- **Pre- & Post-Flight Deterministic Gates**: Regulatory compliance checks are executed deterministically before and after agent tasks.
- **Native Checkpoint Serialization**: If an evaluation triggers executive risk criteria (e.g., merit increase $\ge 10\%$, out-of-band promotion), the engine records an `ApprovalRequest`, halts with status `AWAITING_HUMAN_APPROVAL`, and serializes the state to storage. Execution resumes deterministically upon receiving signed webhook verification.

---

## 5. Consequences & Trade-offs

- **Positive**:
  - 100% compliance guarantee: zero risk of LLM skipping labor law checks.
  - Complete crash resilience: long-running approvals can survive worker restarts without state loss.
  - Zero token waste during human wait times.
- **Negative / Mitigations**:
  - Requires upfront engineering effort to maintain typed Pydantic state contracts. Mitigated by standardized `AgentSpec` templates.
