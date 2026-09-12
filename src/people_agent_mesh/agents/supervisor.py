"""
Mesh Supervisor Agent & Workflow Orchestration Controller.
Directs sub-agents, orchestrates HITL interruption checkpoints,
and evaluates composite organizational risk.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from people_agent_mesh.agents.base import AgentResult, BaseAgent
from people_agent_mesh.agents.compensation import CompensationAgent
from people_agent_mesh.agents.promotion import PromotionAgent
from people_agent_mesh.core.state import (
    ApprovalRequest,
    ApprovalStatus,
    MeshState,
    WorkflowStatus,
    WorkflowType,
)
from people_agent_mesh.security.abac import ABACSecurityEngine, RequesterContext
from people_agent_mesh.security.canary import CanaryLeakageException, CanaryManager
from people_agent_mesh.security.compliance import ComplianceEngine
from people_agent_mesh.security.guardrails import PromptInjectionGuardrail
from people_agent_mesh.security.tokenizer import ZeroRetentionPrivacyGateway
from people_agent_mesh.tools.contracts import SlackApprovalDispatchInput
from people_agent_mesh.tools.enterprise_tools import SlackApprovalTool


class MeshSupervisorAgent(BaseAgent):
    def __init__(
        self,
        comp_agent: CompensationAgent | None = None,
        promo_agent: PromotionAgent | None = None,
        privacy_gateway: ZeroRetentionPrivacyGateway | None = None,
        abac_engine: ABACSecurityEngine | None = None,
        slack_tool: SlackApprovalTool | None = None,
        guardrail: PromptInjectionGuardrail | None = None,
        canary_manager: CanaryManager | None = None,
    ) -> None:
        super().__init__(name="MeshSupervisorAgent")
        self.comp_agent = comp_agent or CompensationAgent()
        self.promo_agent = promo_agent or PromotionAgent()
        self.privacy_gateway = privacy_gateway or ZeroRetentionPrivacyGateway()
        self.abac_engine = abac_engine
        self.slack_tool = slack_tool or SlackApprovalTool()
        self.guardrail = guardrail or PromptInjectionGuardrail()
        self.canary_manager = canary_manager or CanaryManager()

    def _assess_risk(self, state: MeshState) -> tuple[float, str, str]:
        """
        Computes composite risk score (0.0 - 1.0), triggering reason, and required approver.
        """
        reasons: list[str] = []
        risk_score = 0.10
        required_role = "PEOPLE_PARTNER"

        if state.comp_proposal:
            # High salary increase (> 10% requires VP, > 7% requires People Partner)
            if state.comp_proposal.percentage_increase >= Decimal("0.10"):
                risk_score += 0.40
                reasons.append(
                    f"High merit increase: {(state.comp_proposal.percentage_increase * 100):.1f}%"
                )
                required_role = "VP_ENGINEERING"
            elif state.comp_proposal.percentage_increase >= Decimal("0.07"):
                risk_score += 0.25
                reasons.append("Merit increase >= 7%")

            # Compa-ratio out of band
            if state.comp_proposal.compa_ratio_after > Decimal("1.15"):
                risk_score += 0.20
                reasons.append("Post-increase compa-ratio exceeds 1.15 (upper band boundary)")

        if state.promotion_proposal:
            risk_score += 0.30
            reasons.append(
                f"Level promotion requested: {state.promotion_proposal.current_level} -> {state.promotion_proposal.proposed_level}"
            )
            if state.promotion_proposal.readiness_score < 0.80:
                risk_score += 0.20
                reasons.append("Promotion readiness score below 0.80 confidence threshold")
                required_role = "VP_ENGINEERING"

        if state.compliance_violations:
            risk_score = 1.0
            reasons.append(f"Compliance violations: {', '.join(state.compliance_violations)}")
            required_role = "CHIEF_PEOPLE_OFFICER"

        return (
            min(1.0, risk_score),
            "; ".join(reasons) if reasons else "Routine calibration",
            required_role,
        )

    def execute(self, state: MeshState) -> AgentResult:
        start_time = time.time()
        current_state = state

        # 0. Pre-Flight Adversarial Prompt Injection & Threat Assessment
        raw_inputs_to_scan: list[str] = []
        for v in state.intermediate_artifacts.values():
            if isinstance(v, str):
                raw_inputs_to_scan.append(v)
        for doc in state.retrieved_documents:
            if isinstance(doc, dict):
                for dv in doc.values():
                    if isinstance(dv, str):
                        raw_inputs_to_scan.append(dv)

        for raw_text in raw_inputs_to_scan:
            assessment = self.guardrail.evaluate_threat(raw_text)
            if assessment.is_blocked:
                blocked_state = current_state.model_copy(
                    update={
                        "status": WorkflowStatus.SECURITY_BLOCKED,
                        "security_assessment": assessment.model_dump(),
                    }
                ).record_audit(
                    actor=self.name,
                    action="SECURITY_ALERT_PROMPT_INJECTION_BLOCKED",
                    details=assessment.model_dump(),
                )
                return AgentResult(
                    agent_name=self.name,
                    success=False,
                    state=blocked_state,
                    errors=[assessment.explanation],
                    duration_ms=(time.time() - start_time) * 1000,
                )

        # 1. ABAC Authorization check if engine is attached
        if self.abac_engine:
            ctx = RequesterContext(
                user_id=state.requester_id,
                role=state.requester_role,
                department=state.employee.department,
            )
            is_comp = state.workflow_type in {
                WorkflowType.COMPENSATION_REVIEW,
                WorkflowType.FULL_TALENT_DOSSIER,
            }
            if not self.abac_engine.can_access_employee_data(
                ctx, state.employee.employee_id, is_compensation_data=is_comp
            ):
                err = f"ABAC Denied: Requester {ctx.user_id} with role {ctx.role} unauthorized to access employee {state.employee.employee_id}"
                failed_state = current_state.model_copy(
                    update={"status": WorkflowStatus.FAILED}
                ).record_audit(actor=self.name, action="ABAC_DENIAL", details={"error": err})
                return AgentResult(
                    agent_name=self.name,
                    success=False,
                    state=failed_state,
                    errors=[err],
                )

        current_state = current_state.model_copy(update={"status": WorkflowStatus.IN_PROGRESS})

        # 2. Delegate to Specialist Sub-Agents based on WorkflowType if proposal not already supplied
        if state.workflow_type in {
            WorkflowType.COMPENSATION_REVIEW,
            WorkflowType.FULL_TALENT_DOSSIER,
        }:
            if current_state.comp_proposal is None:
                comp_res = self.comp_agent.execute(current_state)
                current_state = comp_res.state

        if state.workflow_type in {
            WorkflowType.PROMOTION_CALIBRATION,
            WorkflowType.FULL_TALENT_DOSSIER,
        }:
            if current_state.promotion_proposal is None:
                promo_res = self.promo_agent.execute(current_state)
                current_state = promo_res.state

        # 3. Multi-Jurisdiction Compliance Verification
        comp_report = ComplianceEngine.verify(
            employee=current_state.employee,
            comp_proposal=current_state.comp_proposal,
        )
        current_state = current_state.model_copy(
            update={
                "compliance_passed": comp_report.passed,
                "compliance_violations": comp_report.violations,
            }
        ).record_audit(
            actor=self.name,
            action="VERIFY_COMPLIANCE",
            details={"passed": comp_report.passed, "violations": comp_report.violations},
        )

        # 4. Composite Risk Evaluation & HITL Gating
        risk_score, triggered_reason, required_role = self._assess_risk(current_state)

        # Any risk score >= 0.40 or compliance violation triggers Human-in-the-Loop Interruption Gate
        if risk_score >= 0.40 or not comp_report.passed:
            req_id = f"REQ-{uuid.uuid4().hex[:8].upper()}"
            approval_req = ApprovalRequest(
                request_id=req_id,
                workflow_id=current_state.workflow_id,
                required_role=required_role,
                triggered_reason=triggered_reason,
                risk_score=risk_score,
                status=ApprovalStatus.PENDING,
            )

            # Dispatch notification to Slack
            callback_token = f"tok_{uuid.uuid4().hex[:12]}"
            self.slack_tool.dispatch(
                SlackApprovalDispatchInput(
                    workflow_id=current_state.workflow_id,
                    approver_role=required_role,
                    employee_name=self.privacy_gateway.tokenize(current_state.employee.name),
                    proposed_action=current_state.workflow_type.value,
                    risk_score=risk_score,
                    executive_summary=triggered_reason,
                    callback_token=callback_token,
                )
            )

            current_state = current_state.model_copy(
                update={
                    "status": WorkflowStatus.AWAITING_HUMAN_APPROVAL,
                    "approval_request": approval_req,
                }
            ).record_audit(
                actor=self.name,
                action="HITL_INTERRUPT_TRIGGERED",
                details={
                    "request_id": req_id,
                    "required_role": required_role,
                    "risk_score": risk_score,
                },
            )
        else:
            current_state = current_state.model_copy(
                update={
                    "status": WorkflowStatus.COMPLETED,
                }
            ).record_audit(
                actor=self.name,
                action="AUTO_APPROVED_LOW_RISK",
                details={"risk_score": risk_score},
            )

        # 5. Post-Flight Tripwire Barrier: Assert zero canary leakage in outputs
        texts_to_verify: list[str] = []
        if current_state.comp_proposal:
            texts_to_verify.append(current_state.comp_proposal.rationale)
        if current_state.promotion_proposal:
            texts_to_verify.append(current_state.promotion_proposal.business_impact_summary)

        for out_text in texts_to_verify:
            if out_text:
                try:
                    self.canary_manager.assert_zero_canary_leakage(out_text)
                except CanaryLeakageException as cle:
                    leaked_state = current_state.model_copy(
                        update={"status": WorkflowStatus.SECURITY_BLOCKED}
                    ).record_audit(
                        actor=self.name,
                        action="SECURITY_ALERT_CANARY_LEAK_DETECTED",
                        details={"canary_token": cle.token},
                    )
                    return AgentResult(
                        agent_name=self.name,
                        success=False,
                        state=leaked_state,
                        errors=[str(cle)],
                        duration_ms=(time.time() - start_time) * 1000,
                    )

        duration = (time.time() - start_time) * 1000
        return AgentResult(
            agent_name=self.name,
            success=True,
            state=current_state,
            rationale=f"Workflow processed. Status: {current_state.status.value}, Risk Score: {risk_score:.2f}",
            duration_ms=duration,
        )

    def resume_human_decision(
        self,
        state: MeshState,
        decision: ApprovalStatus,
        decided_by: str,
        comments: str | None = None,
    ) -> MeshState:
        """
        Resumes an interrupted workflow following human sign-off via webhook or Slack callback.
        """
        if state.status != WorkflowStatus.AWAITING_HUMAN_APPROVAL:
            raise ValueError(
                f"Cannot resume workflow in state {state.status}. Must be AWAITING_HUMAN_APPROVAL."
            )

        if not state.approval_request:
            raise ValueError("State is missing active ApprovalRequest.")

        now = datetime.now(UTC)
        updated_approval = state.approval_request.model_copy(
            update={
                "status": decision,
                "decided_by": decided_by,
                "decided_at": now,
                "decision_comments": comments,
            }
        )

        new_status = (
            WorkflowStatus.COMPLETED
            if decision == ApprovalStatus.APPROVED
            else (
                WorkflowStatus.REVISION_REQUESTED
                if decision == ApprovalStatus.REVISION_REQUESTED
                else WorkflowStatus.REJECTED
            )
        )

        return state.model_copy(
            update={
                "status": new_status,
                "approval_request": updated_approval,
                "updated_at": now,
            }
        ).record_audit(
            actor=decided_by,
            action=f"HUMAN_DECISION_{decision.value}",
            details={"decision": decision.value, "comments": comments or ""},
        )
