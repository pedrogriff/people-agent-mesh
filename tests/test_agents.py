from decimal import Decimal

from people_agent_mesh.agents.compensation import CompensationAgent
from people_agent_mesh.agents.promotion import PromotionAgent
from people_agent_mesh.agents.supervisor import MeshSupervisorAgent
from people_agent_mesh.core.state import (
    ApprovalStatus,
    EmployeeProfile,
    Jurisdiction,
    MeshState,
    WorkflowStatus,
    WorkflowType,
)


def _sample_employee(
    level: str = "IC4", compa: str = "0.80", rating: str = "EXCEEDS"
) -> EmployeeProfile:
    return EmployeeProfile(
        employee_id="EMP-TEST-1",
        name="Beatriz Lima",
        email="beatriz@enterprise.internal",
        department="Core Engineering",
        job_title="Software Engineer",
        level=level,
        jurisdiction=Jurisdiction.BRAZIL,
        manager_id="MGR-1",
        base_salary=Decimal("176000.00"),
        currency="BRL",
        compa_ratio=Decimal(compa),
        performance_rating=rating,
        tenure_months=24,
    )


def test_compensation_agent_merit_calculation() -> None:
    emp = _sample_employee(compa="0.80", rating="EXCEEDS")
    state = MeshState(
        workflow_id="WF-COMP-1",
        workflow_type=WorkflowType.COMPENSATION_REVIEW,
        jurisdiction=Jurisdiction.BRAZIL,
        employee=emp,
        requester_id="MGR-1",
        requester_role="PEOPLE_MANAGER",
    )

    agent = CompensationAgent()
    result = agent.execute(state)

    assert result.success is True
    assert result.state.comp_proposal is not None
    # Base 10% + 2% acceleration for compa < 0.85 = 12%
    assert result.state.comp_proposal.percentage_increase == Decimal("0.12")
    expected_new_base = (Decimal("176000.00") * Decimal("1.12")).quantize(Decimal("0.01"))
    assert result.state.comp_proposal.proposed_base == expected_new_base
    assert result.state.comp_proposal.calculated_bonus > Decimal("0")


def test_promotion_agent_synthesis() -> None:
    emp = _sample_employee(level="IC4", rating="EXCEEDS")
    state = MeshState(
        workflow_id="WF-PROMO-1",
        workflow_type=WorkflowType.PROMOTION_CALIBRATION,
        jurisdiction=Jurisdiction.BRAZIL,
        employee=emp,
        requester_id="MGR-1",
        requester_role="PEOPLE_MANAGER",
    )

    agent = PromotionAgent()
    result = agent.execute(state)

    assert result.success is True
    assert result.state.promotion_proposal is not None
    assert result.state.promotion_proposal.proposed_level == "IC5"
    assert result.state.promotion_proposal.readiness_score >= 0.85


def test_supervisor_hitl_workflow_and_resume() -> None:
    emp = _sample_employee(level="IC4", compa="0.80", rating="EXCEEDS")
    state = MeshState(
        workflow_id="WF-SUP-1",
        workflow_type=WorkflowType.FULL_TALENT_DOSSIER,
        jurisdiction=Jurisdiction.BRAZIL,
        employee=emp,
        requester_id="MGR-1",
        requester_role="PEOPLE_MANAGER",
    )

    supervisor = MeshSupervisorAgent()
    result = supervisor.execute(state)

    assert result.success is True
    # 12% merit + promotion triggers HITL interruption
    assert result.state.status == WorkflowStatus.AWAITING_HUMAN_APPROVAL
    assert result.state.approval_request is not None
    assert result.state.approval_request.required_role == "VP_ENGINEERING"

    # Now resume with human approval
    resumed = supervisor.resume_human_decision(
        state=result.state,
        decision=ApprovalStatus.APPROVED,
        decided_by="vp.eng@enterprise.internal",
        comments="Approved in calibration committee.",
    )

    assert resumed.status == WorkflowStatus.COMPLETED
    assert resumed.approval_request is not None
    assert resumed.approval_request.status == ApprovalStatus.APPROVED
    assert resumed.approval_request.decided_by == "vp.eng@enterprise.internal"
