"""
Saga Orchestration & Compensation Coordinator for PeopleAgentMesh.
Provides backwards compensation, side-effect revocation, and transactional rollback (ADR-007).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from people_agent_mesh.core.state import MeshState

logger = logging.getLogger(__name__)


class SagaCompensationEntry(BaseModel):
    """Record of a registered compensating transaction."""

    step_name: str
    description: str
    action_type: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    registered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SagaExecutionReport(BaseModel):
    """Report generated when a saga rollback is executed."""

    workflow_id: str
    executed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    reason: str
    compensated_steps: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    success: bool = True


class SagaCoordinator:
    """
    Coordinates forward activity registrations and executes backwards compensation
    steps when a workflow is rejected, cancelled, or aborted.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[MeshState, dict[str, Any]], str]] = {}
        self._registered_entries: dict[str, list[SagaCompensationEntry]] = {}
        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        def release_headroom_handler(state: MeshState, params: dict[str, Any]) -> str:
            currency = params.get("currency", state.employee.currency)
            amount = params.get("amount", "0.00")
            dept = state.employee.department
            return f"Released provisional merit budget hold of {currency} {amount} back to {dept} envelope."

        def revoke_provisional_level_handler(state: MeshState, params: dict[str, Any]) -> str:
            target_level = params.get("target_level", "Unknown")
            return (
                f"Revoked provisional HRIS promotion reservation for target level {target_level}."
            )

        def restore_prior_compa_ratio_handler(state: MeshState, params: dict[str, Any]) -> str:
            prior_compa = params.get("prior_compa", str(state.employee.compa_ratio))
            return f"Restored baseline compa-ratio benchmark at {prior_compa}."

        def notify_slack_channel_handler(state: MeshState, params: dict[str, Any]) -> str:
            role = params.get("role", "PEOPLE_PARTNER")
            return f"Dispatched automated cancellation & audit rollback notification to {role} channel."

        self.register_handler("release_headroom", release_headroom_handler)
        self.register_handler("revoke_provisional_level", revoke_provisional_level_handler)
        self.register_handler("restore_prior_compa", restore_prior_compa_ratio_handler)
        self.register_handler("notify_slack_channel", notify_slack_channel_handler)

    def register_handler(
        self, action_type: str, handler: Callable[[MeshState, dict[str, Any]], str]
    ) -> None:
        self._handlers[action_type] = handler

    def record_forward_activity(
        self,
        workflow_id: str,
        step_name: str,
        action_type: str,
        description: str,
        parameters: dict[str, Any] | None = None,
    ) -> None:
        """Registers a compensating transaction for a completed forward activity."""
        entries = self._registered_entries.setdefault(workflow_id, [])
        entries.append(
            SagaCompensationEntry(
                step_name=step_name,
                description=description,
                action_type=action_type,
                parameters=parameters or {},
            )
        )

    def get_registered_steps(self, workflow_id: str) -> list[SagaCompensationEntry]:
        return list(self._registered_entries.get(workflow_id, []))

    def execute_compensation(
        self,
        state: MeshState,
        reason: str,
    ) -> SagaExecutionReport:
        """
        Executes registered compensating transactions in reverse chronological order (LIFO).
        """
        workflow_id = state.workflow_id
        entries = self._registered_entries.get(workflow_id, [])
        compensated: list[str] = []
        errors: list[str] = []

        logger.info(
            f"Executing saga rollback for workflow {workflow_id}: {len(entries)} steps to compensate."
        )

        # Reverse order: LIFO
        for entry in reversed(entries):
            handler = self._handlers.get(entry.action_type)
            if not handler:
                msg = f"No handler registered for saga action '{entry.action_type}'"
                logger.warning(msg)
                errors.append(msg)
                continue

            try:
                msg = handler(state, entry.parameters)
                compensated.append(f"[{entry.step_name}] {msg}")
            except Exception as ex:
                err_msg = f"Failed compensating step '{entry.step_name}': {ex}"
                logger.error(err_msg)
                errors.append(err_msg)

        # Clear compensated steps once rolled back
        if workflow_id in self._registered_entries:
            del self._registered_entries[workflow_id]

        return SagaExecutionReport(
            workflow_id=workflow_id,
            reason=reason,
            compensated_steps=compensated,
            errors=errors,
            success=len(errors) == 0,
        )
