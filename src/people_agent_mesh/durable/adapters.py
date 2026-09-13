"""
Durable Execution Adapters for PeopleAgentMesh.
Provides abstract adapter interfaces and production specifications for Local SQLite,
Temporal.io, and Trigger.dev v3 (ADR-007).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from people_agent_mesh.core.state import MeshState
from people_agent_mesh.durable.engine import DurableWorkflowEngine
from people_agent_mesh.durable.events import WorkflowEvent
from people_agent_mesh.durable.store import DurableEventStore, SQLiteDurableStore


class DurableExecutionAdapter(ABC):
    """Abstract interface for pluggable durable execution engines."""

    @abstractmethod
    def start_workflow(self, state: MeshState, idempotency_key: str | None = None) -> MeshState:
        """Starts a durable workflow run."""

    @abstractmethod
    def signal_workflow(
        self, workflow_id: str, signal_name: str, payload: dict[str, Any]
    ) -> MeshState:
        """Sends an asynchronous signal to a suspended or in-progress workflow."""

    @abstractmethod
    def get_workflow_state(self, workflow_id: str) -> MeshState:
        """Retrieves the current state of a workflow."""

    @abstractmethod
    def get_workflow_history(self, workflow_id: str) -> list[WorkflowEvent]:
        """Retrieves the complete audit event stream for a workflow."""

    @abstractmethod
    def replay_workflow(self, workflow_id: str) -> tuple[MeshState, int]:
        """Deterministically replays the event history from source."""


class LocalDurableAdapter(DurableExecutionAdapter):
    """
    Local, zero-dependency Durable Execution Adapter backed by SQLite WAL.
    Ideal for local development, edge microservices, and self-hosted environments.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self.store: DurableEventStore = SQLiteDurableStore(db_path)
        self.engine = DurableWorkflowEngine(store=self.store)

    def start_workflow(self, state: MeshState, idempotency_key: str | None = None) -> MeshState:
        return self.engine.start_workflow(state, idempotency_key=idempotency_key)

    def signal_workflow(
        self, workflow_id: str, signal_name: str, payload: dict[str, Any]
    ) -> MeshState:
        return self.engine.signal_workflow(workflow_id, signal_name, payload)

    def get_workflow_state(self, workflow_id: str) -> MeshState:
        return self.engine.recover_workflow(workflow_id)

    def get_workflow_history(self, workflow_id: str) -> list[WorkflowEvent]:
        return self.store.get_events(workflow_id)

    def replay_workflow(self, workflow_id: str) -> tuple[MeshState, int]:
        return self.engine.replay_workflow(workflow_id)


class TemporalAdapterSpec:
    """
    Reference specification and blueprint for binding PeopleAgentMesh to Temporal.io.

    Example mapping:
        @workflow.defn
        class PeopleMeshTemporalWorkflow:
            def __init__(self) -> None:
                self._state: MeshState | None = None
                self._decision_received = asyncio.Event()

            @workflow.run
            async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
                # 1. Activities executed with automatic retries and durable timers
                comp = await workflow.execute_activity(
                    execute_compensation_activity,
                    input_data,
                    start_to_close_timeout=timedelta(minutes=2),
                )
                if comp.requires_hitl:
                    await self._decision_received.wait()
                return self._state.to_snapshot()

            @workflow.signal
            async def human_decision_signal(self, payload: dict[str, Any]) -> None:
                self._decision_received.set()
    """

    engine_type: str = "TEMPORAL_IO_V1"
    supported_features: list[str] = [
        "Activity Heartbeating",
        "Deterministic Event Replay",
        "Cross-Worker Migration",
        "Durable Timers (up to years)",
        "Search Attributes",
    ]


class TriggerDevAdapterSpec:
    """
    Reference specification and blueprint for binding PeopleAgentMesh to Trigger.dev v3.

    Example mapping:
        export const peopleMeshTask = task({
            id: "people-agent-mesh",
            run: async (payload, { ctx }) => {
                const comp = await step.run("calc-compensation", async () => { ... });
                if (comp.risk_score >= 0.40) {
                    const decision = await wait.forRequest({
                        id: `approval-${ctx.run.id}`,
                        timeout: "48h"
                    });
                }
            }
        });
    """

    engine_type: str = "TRIGGER_DEV_V3"
    supported_features: list[str] = [
        "Serverless Micro-VM Execution",
        "wait.forRequest() Human-in-the-Loop",
        "Real-Time Run Streams",
        "Automatic OpenTelemetry Trace Export",
    ]
