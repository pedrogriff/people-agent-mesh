"""
Comprehensive Unit & Integration Tests for Multi-Agent Calibration Committee (ADR-006).
Tests structured deliberation (Advocate, Skeptic, Equity Auditor, Consensus Moderator),
Reflexion self-correction loops, MCP tool contracts, and supervisor integration.
"""

from decimal import Decimal

from fastapi.testclient import TestClient

from people_agent_mesh.agents.committee import (
    AdvocateAgent,
    CalibrationCommitteeOrchestrator,
    ConsensusModeratorAgent,
    EquityAuditorAgent,
    ReflexionCritiqueEngine,
    SkepticAgent,
)
from people_agent_mesh.agents.compensation import CompensationAgent
from people_agent_mesh.agents.promotion import PromotionAgent
from people_agent_mesh.agents.supervisor import MeshSupervisorAgent
from people_agent_mesh.core.state import (
    CommitteeVerdict,
    DebateRole,
    EmployeeProfile,
    Jurisdiction,
    MeshState,
    WorkflowStatus,
    WorkflowType,
)
from people_agent_mesh.mcp.server import PeopleMeshMCPServer
from people_agent_mesh.server import app


def _create_sample_state(
    employee_id: str = "EMP-TEST-01",
    name: str = "Carlos Mendez",
    level: str = "IC4",
    rating: str = "EXCEEDS",
    tenure: int = 15,
    compa: str = "0.95",
    jurisdiction: Jurisdiction = Jurisdiction.UNITED_STATES,
) -> MeshState:
    emp = EmployeeProfile(
        employee_id=employee_id,
        name=name,
        email="carlos@enterprise.internal",
        department="Core Infrastructure",
        job_title="Senior Software Engineer",
        level=level,
        jurisdiction=jurisdiction,
        manager_id="MGR-001",
        base_salary=Decimal("170000.00"),
        currency="USD" if jurisdiction != Jurisdiction.BRAZIL else "BRL",
        compa_ratio=Decimal(compa),
        performance_rating=rating,
        tenure_months=tenure,
    )
    state = MeshState(
        workflow_id="wf-test-comm-01",
        workflow_type=WorkflowType.ANNUAL_CALIBRATION_COMMITTEE,
        jurisdiction=jurisdiction,
        employee=emp,
        requester_id="MGR-001",
        requester_role="ENGINEERING_DIRECTOR",
    )
    state = CompensationAgent().execute(state).state
    state = PromotionAgent().execute(state).state
    return state


def test_advocate_agent_statements() -> None:
    state = _create_sample_state()
    advocate = AdvocateAgent()
    open_turn = advocate.opening_statement(state)

    assert open_turn.speaker == DebateRole.ADVOCATE
    assert open_turn.round_number == 1
    assert "IC5" in open_turn.statement
    assert len(open_turn.key_arguments) >= 2

    # Test rebuttal
    skeptic = SkepticAgent()
    skep_turn = skeptic.challenge_statement(state, open_turn)
    equity = EquityAuditorAgent().audit(state)
    rebuttal = advocate.rebuttal_statement(state, skep_turn, equity)

    assert rebuttal.speaker == DebateRole.ADVOCATE
    assert rebuttal.round_number == 2
    assert len(rebuttal.key_arguments) >= 1


def test_skeptic_agent_challenge_and_closing() -> None:
    state = _create_sample_state(tenure=14)
    advocate = AdvocateAgent()
    open_turn = advocate.opening_statement(state)

    skeptic = SkepticAgent()
    challenge = skeptic.challenge_statement(state, open_turn)
    assert challenge.speaker == DebateRole.SKEPTIC
    assert challenge.round_number == 1
    assert any("tenure" in r.lower() for r in challenge.risks_or_objections)

    closing = skeptic.closing_assessment(state, open_turn)
    assert closing.speaker == DebateRole.SKEPTIC
    assert closing.round_number == 2
    assert (
        "concede" in closing.statement.lower()
        or "undisputed" in " ".join(closing.key_arguments).lower()
    )


def test_equity_auditor_statutory_and_budget() -> None:
    # US employee
    state_us = _create_sample_state(jurisdiction=Jurisdiction.UNITED_STATES)
    turn_us = EquityAuditorAgent().audit(state_us)
    assert turn_us.speaker == DebateRole.EQUITY_AUDITOR
    assert any("statutory" in k.lower() for k in turn_us.key_arguments)

    # Brazil employee
    state_br = _create_sample_state(jurisdiction=Jurisdiction.BRAZIL)
    turn_br = EquityAuditorAgent().audit(state_br)
    assert any("BRAZIL" in k for k in turn_br.key_arguments)


