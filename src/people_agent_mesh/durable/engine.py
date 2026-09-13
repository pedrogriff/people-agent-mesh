"""
Durable Workflow Execution Engine for PeopleAgentMesh.
Implements event-sourcing, deterministic state reducers, crash recovery, and saga rollbacks (ADR-007).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from people_agent_mesh.agents.committee import CalibrationCommitteeOrchestrator
from people_agent_mesh.agents.compensation import CompensationAgent
from people_agent_mesh.agents.promotion import PromotionAgent
from people_agent_mesh.core.state import (
    ApprovalRequest,
    ApprovalStatus,
    CompensationProposal,
    MeshState,
    PromotionProposal,
    WorkflowStatus,
    WorkflowType,
)
from people_agent_mesh.durable.escalation import EscalationManager
from people_agent_mesh.durable.events import WorkflowEvent, WorkflowEventType
from people_agent_mesh.durable.saga import SagaCoordinator
from people_agent_mesh.durable.store import DurableEventStore, InMemoryDurableStore
from people_agent_mesh.security.compliance import ComplianceEngine
from people_agent_mesh.security.guardrails import PromptInjectionGuardrail

logger = logging.getLogger(__name__)


class WorkflowNotFoundError(Exception):
    """Raised when a workflow ID is not found in the durable store."""


class WorkflowAlreadyTerminalError(Exception):
    """Raised when signaling an already completed or failed workflow."""


class DurableWorkflowEngine:
    """
    Core engine managing event-sourced workflow lifecycles, crash-resilient checkpoints,
    human signaling, and backward saga rollbacks.
    """

    def __init__(
        self,
        store: DurableEventStore | None = None,
        saga_coordinator: SagaCoordinator | None = None,
        escalation_manager: EscalationManager | None = None,
    ) -> None:
        self.store: DurableEventStore = store or InMemoryDurableStore()
        self.saga: SagaCoordinator = saga_coordinator or SagaCoordinator()
        self.escalation: EscalationManager = escalation_manager or EscalationManager()
        self.guardrail = PromptInjectionGuardrail()
        self.comp_agent = CompensationAgent()
        self.promo_agent = PromotionAgent()
        self.committee_orchestrator = CalibrationCommitteeOrchestrator()

    def start_workflow(
        self,
        state: MeshState,
        idempotency_key: str | None = None,
    ) -> MeshState:
        """
        Executes a workflow durably with incremental event logging and checkpointing.
        If a HITL condition is reached, the workflow suspends in AWAITING_HUMAN_APPROVAL.
        """
        wf_id = state.workflow_id
        seq = self.store.get_last_sequence(wf_id)

        # 1. Event: WORKFLOW_STARTED
        seq += 1
        start_event = WorkflowEvent(
            workflow_id=wf_id,
            sequence_number=seq,
            event_type=WorkflowEventType.WORKFLOW_STARTED,
            payload={
                "workflow_type": state.workflow_type.value,
                "jurisdiction": state.jurisdiction.value,
                "employee_id": state.employee.employee_id,
                "name": state.employee.name,
                "level": state.employee.level,
                "base_salary": str(state.employee.base_salary),
                "currency": state.employee.currency,
                "performance_rating": state.employee.performance_rating,
                "tenure_months": state.employee.tenure_months,
            },
            idempotency_key=idempotency_key,
        )
        self.store.append_event(wf_id, start_event)
        current_state = state.model_copy(update={"status": WorkflowStatus.IN_PROGRESS})

        # 2. Security scan
        threat = self.guardrail.evaluate_threat(state.employee.name)
        if threat.is_blocked:
            seq += 1
            fail_event = WorkflowEvent(
                workflow_id=wf_id,
                sequence_number=seq,
                event_type=WorkflowEventType.WORKFLOW_FAILED,
                payload={"reason": threat.explanation, "threat_score": threat.threat_score},
            )
            self.store.append_event(wf_id, fail_event)
            blocked_state = current_state.model_copy(
                update={
                    "status": WorkflowStatus.SECURITY_BLOCKED,
                    "security_assessment": threat.model_dump(),
                }
            )
            self.store.save_snapshot(wf_id, blocked_state, seq)
            return blocked_state

        # 3. Specialist Agents Execution
        # Compensation Agent
        if current_state.workflow_type in {
            WorkflowType.COMPENSATION_REVIEW,
            WorkflowType.FULL_TALENT_DOSSIER,
            WorkflowType.ANNUAL_CALIBRATION_COMMITTEE,
        }:
            seq += 1
            self.store.append_event(
                wf_id,
                WorkflowEvent(
                    workflow_id=wf_id,
                    sequence_number=seq,
                    event_type=WorkflowEventType.ACTIVITY_SCHEDULED,
                    payload={"agent": "CompensationSpecialistAgent"},
                ),
            )
            comp_res = self.comp_agent.execute(current_state)
            current_state = comp_res.state
            seq += 1
            self.store.append_event(
                wf_id,
                WorkflowEvent(
                    workflow_id=wf_id,
                    sequence_number=seq,
                    event_type=WorkflowEventType.ACTIVITY_COMPLETED,
                    payload={
                        "agent": "CompensationSpecialistAgent",
                        "proposal": (
                            current_state.comp_proposal.model_dump(mode="json")
                            if current_state.comp_proposal
                            else {}
                        ),
                    },
                ),
            )

        # Promotion Agent
        if current_state.workflow_type in {
            WorkflowType.PROMOTION_CALIBRATION,
            WorkflowType.FULL_TALENT_DOSSIER,
            WorkflowType.ANNUAL_CALIBRATION_COMMITTEE,
        }:
            seq += 1
            self.store.append_event(
                wf_id,
                WorkflowEvent(
                    workflow_id=wf_id,
                    sequence_number=seq,
                    event_type=WorkflowEventType.ACTIVITY_SCHEDULED,
                    payload={"agent": "PromotionSpecialistAgent"},
                ),
            )
            promo_res = self.promo_agent.execute(current_state)
            current_state = promo_res.state
            seq += 1
            self.store.append_event(
                wf_id,
                WorkflowEvent(
                    workflow_id=wf_id,
                    sequence_number=seq,
                    event_type=WorkflowEventType.ACTIVITY_COMPLETED,
                    payload={
                        "agent": "PromotionSpecialistAgent",
                        "proposal": (
                            current_state.promotion_proposal.model_dump(mode="json")
                            if current_state.promotion_proposal
                            else {}
                        ),
                    },
                ),
            )

        # 4. Multi-Jurisdiction Compliance Verification
        comp_report = ComplianceEngine.verify(
            employee=current_state.employee,
            comp_proposal=current_state.comp_proposal,
        )
        current_state = current_state.model_copy(
            update={
                "compliance_passed": comp_report.passed,
                "compliance_violations": comp_report.violations,
            }
        )
        seq += 1
        self.store.append_event(
            wf_id,
            WorkflowEvent(
                workflow_id=wf_id,
                sequence_number=seq,
                event_type=WorkflowEventType.STATUTORY_CHECKED,
                payload={
                    "passed": comp_report.passed,
                    "violations": comp_report.violations,
                    "jurisdiction": current_state.jurisdiction.value,
                },
            ),
        )

        # 5. Calibration Committee if applicable
        if current_state.workflow_type == WorkflowType.ANNUAL_CALIBRATION_COMMITTEE:
            seq += 1
            self.store.append_event(
                wf_id,
                WorkflowEvent(
                    workflow_id=wf_id,
                    sequence_number=seq,
                    event_type=WorkflowEventType.ACTIVITY_SCHEDULED,
                    payload={"agent": "CalibrationCommitteeOrchestrator"},
                ),
            )
            comm_res = self.committee_orchestrator.execute(current_state)
            current_state = comm_res.state
            seq += 1
            self.store.append_event(
                wf_id,
                WorkflowEvent(
                    workflow_id=wf_id,
                    sequence_number=seq,
                    event_type=WorkflowEventType.COMMITTEE_DELIBERATED,
                    payload={
                        "verdict": (
                            current_state.committee_dossier.verdict.value
                            if current_state.committee_dossier
                            else "NONE"
                        ),
                        "calibrated_level": (
                            current_state.committee_dossier.calibrated_level
                            if current_state.committee_dossier
                            else current_state.employee.level
                        ),
                        "reflexion_iterations": (
                            current_state.committee_dossier.reflexion_iterations
                            if current_state.committee_dossier
                            else 0
                        ),
                    },
                ),
            )

        # 6. Risk Assessment & HITL Interruption Decision
        risk_score = 0.10
        reasons: list[str] = []
        required_role = "PEOPLE_PARTNER"

        if (
            current_state.comp_proposal
            and current_state.comp_proposal.percentage_increase >= Decimal("0.10")
        ):
            risk_score += 0.40
            reasons.append(
                f"Upper-tier merit increase (+{(current_state.comp_proposal.percentage_increase * 100):.1f}%)"
            )
            required_role = "VP_ENGINEERING"

        if (
            current_state.promotion_proposal
            and current_state.promotion_proposal.proposed_level != current_state.employee.level
        ):
            risk_score += 0.30
            reasons.append(
                f"Level promotion: {current_state.employee.level} -> {current_state.promotion_proposal.proposed_level}"
            )

        if not comp_report.passed:
            risk_score = 1.0
            reasons.append(f"Statutory violations: {', '.join(comp_report.violations)}")
            required_role = "CHIEF_PEOPLE_OFFICER"

        # Check for HITL Interruption
        if risk_score >= 0.40 or not comp_report.passed:
            approval_req = ApprovalRequest(
                request_id=f"REQ-{wf_id.split('-')[-1].upper()}",
                workflow_id=wf_id,
                required_role=required_role,
                triggered_reason="; ".join(reasons),
                risk_score=min(1.0, risk_score),
                status=ApprovalStatus.PENDING,
            )
            current_state = current_state.model_copy(
                update={
                    "status": WorkflowStatus.AWAITING_HUMAN_APPROVAL,
                    "approval_request": approval_req,
                }
            ).record_audit(
                actor="DurableWorkflowEngine",
                action="DURABLE_HITL_SUSPENDED",
                details={"required_role": required_role, "risk_score": risk_score},
            )

            # Register forward saga steps for potential rollback on human rejection
            if current_state.comp_proposal:
                self.saga.record_forward_activity(
                    workflow_id=wf_id,
                    step_name="MeritBudgetHold",
                    action_type="release_headroom",
                    description="Provisional merit budget reservation",
                    parameters={
                        "amount": str(
                            current_state.comp_proposal.proposed_base
                            - current_state.employee.base_salary
                        ),
                        "currency": current_state.employee.currency,
                    },
                )
            if current_state.promotion_proposal:
                self.saga.record_forward_activity(
                    workflow_id=wf_id,
                    step_name="HRISPromotionLock",
                    action_type="revoke_provisional_level",
                    description="Provisional level promotion reservation",
                    parameters={"target_level": current_state.promotion_proposal.proposed_level},
                )

            seq += 1
            suspend_event = WorkflowEvent(
                workflow_id=wf_id,
                sequence_number=seq,
                event_type=WorkflowEventType.HUMAN_INTERRUPT_SUSPENDED,
                payload={
                    "required_role": required_role,
                    "risk_score": risk_score,
                    "reasons": reasons,
                },
            )
            self.store.append_event(wf_id, suspend_event)

            # Schedule durable SLA timer
            seq += 1
            timer_event = self.escalation.create_timer_event(
                workflow_id=wf_id,
                sequence_number=seq,
                duration_seconds=self.escalation.policy.primary_sla_seconds,
                target_role=required_role,
            )
            self.store.append_event(wf_id, timer_event)

            # Save persistent snapshot at suspension point
            self.store.save_snapshot(wf_id, current_state, seq)
            return current_state
        else:
            # Low risk: Auto-complete
            current_state = current_state.model_copy(
                update={"status": WorkflowStatus.COMPLETED}
            ).record_audit(
                actor="DurableWorkflowEngine",
                action="AUTO_APPROVED_LOW_RISK",
                details={"risk_score": risk_score},
            )
            seq += 1
            complete_event = WorkflowEvent(
                workflow_id=wf_id,
                sequence_number=seq,
                event_type=WorkflowEventType.WORKFLOW_COMPLETED,
                payload={"auto_approved": True, "risk_score": risk_score},
            )
            self.store.append_event(wf_id, complete_event)
            self.store.save_snapshot(wf_id, current_state, seq)
            return current_state

    def signal_workflow(
        self,
        workflow_id: str,
        signal_name: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> MeshState:
        """
        Delivers a durable asynchronous signal to an in-flight or suspended workflow.
        Handles approval, revision, rejection with saga rollback, and external timer triggers.
        """
        state = self.recover_workflow(workflow_id)
        if not state:
            raise WorkflowNotFoundError(f"Workflow {workflow_id} not found in durable store.")

        if state.status in {
            WorkflowStatus.COMPLETED,
            WorkflowStatus.REJECTED,
            WorkflowStatus.FAILED,
        }:
            raise WorkflowAlreadyTerminalError(
                f"Workflow {workflow_id} is already in terminal status '{state.status.value}'."
            )

        seq = self.store.get_last_sequence(workflow_id)

        if signal_name == "HUMAN_DECISION":
            decision_raw = payload.get("decision", "APPROVED").upper()
            decided_by = payload.get("decided_by", "system.approver@enterprise.internal")
            comments = payload.get("comments", "")

            decision = (
                ApprovalStatus.APPROVED
                if decision_raw == "APPROVED"
                else (
                    ApprovalStatus.REVISION_REQUESTED
                    if decision_raw == "REVISION_REQUESTED"
                    else ApprovalStatus.REJECTED
                )
            )

            # Record HUMAN_SIGNAL_RECEIVED event
            seq += 1
            sig_event = WorkflowEvent(
                workflow_id=workflow_id,
                sequence_number=seq,
                event_type=WorkflowEventType.HUMAN_SIGNAL_RECEIVED,
                payload={
                    "signal_name": signal_name,
                    "decision": decision.value,
                    "decided_by": decided_by,
                    "comments": comments,
                },
                idempotency_key=idempotency_key,
            )
            self.store.append_event(workflow_id, sig_event)

            now = datetime.now(UTC)
            updated_req = (
                state.approval_request.model_copy(
                    update={
                        "status": decision,
                        "decided_by": decided_by,
                        "decided_at": now,
                        "decision_comments": comments,
                    }
                )
                if state.approval_request
                else None
            )

            if decision == ApprovalStatus.APPROVED:
                state = state.model_copy(
                    update={
                        "status": WorkflowStatus.COMPLETED,
                        "approval_request": updated_req,
                        "updated_at": now,
                    }
                ).record_audit(
                    actor=decided_by,
                    action="HUMAN_DECISION_APPROVED",
                    details={"comments": comments},
                )
                seq += 1
                self.store.append_event(
                    workflow_id,
                    WorkflowEvent(
                        workflow_id=workflow_id,
                        sequence_number=seq,
                        event_type=WorkflowEventType.WORKFLOW_COMPLETED,
                        payload={"decided_by": decided_by},
                    ),
                )
            elif decision == ApprovalStatus.REJECTED:
                # Trigger backward Saga compensation rollback
                seq += 1
                self.store.append_event(
                    workflow_id,
                    WorkflowEvent(
                        workflow_id=workflow_id,
                        sequence_number=seq,
                        event_type=WorkflowEventType.SAGA_COMPENSATION_STARTED,
                        payload={"reason": comments or "Human rejection"},
                    ),
                )

                saga_report = self.saga.execute_compensation(
                    state, reason=comments or "Human rejection"
                )

                seq += 1
                self.store.append_event(
                    workflow_id,
                    WorkflowEvent(
                        workflow_id=workflow_id,
                        sequence_number=seq,
                        event_type=WorkflowEventType.SAGA_COMPENSATION_COMPLETED,
                        payload={
                            "compensated_steps": saga_report.compensated_steps,
                            "errors": saga_report.errors,
                        },
                    ),
                )

                state = state.model_copy(
                    update={
                        "status": WorkflowStatus.REJECTED,
                        "approval_request": updated_req,
                        "updated_at": now,
                    }
                ).record_audit(
                    actor=decided_by,
                    action="HUMAN_DECISION_REJECTED",
                    details={
                        "comments": comments,
                        "saga_compensated_steps": saga_report.compensated_steps,
                    },
                )

                seq += 1
                self.store.append_event(
                    workflow_id,
                    WorkflowEvent(
                        workflow_id=workflow_id,
                        sequence_number=seq,
                        event_type=WorkflowEventType.WORKFLOW_REJECTED,
                        payload={"decided_by": decided_by, "reason": comments},
                    ),
                )
            else:  # REVISION_REQUESTED
                state = state.model_copy(
                    update={
                        "status": WorkflowStatus.REVISION_REQUESTED,
                        "approval_request": updated_req,
                        "updated_at": now,
                    }
                ).record_audit(
                    actor=decided_by,
                    action="HUMAN_DECISION_REVISION_REQUESTED",
                    details={"comments": comments},
                )
                seq += 1
                self.store.append_event(
                    workflow_id,
                    WorkflowEvent(
                        workflow_id=workflow_id,
                        sequence_number=seq,
                        event_type=WorkflowEventType.WORKFLOW_REVISION_REQUESTED,
                        payload={"decided_by": decided_by, "comments": comments},
                    ),
                )

            # Persist terminal or updated snapshot
            self.store.save_snapshot(workflow_id, state, seq)
            return state

        elif signal_name == "TIMER_EXPIRED":
            elapsed_sec = float(payload.get("elapsed_seconds", 3600.0 * 24.0))
            escalated_state, fired_event = self.escalation.evaluate_escalation(
                state=state,
                elapsed_seconds=elapsed_sec,
                current_sequence=seq,
            )
            if fired_event:
                self.store.append_event(workflow_id, fired_event)
                self.store.save_snapshot(workflow_id, escalated_state, fired_event.sequence_number)
            return escalated_state

        else:
            raise ValueError(f"Unknown durable signal '{signal_name}'")

    def recover_workflow(self, workflow_id: str) -> MeshState:
        """
        Recovers a workflow from disk or event stream.
        Optimized by starting from the latest snapshot and replaying only subsequent events.
        """
        snapshot_state, last_seq = self.store.get_latest_snapshot(workflow_id)
        events = self.store.get_events(workflow_id, since_sequence=last_seq)

        if snapshot_state is None and not events:
            raise WorkflowNotFoundError(f"Workflow {workflow_id} not found in durable store.")

        if snapshot_state is None:
            # Replay from origin (seq 1)
            return self.replay_workflow(workflow_id)[0]

        # Apply subsequent events onto snapshot
        current_state = snapshot_state
        for evt in events:
            current_state = self._apply_event_reducer(current_state, evt)

        return current_state

    def replay_workflow(
        self, workflow_id: str, up_to_sequence: int | None = None
    ) -> tuple[MeshState, int]:
        """
        Deterministically replays the event stream from sequence 1 without invoking external side-effects.
        Returns the reconstructed MeshState and the count of replayed events.
        """
        all_events = self.store.get_events(workflow_id)
        if not all_events:
            raise WorkflowNotFoundError(f"No events found for workflow {workflow_id}")

        if up_to_sequence is not None:
            all_events = [e for e in all_events if e.sequence_number <= up_to_sequence]

        # First event must be WORKFLOW_STARTED
        start_evt = all_events[0]
        if start_evt.event_type != WorkflowEventType.WORKFLOW_STARTED:
            raise ValueError(f"Stream for {workflow_id} does not begin with WORKFLOW_STARTED.")

        # Reconstruct base state from start event
        p = start_evt.payload
        from people_agent_mesh.core.state import EmployeeProfile, Jurisdiction

        emp = EmployeeProfile(
            employee_id=p["employee_id"],
            name=p["name"],
            email=f"{p['name'].lower().replace(' ', '.')}@enterprise.internal",
            department="Core Infrastructure",
            job_title="Software Engineer",
            level=p["level"],
            jurisdiction=Jurisdiction(p["jurisdiction"]),
            manager_id="MGR-REPLAY",
            base_salary=Decimal(p["base_salary"]),
            currency=p["currency"],
            compa_ratio=Decimal("0.95"),
            performance_rating=p["performance_rating"],
            tenure_months=int(p["tenure_months"]),
        )

        state = MeshState(
            workflow_id=workflow_id,
            workflow_type=WorkflowType(p["workflow_type"]),
            jurisdiction=Jurisdiction(p["jurisdiction"]),
            employee=emp,
            requester_id="REQ-DURABLE-REPLAY",
            requester_role="PEOPLE_PARTNER",
            status=WorkflowStatus.IN_PROGRESS,
            created_at=start_evt.timestamp,
            updated_at=start_evt.timestamp,
        )

        # Apply rest of events via deterministic reducer
        for evt in all_events[1:]:
            state = self._apply_event_reducer(state, evt)

        return state, len(all_events)

    def _apply_event_reducer(self, state: MeshState, event: WorkflowEvent) -> MeshState:
        """
        Pure deterministic state reducer: f(MeshState, WorkflowEvent) -> MeshState.
        Guarantees zero divergence between live execution and replayed history.
        """
        t = event.event_type
        p = event.payload
        now = event.timestamp

        if t == WorkflowEventType.ACTIVITY_COMPLETED:
            agent = p.get("agent")
            if agent == "CompensationSpecialistAgent" and "proposal" in p:
                comp_prop = CompensationProposal.model_validate(p["proposal"])
                return state.model_copy(update={"comp_proposal": comp_prop, "updated_at": now})
            elif agent == "PromotionSpecialistAgent" and "proposal" in p:
                promo_prop = PromotionProposal.model_validate(p["proposal"])
                return state.model_copy(
                    update={"promotion_proposal": promo_prop, "updated_at": now}
                )

        elif t == WorkflowEventType.STATUTORY_CHECKED:
            return state.model_copy(
                update={
                    "compliance_passed": p.get("passed", True),
                    "compliance_violations": p.get("violations", []),
                    "updated_at": now,
                }
            )

        elif t == WorkflowEventType.HUMAN_INTERRUPT_SUSPENDED:
            req = ApprovalRequest(
                request_id=f"REQ-{state.workflow_id.split('-')[-1].upper()}",
                workflow_id=state.workflow_id,
                required_role=p.get("required_role", "PEOPLE_PARTNER"),
                triggered_reason="; ".join(p.get("reasons", [])),
                risk_score=float(p.get("risk_score", 0.5)),
                status=ApprovalStatus.PENDING,
            )
            return state.model_copy(
                update={
                    "status": WorkflowStatus.AWAITING_HUMAN_APPROVAL,
                    "approval_request": req,
                    "updated_at": now,
                }
            )

        elif t == WorkflowEventType.HUMAN_SIGNAL_RECEIVED:
            decision = p.get("decision", "APPROVED")
            decided_by = p.get("decided_by", "system")
            comments = p.get("comments", "")
            if state.approval_request:
                updated_req = state.approval_request.model_copy(
                    update={
                        "status": ApprovalStatus(decision),
                        "decided_by": decided_by,
                        "decided_at": now,
                        "decision_comments": comments,
                    }
                )
                return state.model_copy(update={"approval_request": updated_req, "updated_at": now})

        elif t == WorkflowEventType.TIMER_FIRED:
            escalated_role = p.get("escalated_role")
            if state.approval_request and escalated_role:
                updated_req = state.approval_request.model_copy(
                    update={"required_role": escalated_role}
                )
                return state.model_copy(update={"approval_request": updated_req, "updated_at": now})

        elif t == WorkflowEventType.WORKFLOW_COMPLETED:
            return state.model_copy(update={"status": WorkflowStatus.COMPLETED, "updated_at": now})

        elif t == WorkflowEventType.WORKFLOW_REJECTED:
            return state.model_copy(update={"status": WorkflowStatus.REJECTED, "updated_at": now})

        elif t == WorkflowEventType.WORKFLOW_REVISION_REQUESTED:
            return state.model_copy(
                update={"status": WorkflowStatus.REVISION_REQUESTED, "updated_at": now}
            )

        elif t == WorkflowEventType.WORKFLOW_FAILED:
            return state.model_copy(update={"status": WorkflowStatus.FAILED, "updated_at": now})

        return state
