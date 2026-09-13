"""
Durable Timers & SLA Escalation Policies for PeopleAgentMesh.
Handles asynchronous timeout evaluation, human escalation ladders, and auto-deferrals (ADR-007).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel

from people_agent_mesh.core.state import MeshState, WorkflowStatus
from people_agent_mesh.durable.events import WorkflowEvent, WorkflowEventType


class DurableTimerPolicy(BaseModel):
    """Configuration for human review SLAs and escalation hierarchies."""

    primary_sla_seconds: float = 3600.0 * 24.0  # 24 hours
    escalate_to_role: str = "VP_ENGINEERING"
    secondary_sla_seconds: float = 3600.0 * 48.0  # 48 hours
    secondary_escalate_to_role: str = "CHIEF_PEOPLE_OFFICER"
    final_action_on_timeout: str = "AUTO_DEFER_NEXT_CYCLE"


class EscalationManager:
    """Evaluates pending human reviews and triggers durable timer escalation events."""

    def __init__(self, default_policy: DurableTimerPolicy | None = None) -> None:
        self.policy = default_policy or DurableTimerPolicy()

    def create_timer_event(
        self,
        workflow_id: str,
        sequence_number: int,
        duration_seconds: float,
        target_role: str,
    ) -> WorkflowEvent:
        """Emits a TIMER_SCHEDULED event for deterministic SLA tracking."""
        fire_at = datetime.now(UTC) + timedelta(seconds=duration_seconds)
        return WorkflowEvent(
            workflow_id=workflow_id,
            sequence_number=sequence_number,
            event_type=WorkflowEventType.TIMER_SCHEDULED,
            payload={
                "duration_seconds": duration_seconds,
                "target_role": target_role,
                "scheduled_fire_at": fire_at.isoformat(),
            },
        )

    def evaluate_escalation(
        self,
        state: MeshState,
        elapsed_seconds: float,
        current_sequence: int,
        policy_override: DurableTimerPolicy | None = None,
    ) -> tuple[MeshState, WorkflowEvent | None]:
        """
        Assesses if a pending human review has breached SLA thresholds,
        escalates role hierarchy, and generates a TIMER_FIRED event.
        """
        if state.status != WorkflowStatus.AWAITING_HUMAN_APPROVAL or not state.approval_request:
            return state, None

        policy = policy_override or self.policy
        req = state.approval_request
        current_role = req.required_role

        escalated_role = None
        action_note = None

        if elapsed_seconds >= policy.secondary_sla_seconds:
            escalated_role = policy.secondary_escalate_to_role
            action_note = (
                f"SLA breached {elapsed_seconds / 3600:.1f}h (threshold: {policy.secondary_sla_seconds / 3600:.1f}h). "
                f"Escalated from {current_role} to {escalated_role}."
            )
        elif elapsed_seconds >= policy.primary_sla_seconds:
            if (
                current_role != policy.escalate_to_role
                and current_role != policy.secondary_escalate_to_role
            ):
                escalated_role = policy.escalate_to_role
                action_note = (
                    f"SLA breached {elapsed_seconds / 3600:.1f}h (threshold: {policy.primary_sla_seconds / 3600:.1f}h). "
                    f"Escalated from {current_role} to {escalated_role}."
                )

        if not escalated_role:
            return state, None

        # Build updated approval request and audit
        updated_req = req.model_copy(
            update={
                "required_role": escalated_role,
                "triggered_reason": f"{req.triggered_reason} [ESCALATED: {action_note}]",
            }
        )

        now = datetime.now(UTC)
        updated_state = state.model_copy(
            update={
                "approval_request": updated_req,
                "updated_at": now,
            }
        ).record_audit(
            actor="DurableEscalationTimer",
            action="HUMAN_APPROVAL_SLA_ESCALATED",
            details={
                "prior_role": current_role,
                "escalated_role": escalated_role,
                "elapsed_seconds": elapsed_seconds,
            },
        )

        event = WorkflowEvent(
            workflow_id=state.workflow_id,
            sequence_number=current_sequence + 1,
            event_type=WorkflowEventType.TIMER_FIRED,
            payload={
                "prior_role": current_role,
                "escalated_role": escalated_role,
                "elapsed_seconds": elapsed_seconds,
                "action_note": action_note,
            },
        )

        return updated_state, event
