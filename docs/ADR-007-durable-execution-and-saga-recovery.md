# ADR-007: Durable Execution Engine, Event Sourcing & Backward Saga Rollbacks

## Status
**Accepted & Implemented** (v1.2.0)

## Context & Problem Statement
In enterprise People Operations, compensation calibrations, promotional reviews, and statutory exceptions do not execute within synchronous 500ms HTTP transaction boundaries. They represent **asynchronous, long-running human-in-the-loop (HITL) workflows** that often remain pending for hours, days, or weeks awaiting executive sign-off from People Partners, Total Rewards Directors, or VPs of Engineering.

Historically, LLM agent frameworks maintain in-flight execution state in transient process memory (e.g., in-memory dictionaries or volatile Celery worker caches). This architectural shortcut introduces three critical enterprise vulnerabilities:
1. **Container Recycling & Crash Loss**: In Kubernetes or serverless environments, pod evictions, node updates, or worker restarts wipe out in-memory state, stranding workflows in limbo and losing audit trails.
2. **Double-Spend & Non-Idempotent Retries**: Naive re-execution of failed workflows re-invokes expensive LLM inference agents and non-idempotent tool mutations (such as double-adjusting salary bands or re-triggering webhook dispatches).
3. **Absence of Backwards Compensation (Saga Pattern)**: When an executive rejects a proposed promotion or statutory violation is uncovered during human review, provisional resource reservations (such as merit budget holds or HRIS headcount reservations) remain orphaned without structured rollback transactions.

## Decision Drivers
* **Zero Data Loss**: In-flight workflows must withstand process termination, pod kills, and network partitions with 100% state recovery.
* **Deterministic Event Sourcing & Replay**: Workflow state must be derivable from an append-only stream of immutable events with zero divergence between live execution and replayed history.
* **Backward Saga Compensation**: Human rejections or cancellations must execute compensating transactions in reverse chronological order (LIFO).
* **Zero External Infrastructure Dependency**: Provide a fully operational, embedded, zero-dependency engine powered by SQLite Write-Ahead Logging (WAL) while providing native adapter specifications for cloud-native orchestration engines (**Temporal.io** and **Trigger.dev v3**).
* **Durable Timers & Escalation SLAs**: Automatic tracking of review deadlines with multi-tier escalation ladders (e.g., 24h People Partner -> 48h VP Engineering -> Chief People Officer).

---

## Architectural Specification

```
                          ┌────────────────────────────────────────────────────────┐
                          │         Durable Execution Engine (ADR-007)             │
                          └──────────────────────────┬─────────────────────────────┘
                                                     │
       1. Start Workflow                             │ 2. Append Events (WAL)
  ┌─────────────────────────┐                        ▼                        ┌─────────────────────────┐
  │  Client / REST / MCP    │────────────► ┌───────────────────┐ ───────────► │   SQLite Durable Store  │
  └─────────────────────────┘              │  Workflow Engine  │              │    (WAL Mode, ACID)     │
                                           └─────────┬─────────┘              └─────────────────────────┘
                                                     │                                     │
                                 3. HITL Interrupt   │                                     │
                                    (Risk >= 0.40)   ▼                                     │
                                           ┌───────────────────┐                           │
                                           │ Suspended State   │                           │
                                           │ (Awaiting Signal) │                           │
                                           └─────────┬─────────┘                           │
                                                     │                                     │
                             4. Crash / Kill Pod     │ 💥                                  │
                                ─────────────────────┘                                     │
                                                     │ 5. Cold Restart                     │
                                                     ▼                                     ▼
                                           ┌───────────────────┐              ┌─────────────────────────┐
                                           │ Replay & Reducer  │ ◄─────────── │ Append-Only Event Stream│
                                           │ f(State, Event)   │              │ Seq #1..N + Checksums   │
                                           └─────────┬─────────┘              └─────────────────────────┘
                                                     │
                                 6. Asynchronous     │
                                    Signal Received  ▼
                                           ┌───────────────────┐
                                           │ Completed State / │
                                           │ Saga Compensation │
                                           └───────────────────┘
```

### 1. Immutable Event Schema (`WorkflowEvent`)
Every state transition emits an immutable domain event conforming to strict monotonic sequence numbering:

| Field | Type | Description |
| :--- | :--- | :--- |
| `event_id` | `str` | Globally unique identifier (`evt-<uuid12>`) |
| `workflow_id` | `str` | Correlated workflow identifier (`wf-dur-<hex>`) |
| `sequence_number` | `int` | Strictly monotonic integer ($1, 2, 3 \dots$) enforcing sequence integrity |
| `event_type` | `WorkflowEventType` | Domain event type (e.g., `WORKFLOW_STARTED`, `HUMAN_INTERRUPT_SUSPENDED`) |
| `timestamp` | `datetime` | UTC timestamp of event generation |
| `payload` | `dict[str, Any]` | JSON-safe serialized domain payload |
| `idempotency_key`| `str \| None` | Client-provided key preventing duplicate execution |
| `checksum` | `str` | SHA-256 digest of canonical event contents verifying zero tampering |