def test_reflexion_critique_engine_detects_flaws_and_passes_refinement() -> None:
    state = _create_sample_state(tenure=14)
    adv = AdvocateAgent().opening_statement(state)
    skep = SkepticAgent().challenge_statement(state, adv)
    eq = EquityAuditorAgent().audit(state)
    reb = AdvocateAgent().rebuttal_statement(state, skep, eq)
    closing = SkepticAgent().closing_assessment(state, reb)

    moderator = ConsensusModeratorAgent()
    draft = moderator.synthesize_draft(state, adv, skep, eq, reb, closing)

    engine = ReflexionCritiqueEngine()
    critique_1 = engine.critique(draft, skep, eq)

    # Draft contains vague coaching and unmitigated tenure objection
    assert critique_1.passed is False
    assert critique_1.requires_revision is True
    assert len(critique_1.coaching_specificity_issues) >= 1
    assert len(critique_1.unaddressed_objections) >= 1

    # Perform refinement
    refined = moderator.refine_consensus(draft, critique_1, state)
    critique_2 = engine.critique(refined, skep, eq)

    # Refined dossier must satisfy all criteria
    assert critique_2.passed is True
    assert critique_2.requires_revision is False
    assert critique_2.critique_score == 1.0


def test_committee_orchestrator_end_to_end() -> None:
    state = _create_sample_state(tenure=16)
    orchestrator = CalibrationCommitteeOrchestrator()
    dossier = orchestrator.run_committee(state)

    assert dossier.verdict in {
        CommitteeVerdict.PROMOTION_ENDORSED,
        CommitteeVerdict.CONDITIONAL_ENDORSEMENT,
    }
    assert dossier.calibrated_level == "IC5"
    assert dossier.reflexion_iterations >= 1
    assert len(dossier.actionable_coaching_milestones) >= 2
    assert len(dossier.debate_transcript) >= 5
    assert len(dossier.reflexion_critiques) >= 2
    assert dossier.reflexion_critiques[-1].passed is True


def test_supervisor_committee_workflow() -> None:
    state = _create_sample_state(tenure=15)
    supervisor = MeshSupervisorAgent()
    result = supervisor.execute(state)

    assert result.success is True
    assert result.state.committee_dossier is not None
    assert result.state.status == WorkflowStatus.AWAITING_HUMAN_APPROVAL
    assert result.state.approval_request is not None
    assert result.state.executive_dossier is not None
    assert "Calibration Committee" in result.state.executive_dossier


def test_mcp_run_calibration_committee_tool() -> None:
    mcp_server = PeopleMeshMCPServer()
    tool_res = mcp_server.call_tool(
        "run_calibration_committee",
        {
            "employee_id": "EMP-CALIB-99",
            "name": "Mariana Souza",
            "level": "IC4",
            "performance_rating": "EXCEEDS",
            "tenure_months": 15,
            "compa_ratio": 0.95,
            "jurisdiction": "BRAZIL",
        },
    )

    assert tool_res.isError is False
    content_text = tool_res.content[0]["text"]
    assert "CONDITIONAL_ENDORSEMENT" in content_text or "PROMOTION_ENDORSED" in content_text
    assert "points_of_consensus" in content_text
    assert "actionable_coaching_milestones" in content_text
    assert "reflexion_iterations" in content_text


def test_fastapi_committee_deliberate_endpoint() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/committee/deliberate",
        json={
            "employee_id": "EMP-API-101",
            "name": "Devin Wright",
            "department": "Infrastructure",
            "level": "IC4",
            "target_level": "IC5",
            "jurisdiction": "UNITED_STATES",
            "base_salary": 180000.0,
            "currency": "USD",
            "performance_rating": "EXCEEDS",
            "tenure_months": 26,
            "compa_ratio": 1.02,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] in {"COMPLETED", "AWAITING_HUMAN_APPROVAL"}
    assert data["verdict"] == CommitteeVerdict.PROMOTION_ENDORSED.value
    assert data["calibrated_level"] == "IC5"
    assert len(data["debate_transcript"]) >= 5
    assert len(data["actionable_coaching_milestones"]) >= 2


def test_counterfactual_parity_in_calibration_committee() -> None:
    """
    Asserts exact statistical invariance and parity across demographic twins
    during Multi-Agent Calibration Committee deliberation.
    """
    orchestrator = CalibrationCommitteeOrchestrator()

    state_a = _create_sample_state(
        employee_id="EMP-A", name="Gabriel Santos", tenure=18, jurisdiction=Jurisdiction.BRAZIL
    )
    state_b = _create_sample_state(
        employee_id="EMP-B", name="Gabriela Santos", tenure=18, jurisdiction=Jurisdiction.BRAZIL
    )

    dossier_a = orchestrator.run_committee(state_a)
    dossier_b = orchestrator.run_committee(state_b)

    assert dossier_a.verdict == dossier_b.verdict
    assert dossier_a.calibrated_level == dossier_b.calibrated_level
    assert dossier_a.calibrated_increase_pct == dossier_b.calibrated_increase_pct
    assert dossier_a.reflexion_iterations == dossier_b.reflexion_iterations
