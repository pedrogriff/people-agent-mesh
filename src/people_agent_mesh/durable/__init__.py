"""
Durable Execution Package for PeopleAgentMesh (ADR-007).
"""

from people_agent_mesh.durable.adapters import (
    DurableExecutionAdapter,
    LocalDurableAdapter,
    TemporalAdapterSpec,
    TriggerDevAdapterSpec,
)
from people_agent_mesh.durable.engine import (
    DurableWorkflowEngine,
    WorkflowAlreadyTerminalError,
    WorkflowNotFoundError,
)
from people_agent_mesh.durable.escalation import (
    DurableTimerPolicy,
    EscalationManager,
)
from people_agent_mesh.durable.events import (
    WorkflowEvent,
    WorkflowEventType,
)
from people_agent_mesh.durable.saga import (
    SagaCompensationEntry,
    SagaCoordinator,
    SagaExecutionReport,
)
from people_agent_mesh.durable.store import (
    DurableEventStore,
    IdempotencyDuplicateError,
    InMemoryDurableStore,
    SequenceConflictError,
    SQLiteDurableStore,
)

__all__ = [
    "DurableEventStore",
    "DurableExecutionAdapter",
    "DurableTimerPolicy",
    "DurableWorkflowEngine",
    "EscalationManager",
    "IdempotencyDuplicateError",
    "InMemoryDurableStore",
    "LocalDurableAdapter",
    "SagaCompensationEntry",
    "SagaCoordinator",
    "SagaExecutionReport",
    "SequenceConflictError",
    "SQLiteDurableStore",
    "TemporalAdapterSpec",
    "TriggerDevAdapterSpec",
    "WorkflowAlreadyTerminalError",
    "WorkflowEvent",
    "WorkflowEventType",
    "WorkflowNotFoundError",
]