### 2. Supported Domain Event Stream (`WorkflowEventType`)
* `WORKFLOW_STARTED`: Workflow initialized and inputs validated.
* `ACTIVITY_SCHEDULED`: Specialist sub-agent execution queued (`CompensationAgent`, `PromotionAgent`).
* `ACTIVITY_COMPLETED`: Sub-agent successfully executed with proposal output delta.
* `STATUTORY_CHECKED`: Statutory compliance evaluation finalized (CLT Art. 468, FLSA, PIPEDA).
* `COMMITTEE_DELIBERATED`: Calibration Committee dialectic debate completed.
* `HUMAN_INTERRUPT_SUSPENDED`: Risk score $\ge 0.40$; workflow checkpointed and halted for sign-off.
* `HUMAN_SIGNAL_RECEIVED`: Asynchronous external decision delivered (`APPROVED`, `REJECTED`, `REVISION_REQUESTED`).
* `TIMER_SCHEDULED`: Durable timer registered with review SLA deadline.
* `TIMER_FIRED`: Review SLA expired; escalation ladder triggered.
* `SAGA_COMPENSATION_STARTED`: Backwards compensation sequence initiated following human rejection.
* `SAGA_COMPENSATION_COMPLETED`: All provisional reservations reversed.
* `WORKFLOW_COMPLETED`: Terminal success state reached; executive dossier sealed.
* `WORKFLOW_REJECTED`: Terminal rejection state reached following saga rollback.

---

### 3. Pure Deterministic State Reducer
Crash recovery and historical audits operate via a pure reducer function:
$$\text{State}_{t+1} = \text{Reduce}(\text{State}_t, \text{Event}_{t+1})$$

Because all activity outputs and human decisions are committed to the event stream, replaying sequence $1 \to N$:
1. Never makes external HTTP or LLM API calls.
2. Never triggers redundant tool side-effects.
3. Produces an exact, bit-for-bit identical `MeshState` snapshot in $< 10\text{ms}$.

---

### 4. Backward Saga Compensation Coordinator (`SagaCoordinator`)
When forward activities execute, they register compensating rollback handlers:
* **`MeritBudgetHold`** $\to$ `release_headroom`: Unlocks held merit budget in the departmental compensation pool.
* **`HRISPromotionLock`** $\to$ `revoke_provisional_level`: Cancels pending promotion band reservations in the HRIS queue.
* **`CompaRatioAdjustment`** $\to$ `restore_prior_compa`: Reverts internal benchmarking indices.

Upon receiving a `REJECTED` signal, the `SagaCoordinator` executes registered compensations in **reverse order (LIFO)**, records `SAGA_COMPENSATION_COMPLETED`, and transitions the workflow to `REJECTED`.

---

### 5. Pluggable Cloud Adapters (`DurableExecutionAdapter`)
PeopleAgentMesh decouples workflow logic from physical task runtimes:
* **`LocalDurableAdapter`**: Production-ready, zero-dependency embedded runtime using SQLite WAL.
* **`TemporalAdapterSpec`**: Blueprint mapping mesh workflows to Temporal Workflows (`@workflow.defn`), Signals (`@workflow.signal`), Queries (`@workflow.query`), and Activities (`workflow.execute_activity`).
* **`TriggerDevAdapterSpec`**: Blueprint mapping mesh workflows to Trigger.dev v3 micro-VM tasks and `wait.forRequest()` human approval primitives.

---

## Verification & Golden Gates

| Verification Gate | Specification | Status |
| :--- | :--- | :--- |
| **Monotonic Sequence Enforcement** | Non-monotonic or conflicting sequences rejected with `SequenceConflictError` | ✅ PASSED |
| **Idempotency Guarantee** | Duplicate idempotency keys within a workflow rejected with `IdempotencyDuplicateError` | ✅ PASSED |
| **Crash Recovery Parity** | In-memory engine purged; state restored from SQLite WAL with 0.0% data loss | ✅ PASSED |
| **Deterministic Replay** | Replay of historical event stream yields identical `MeshState` | ✅ PASSED |
| **Saga Compensation Rollback** | Rejection cleanly executes backwards compensations in LIFO order | ✅ PASSED |
| **SLA Escalation Timer** | Review timeout escalates role hierarchy (`PEOPLE_PARTNER` $\to$ `VP_ENG` $\to$ `CPO`) | ✅ PASSED |
| **REST API & MCP Integration** | REST endpoints (`/api/v1/durable/*`) and MCP tools (`start_durable_workflow`, etc.) verified | ✅ PASSED |

