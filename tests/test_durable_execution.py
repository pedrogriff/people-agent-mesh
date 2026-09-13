"""
Unit and Integration Tests for Durable Execution Engine, Event Sourcing,
Crash Recovery, and Saga Rollbacks (ADR-007).
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from people_agent_mesh.core.state import (
    ApprovalStatus,
    EmployeeProfile,
    Jurisdiction,
    MeshState,
    WorkflowStatus,
    WorkflowType,
)
from people_agent_mesh.durable.adapters import (
    LocalDurableAdapter,
    TemporalAdapterSpec,
    TriggerDevAdapterSpec,
)
from people_agent_mesh.durable.engine import (
    DurableWorkflowEngine,
    WorkflowAlreadyTerminalError,
)
from people_agent_mesh.durable.escalation import DurableTimerPolicy, EscalationManager
from people_agent_mesh.durable.events import WorkflowEvent, WorkflowEventType
from people_agent_mesh.durable.saga import SagaCoordinator
from people_agent_mesh.durable.store import (
    IdempotencyDuplicateError,
    InMemoryDurableStore,
    SequenceConflictError,
    SQLiteDurableStore,
)


@pytest.fixture
def sample_employee() -> EmployeeProfile:
    return EmployeeProfile(
        employee_id="EMP-DUR-01",
        name="Elena Rostova",
        email="elena.rostova@enterprise.internal",
        department="Core Infrastructure",
        job_title="Senior Software Engineer",
        level="IC4",
        jurisdiction=Jurisdiction.UNITED_STATES,
        manager_id="MGR-100",
        base_salary=Decimal("170000.00"),
        currency="USD",
        compa_ratio=Decimal("0.94"),
        performance_rating="EXCEEDS",
        tenure_months=20,
    )


@pytest.fixture
def sample_state(sample_employee: EmployeeProfile) -> MeshState:
    return MeshState(
        workflow_id="wf-dur-test-001",
        workflow_type=WorkflowType.FULL_TALENT_DOSSIER,
        jurisdiction=Jurisdiction.UNITED_STATES,
        employee=sample_employee,
        requester_id="REQ-TEST",
        requester_role="PEOPLE_PARTNER",
    )


def test_event_creation_and_integrity_checksum() -> None:
    evt = WorkflowEvent(
        workflow_id="wf-100",
        sequence_number=1,
        event_type=WorkflowEventType.WORKFLOW_STARTED,
        payload={"action": "test_start"},
    )
    assert evt.sequence_number == 1
    assert evt.checksum != ""
    assert evt.verify_integrity() is True


def test_in_memory_durable_store_monotonicity_and_idempotency() -> None:
    store = InMemoryDurableStore()
    wf_id = "wf-seq-test"

    evt1 = WorkflowEvent(
        workflow_id=wf_id,
        sequence_number=1,
        event_type=WorkflowEventType.WORKFLOW_STARTED,
        idempotency_key="idemp-1",
    )
    store.append_event(wf_id, evt1)
    assert store.get_last_sequence(wf_id) == 1

    # Non-monotonic sequence (jumping to 3 instead of 2)
    evt_bad = WorkflowEvent(
        workflow_id=wf_id,
        sequence_number=3,
        event_type=WorkflowEventType.ACTIVITY_COMPLETED,
    )
    with pytest.raises(SequenceConflictError):
        store.append_event(wf_id, evt_bad)

    # Duplicate idempotency key
    evt_dup = WorkflowEvent(
        workflow_id=wf_id,
        sequence_number=2,
        event_type=WorkflowEventType.ACTIVITY_COMPLETED,
        idempotency_key="idemp-1",
    )
    with pytest.raises(IdempotencyDuplicateError):
        store.append_event(wf_id, evt_dup)


def test_sqlite_durable_store_persistence_and_wal(tmp_path: Path, sample_state: MeshState) -> None:
    db_file = tmp_path / "test_durable.db"
    store = SQLiteDurableStore(db_path=db_file)
    wf_id = sample_state.workflow_id

    evt1 = WorkflowEvent(
        workflow_id=wf_id,
        sequence_number=1,
        event_type=WorkflowEventType.WORKFLOW_STARTED,
        payload={"step": "init"},
    )
    store.append_event(wf_id, evt1)
    store.save_snapshot(wf_id, sample_state, 1)

    # Re-open with new store instance
    store2 = SQLiteDurableStore(db_path=db_file)
    events = store2.get_events(wf_id)
    assert len(events) == 1
    assert events[0].event_type == WorkflowEventType.WORKFLOW_STARTED

    loaded_state, last_seq = store2.get_latest_snapshot(wf_id)
    assert loaded_state is not None
    assert loaded_state.employee.name == "Elena Rostova"
    assert last_seq == 1


def test_durable_engine_end_to_end_suspension_and_approval(sample_state: MeshState) -> None:
    store = InMemoryDurableStore()
    engine = DurableWorkflowEngine(store=store)

    # 1. Execute workflow: high performance rating EXCEEDS triggers merit >= 10%, which triggers HITL suspension
    result_state = engine.start_workflow(sample_state)

    assert result_state.status == WorkflowStatus.AWAITING_HUMAN_APPROVAL
    assert result_state.approval_request is not None
    assert result_state.approval_request.status == ApprovalStatus.PENDING

    # Verify event stream
    events = store.get_events(sample_state.workflow_id)
    event_types = [e.event_type for e in events]
    assert WorkflowEventType.WORKFLOW_STARTED in event_types
    assert WorkflowEventType.ACTIVITY_COMPLETED in event_types
    assert WorkflowEventType.STATUTORY_CHECKED in event_types
    assert WorkflowEventType.HUMAN_INTERRUPT_SUSPENDED in event_types
    assert WorkflowEventType.TIMER_SCHEDULED in event_types

    # 2. Signal human approval
    approved_state = engine.signal_workflow(
        workflow_id=sample_state.workflow_id,
        signal_name="HUMAN_DECISION",
        payload={
            "decision": "APPROVED",
            "decided_by": "vp.engineering@enterprise.internal",
            "comments": "Endorsed with full budget approval.",
        },
    )

    assert approved_state.status == WorkflowStatus.COMPLETED
    assert approved_state.approval_request is not None
    assert approved_state.approval_request.status == ApprovalStatus.APPROVED

    final_events = store.get_events(sample_state.workflow_id)
    final_types = [e.event_type for e in final_events]
    assert WorkflowEventType.HUMAN_SIGNAL_RECEIVED in final_types
    assert WorkflowEventType.WORKFLOW_COMPLETED in final_types

    # Signaling an already completed workflow must raise WorkflowAlreadyTerminalError
    with pytest.raises(WorkflowAlreadyTerminalError):
        engine.signal_workflow(
            workflow_id=sample_state.workflow_id,
            signal_name="HUMAN_DECISION",
            payload={"decision": "APPROVED"},
        )


def test_durable_engine_crash_recovery_from_disk(tmp_path: Path, sample_state: MeshState) -> None:
    db_file = tmp_path / "crash_recovery.db"
    store1 = SQLiteDurableStore(db_path=db_file)
    engine1 = DurableWorkflowEngine(store=store1)

    # Start workflow to suspension point
    state1 = engine1.start_workflow(sample_state)
    assert state1.status == WorkflowStatus.AWAITING_HUMAN_APPROVAL
    wf_id = sample_state.workflow_id

    # Simulate sudden crash: destroy engine1 and store1 from memory
    del engine1
    del store1

    # Spin up brand new engine on the same database file
    store2 = SQLiteDurableStore(db_path=db_file)
    engine2 = DurableWorkflowEngine(store=store2)

    # Recover state without executing agents again
    recovered_state = engine2.recover_workflow(wf_id)
    assert recovered_state.status == WorkflowStatus.AWAITING_HUMAN_APPROVAL
    assert recovered_state.employee.employee_id == sample_state.employee.employee_id
    assert recovered_state.comp_proposal is not None

    # Deliver signal to the recovered engine
    final_state = engine2.signal_workflow(
        workflow_id=wf_id,
        signal_name="HUMAN_DECISION",
        payload={
            "decision": "APPROVED",
            "decided_by": "vp.eng@enterprise.internal",
            "comments": "Approved after crash recovery.",
        },
    )
    assert final_state.status == WorkflowStatus.COMPLETED


def test_deterministic_event_replay(sample_state: MeshState) -> None:
    store = InMemoryDurableStore()
    engine = DurableWorkflowEngine(store=store)

    engine.start_workflow(sample_state)
    engine.signal_workflow(
        workflow_id=sample_state.workflow_id,
        signal_name="HUMAN_DECISION",
        payload={
            "decision": "APPROVED",
            "decided_by": "dir.people@enterprise.internal",
            "comments": "Approved.",
        },
    )

    replayed_state, event_count = engine.replay_workflow(sample_state.workflow_id)
    assert event_count >= 6
    assert replayed_state.status == WorkflowStatus.COMPLETED
    assert replayed_state.comp_proposal is not None
    assert replayed_state.approval_request is not None
    assert replayed_state.approval_request.decided_by == "dir.people@enterprise.internal"


def test_saga_compensation_on_rejection(sample_state: MeshState) -> None:
    store = InMemoryDurableStore()
    saga = SagaCoordinator()
    engine = DurableWorkflowEngine(store=store, saga_coordinator=saga)

    # Start workflow into suspension
    engine.start_workflow(sample_state)

    # Deliver REJECTED decision
    rejected_state = engine.signal_workflow(
        workflow_id=sample_state.workflow_id,
        signal_name="HUMAN_DECISION",
        payload={
            "decision": "REJECTED",
            "decided_by": "vp.eng@enterprise.internal",
            "comments": "Budget capacity reached for Q3.",
        },
    )

    assert rejected_state.status == WorkflowStatus.REJECTED
    assert rejected_state.approval_request is not None
    assert rejected_state.approval_request.status == ApprovalStatus.REJECTED

    events = store.get_events(sample_state.workflow_id)
    event_types = [e.event_type for e in events]
    assert WorkflowEventType.SAGA_COMPENSATION_STARTED in event_types
    assert WorkflowEventType.SAGA_COMPENSATION_COMPLETED in event_types
    assert WorkflowEventType.WORKFLOW_REJECTED in event_types


def test_escalation_timer_sla_breach(sample_state: MeshState) -> None:
    store = InMemoryDurableStore()
    policy = DurableTimerPolicy(
        primary_sla_seconds=100.0,
        escalate_to_role="VP_ENGINEERING",
        secondary_sla_seconds=200.0,
        secondary_escalate_to_role="CHIEF_PEOPLE_OFFICER",
    )
    escalation_mgr = EscalationManager(default_policy=policy)
    engine = DurableWorkflowEngine(store=store, escalation_manager=escalation_mgr)

    # Start workflow into suspension
    state = engine.start_workflow(sample_state)
    assert state.approval_request is not None

    # Simulate timer expiration signal with 150s elapsed (exceeds primary 100s)
    escalated_state = engine.signal_workflow(
        workflow_id=sample_state.workflow_id,
        signal_name="TIMER_EXPIRED",
        payload={"elapsed_seconds": 150.0},
    )

    assert escalated_state.approval_request is not None
    assert escalated_state.approval_request.required_role == "VP_ENGINEERING"

    # Simulate secondary breach (250s)
    cpo_state = engine.signal_workflow(
        workflow_id=sample_state.workflow_id,
        signal_name="TIMER_EXPIRED",
        payload={"elapsed_seconds": 250.0},
    )
    assert cpo_state.approval_request is not None
    assert cpo_state.approval_request.required_role == "CHIEF_PEOPLE_OFFICER"


def test_local_durable_adapter_interface(sample_state: MeshState) -> None:
    adapter = LocalDurableAdapter(db_path=":memory:")
    started = adapter.start_workflow(sample_state)
    assert started.status == WorkflowStatus.AWAITING_HUMAN_APPROVAL

    history = adapter.get_workflow_history(sample_state.workflow_id)
    assert len(history) > 0

    replayed, count = adapter.replay_workflow(sample_state.workflow_id)
    assert count == len(history)
    assert replayed.workflow_id == sample_state.workflow_id


def test_temporal_and_triggerdev_specs() -> None:
    assert TemporalAdapterSpec.engine_type == "TEMPORAL_IO_V1"
    assert "Activity Heartbeating" in TemporalAdapterSpec.supported_features
    assert TriggerDevAdapterSpec.engine_type == "TRIGGER_DEV_V3"
    assert "Serverless Micro-VM Execution" in TriggerDevAdapterSpec.supported_features


def test_mcp_durable_tools() -> None:
    import json

    from people_agent_mesh.mcp.server import PeopleMeshMCPServer

    server = PeopleMeshMCPServer()

    # 1. Start durable workflow via MCP
    start_res = server.call_tool(
        "start_durable_workflow",
        {
            "name": "Marcus Vance",
            "level": "IC4",
            "performance_rating": "EXCEEDS",
            "jurisdiction": "UNITED_STATES",
        },
    )
    assert start_res.isError is False
    start_data = json.loads(start_res.content[0]["text"])
    wf_id = start_data["workflow_id"]
    assert start_data["suspended_for_hitl"] is True
    assert start_data["events_logged"] >= 5

    # 2. Inspect history via MCP
    hist_res = server.call_tool("get_durable_workflow_history", {"workflow_id": wf_id})
    assert hist_res.isError is False
    hist_data = json.loads(hist_res.content[0]["text"])
    assert hist_data["total_events"] >= 5

    # 3. Signal workflow via MCP
    sig_res = server.call_tool(
        "signal_durable_workflow",
        {
            "workflow_id": wf_id,
            "decision": "APPROVED",
            "decided_by": "vp.eng@enterprise.internal",
        },
    )
    assert sig_res.isError is False
    sig_data = json.loads(sig_res.content[0]["text"])
    assert sig_data["status"] == "COMPLETED"

    # 4. Replay workflow via MCP
    rep_res = server.call_tool("replay_durable_workflow", {"workflow_id": wf_id})
    assert rep_res.isError is False
    rep_data = json.loads(rep_res.content[0]["text"])
    assert rep_data["parity_verified"] is True
    assert rep_data["reconstructed_status"] == "COMPLETED"
