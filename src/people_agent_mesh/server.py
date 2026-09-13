"""
FastAPI Enterprise Server for PeopleAgentMesh.
Provides RESTful endpoints for real-time multi-agent orchestration,
bi-directional PII tokenization, HITL approval webhooks, and CI eval execution.
"""

from __future__ import annotations

import os
import uuid
from decimal import Decimal
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from people_agent_mesh.agents.supervisor import MeshSupervisorAgent
from people_agent_mesh.core.state import (
    ApprovalStatus,
    CompensationProposal,
    EmployeeProfile,
    Jurisdiction,
    MeshState,
    WorkflowStatus,
    WorkflowType,
)
from people_agent_mesh.evals.runner import EvalSuiteRunner
from people_agent_mesh.mcp.sse import router as mcp_router
from people_agent_mesh.security.abac import ABACSecurityEngine, ReportingHierarchy
from people_agent_mesh.security.tokenizer import PIITokenVault, ZeroRetentionPrivacyGateway
from people_agent_mesh.telemetry.tracer import MeshTelemetryTracer

app = FastAPI(
    title="PeopleAgentMesh Platform API",
    description="Enterprise Multi-Agent Orchestration & Governance for Sensitive People Operations",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Model Context Protocol (MCP) Server Router
app.include_router(mcp_router)

# Shared In-Memory State & Singletons
vault = PIITokenVault()
privacy_gateway = ZeroRetentionPrivacyGateway(vault)
hierarchy = ReportingHierarchy(
    {
        "MGR-EXEC-01": ["EMP-BR-8821", "EMP-US-1020", "EMP-CA-3040"],
        "MGR-ENG-02": ["EMP-BR-1100"],
    }
)
abac_engine = ABACSecurityEngine(hierarchy)
supervisor = MeshSupervisorAgent(abac_engine=abac_engine, privacy_gateway=privacy_gateway)
tracer = MeshTelemetryTracer()

# Workflow state store for active HITL gates: workflow_id -> MeshState
active_workflows: dict[str, MeshState] = {}


# Schemas
class TokenizeRequest(BaseModel):
    text: str


class TokenizeResponse(BaseModel):
    raw_text: str
    tokenized_text: str
    detokenized_text: str
    zero_pii_verified: bool


class ShredResponse(BaseModel):
    shredded_count: int
    message: str


class OrchestrateRequest(BaseModel):
    employee_id: str
    name: str
    email: str
    department: str
    job_title: str
    level: str
    jurisdiction: Jurisdiction
    manager_id: str = "MGR-EXEC-01"
    base_salary: Decimal
    currency: str
    compa_ratio: Decimal
    performance_rating: str
    tenure_months: int
    workflow_type: WorkflowType = WorkflowType.FULL_TALENT_DOSSIER
    requester_id: str = "MGR-EXEC-01"
    requester_role: str = "PEOPLE_MANAGER"
    proposed_base_override: Decimal | None = None


class DecisionRequest(BaseModel):
    workflow_id: str
    decision: ApprovalStatus
    decided_by: str
    comments: str | None = None


# Endpoints
@app.get("/api/v1/health")
def health_check() -> dict[str, str]:
    return {"status": "healthy", "service": "people-agent-mesh", "version": "0.1.0"}


@app.post("/api/v1/tokenize", response_model=TokenizeResponse)
def tokenize_endpoint(req: TokenizeRequest) -> TokenizeResponse:
    tokenized = privacy_gateway.tokenize(req.text)
    zero_leak = False
    try:
        zero_leak = privacy_gateway.assert_zero_pii_leakage(tokenized)
    except ValueError:
        zero_leak = False

    restored = privacy_gateway.detokenize(tokenized)
    return TokenizeResponse(
        raw_text=req.text,
        tokenized_text=tokenized,
        detokenized_text=restored,
        zero_pii_verified=zero_leak,
    )


@app.post("/api/v1/shred", response_model=ShredResponse)
def shred_endpoint() -> ShredResponse:
    count = vault.shred()
    return ShredResponse(
        shredded_count=count,
        message=f"Successfully shredded {count} surrogate token mappings per LGPD Article 18.",
    )


@app.post("/api/v1/orchestrate")
def orchestrate_endpoint(req: OrchestrateRequest) -> dict[str, Any]:
    emp = EmployeeProfile(
        employee_id=req.employee_id,
        name=req.name,
        email=req.email,
        department=req.department,
        job_title=req.job_title,
        level=req.level,
        jurisdiction=req.jurisdiction,
        manager_id=req.manager_id,
        base_salary=req.base_salary,
        currency=req.currency,
        compa_ratio=req.compa_ratio,
        performance_rating=req.performance_rating,
        tenure_months=req.tenure_months,
    )

    wf_id = f"WF-{uuid.uuid4().hex[:8].upper()}"
    state = MeshState(
        workflow_id=wf_id,
        workflow_type=req.workflow_type,
        jurisdiction=req.jurisdiction,
        employee=emp,
        requester_id=req.requester_id,
        requester_role=req.requester_role,
    )

    if req.proposed_base_override is not None:
        pct = (req.proposed_base_override - req.base_salary) / req.base_salary
        state = state.model_copy(
            update={
                "comp_proposal": CompensationProposal(
                    current_base=req.base_salary,
                    proposed_base=req.proposed_base_override,
                    percentage_increase=pct.quantize(Decimal("0.0001")),
                    compa_ratio_after=(req.proposed_base_override / Decimal("220000")).quantize(
                        Decimal("0.0001")
                    ),
                    rationale=f"Manual proposal of {req.proposed_base_override} submitted by {req.requester_id}.",
                )
            }
        )

    span = tracer.start_span(
        trace_id=f"tr-{wf_id.lower()}",
        agent_name="MeshSupervisorAgent",
        workflow_id=wf_id,
        department=emp.department,
    )

    result = supervisor.execute(state)
    active_workflows[wf_id] = result.state

    tracer.finish_span(span, prompt_tokens=1820, completion_tokens=510)
    cost_data = tracer.get_departmental_attribution().get(emp.department, {})

    return {
        "workflow_id": wf_id,
        "status": result.state.status.value,
        "success": result.success,
        "rationale": result.rationale,
        "employee": result.state.employee.model_dump(mode="json"),
        "comp_proposal": (
            result.state.comp_proposal.model_dump(mode="json")
            if result.state.comp_proposal
            else None
        ),
        "promotion_proposal": (
            result.state.promotion_proposal.model_dump(mode="json")
            if result.state.promotion_proposal
            else None
        ),
        "approval_request": (
            result.state.approval_request.model_dump(mode="json")
            if result.state.approval_request
            else None
        ),
        "compliance_passed": result.state.compliance_passed,
        "compliance_violations": result.state.compliance_violations,
        "audit_trail_count": len(result.state.audit_trail),
        "telemetry": {
            "duration_ms": round(result.duration_ms, 2),
            "tokens_consumed": result.tokens_consumed,
            "department_attribution": cost_data,
        },
    }


@app.post("/api/v1/approvals/decide")
def decide_approval_endpoint(req: DecisionRequest) -> dict[str, Any]:
    state = active_workflows.get(req.workflow_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Workflow {req.workflow_id} not found.")

    if state.status != WorkflowStatus.AWAITING_HUMAN_APPROVAL:
        raise HTTPException(
            status_code=400,
            detail=f"Workflow {req.workflow_id} is in status {state.status.value}, cannot decide.",
        )

    resumed_state = supervisor.resume_human_decision(
        state=state,
        decision=req.decision,
        decided_by=req.decided_by,
        comments=req.comments,
    )
    active_workflows[req.workflow_id] = resumed_state

    return {
        "workflow_id": req.workflow_id,
        "status": resumed_state.status.value,
        "approval_request": (
            resumed_state.approval_request.model_dump(mode="json")
            if resumed_state.approval_request
            else None
        ),
        "audit_trail": [entry.model_dump(mode="json") for entry in resumed_state.audit_trail],
    }


@app.get("/api/v1/evals")
def run_evals_endpoint() -> dict[str, Any]:
    runner = EvalSuiteRunner()
    res = runner.run()
    return res.model_dump(mode="json")


class CommitteeDeliberationRequest(BaseModel):
    employee_id: str = "EMP-CALIB-01"
    name: str = "Senior Staff Candidate"
    department: str = "Core Engineering"
    level: str = "IC4"
    target_level: str = "IC5"
    jurisdiction: str = "UNITED_STATES"
    base_salary: float = 175000.0
    currency: str = "USD"
    performance_rating: str = "EXCEEDS"
    tenure_months: int = 16
    compa_ratio: float = 0.95


@app.post("/api/v1/committee/deliberate")
def deliberate_committee_endpoint(req: CommitteeDeliberationRequest) -> dict[str, Any]:
    jur = (
        Jurisdiction.BRAZIL
        if "BRAZIL" in req.jurisdiction.upper()
        else (
            Jurisdiction.CANADA
            if "CANADA" in req.jurisdiction.upper()
            else Jurisdiction.UNITED_STATES
        )
    )

    emp = EmployeeProfile(
        employee_id=req.employee_id,
        name=req.name,
        email="candidate@enterprise.internal",
        department=req.department,
        job_title="Software Engineer",
        level=req.level,
        jurisdiction=jur,
        manager_id="MGR-001",
        base_salary=Decimal(str(req.base_salary)),
        currency=req.currency,
        compa_ratio=Decimal(str(req.compa_ratio)),
        performance_rating=req.performance_rating,
        tenure_months=req.tenure_months,
    )

    wf_id = f"wf-comm-{uuid.uuid4().hex[:8]}"
    state = MeshState(
        workflow_id=wf_id,
        workflow_type=WorkflowType.ANNUAL_CALIBRATION_COMMITTEE,
        jurisdiction=jur,
        employee=emp,
        requester_id="REQ-UI",
        requester_role="PEOPLE_PARTNER",
    )

    result = supervisor.execute(state)
    active_workflows[wf_id] = result.state

    dossier = result.state.committee_dossier
    return {
        "workflow_id": wf_id,
        "status": result.state.status.value,
        "verdict": dossier.verdict.value if dossier else "PENDING",
        "calibrated_level": dossier.calibrated_level if dossier else emp.level,
        "calibrated_increase_pct": (
            float(dossier.calibrated_increase_pct * 100) if dossier else 0.0
        ),
        "executive_summary": dossier.executive_summary if dossier else "",
        "points_of_consensus": dossier.points_of_consensus if dossier else [],
        "points_of_friction": dossier.points_of_friction if dossier else [],
        "actionable_coaching_milestones": (
            dossier.actionable_coaching_milestones if dossier else []
        ),
        "reflexion_iterations": dossier.reflexion_iterations if dossier else 0,
        "reflexion_critiques": (
            [c.model_dump(mode="json") for c in dossier.reflexion_critiques] if dossier else []
        ),
        "debate_transcript": (
            [t.model_dump(mode="json") for t in dossier.debate_transcript] if dossier else []
        ),
        "approval_required": result.state.status == WorkflowStatus.AWAITING_HUMAN_APPROVAL,
    }


# Static Assets and UI Mount
static_dir = os.path.join(os.path.dirname(__file__), "ui", "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def serve_index() -> FileResponse:
    index_file = os.path.join(static_dir, "index.html")
    if not os.path.exists(index_file):
        raise HTTPException(status_code=404, detail="UI index.html not found")
    return FileResponse(index_file)
