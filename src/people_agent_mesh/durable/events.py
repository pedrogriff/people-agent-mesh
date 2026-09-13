"""
Durable Execution Event Models for PeopleAgentMesh.
Defines immutable, append-only domain events for event-sourcing and deterministic replay (ADR-007).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WorkflowEventType(StrEnum):
    WORKFLOW_STARTED = "WORKFLOW_STARTED"
    ACTIVITY_SCHEDULED = "ACTIVITY_SCHEDULED"
    ACTIVITY_COMPLETED = "ACTIVITY_COMPLETED"
    ACTIVITY_FAILED = "ACTIVITY_FAILED"
    STATUTORY_CHECKED = "STATUTORY_CHECKED"
    COMMITTEE_DELIBERATED = "COMMITTEE_DELIBERATED"
    HUMAN_INTERRUPT_SUSPENDED = "HUMAN_INTERRUPT_SUSPENDED"
    HUMAN_SIGNAL_RECEIVED = "HUMAN_SIGNAL_RECEIVED"
    TIMER_SCHEDULED = "TIMER_SCHEDULED"
    TIMER_FIRED = "TIMER_FIRED"
    SAGA_COMPENSATION_STARTED = "SAGA_COMPENSATION_STARTED"
    SAGA_COMPENSATION_COMPLETED = "SAGA_COMPENSATION_COMPLETED"
    WORKFLOW_COMPLETED = "WORKFLOW_COMPLETED"
    WORKFLOW_REJECTED = "WORKFLOW_REJECTED"
    WORKFLOW_REVISION_REQUESTED = "WORKFLOW_REVISION_REQUESTED"
    WORKFLOW_FAILED = "WORKFLOW_FAILED"
    WORKFLOW_CANCELLED = "WORKFLOW_CANCELLED"


class WorkflowEvent(BaseModel):
    """
    Immutable event in a durable workflow execution stream.
    Strict monotonic sequence numbers guarantee deterministic order of replay.
    """

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(default_factory=lambda: f"evt-{uuid.uuid4().hex[:12]}")
    workflow_id: str
    sequence_number: int = Field(ge=1)
    event_type: WorkflowEventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None
    checksum: str = ""

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        if not self.checksum:
            calculated_checksum = self.compute_checksum()
            # Since model is frozen, set via object.__setattr__
            object.__setattr__(self, "checksum", calculated_checksum)

    def compute_checksum(self) -> str:
        """Computes deterministic SHA256 digest of the canonical event content."""
        canonical_dict = {
            "workflow_id": self.workflow_id,
            "sequence_number": self.sequence_number,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "payload": self.payload,
            "idempotency_key": self.idempotency_key,
        }
        canonical_json = json.dumps(canonical_dict, sort_keys=True, default=str)
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()[:16]

    def verify_integrity(self) -> bool:
        """Verifies that the event's checksum matches its canonical payload."""
        return self.checksum == self.compute_checksum()
