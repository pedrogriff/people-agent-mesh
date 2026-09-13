"""
Core State Models & Schemas for PeopleAgentMesh.
Provides immutable state representations, lifecycle transitions, and checkpoint serialization.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Jurisdiction(StrEnum):
    BRAZIL = "BRAZIL"  # CLT, LGPD, BRL currency
    UNITED_STATES = "UNITED_STATES"  # FLSA, Title VII, USD currency
    CANADA = "CANADA"  # PIPEDA, Employment Standards, CAD currency


class WorkflowStatus(StrEnum):
    INITIATED = "INITIATED"
    IN_PROGRESS = "IN_PROGRESS"
    AWAITING_HUMAN_APPROVAL = "AWAITING_HUMAN_APPROVAL"
    APPROVED = "APPROVED"
    REVISION_REQUESTED = "REVISION_REQUESTED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SECURITY_BLOCKED = "SECURITY_BLOCKED"


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REVISION_REQUESTED = "REVISION_REQUESTED"


class WorkflowType(StrEnum):
    COMPENSATION_REVIEW = "COMPENSATION_REVIEW"
    PROMOTION_CALIBRATION = "PROMOTION_CALIBRATION"
    FULL_TALENT_DOSSIER = "FULL_TALENT_DOSSIER"
    ANNUAL_CALIBRATION_COMMITTEE = "ANNUAL_CALIBRATION_COMMITTEE"


class PerformanceRating(StrEnum):
    EXCEEDS = "EXCEEDS"
    MEETS_HIGH = "MEETS_HIGH"
    MEETS = "MEETS"
    NEEDS_IMPROVEMENT = "NEEDS_IMPROVEMENT"


class EmployeeProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    employee_id: str
    name: str
    email: str
    department: str
    job_title: str
    level: str  # e.g., "IC4", "IC5", "M1"
    jurisdiction: Jurisdiction
    manager_id: str
    base_salary: Decimal
    currency: str  # "BRL", "USD", "CAD"
    compa_ratio: Decimal  # e.g., 0.95
    performance_rating: str  # "EXCEEDS", "MEETS_HIGH", "MEETS", "NEEDS_IMPROVEMENT"
    tenure_months: int


class CompensationProposal(BaseModel):
    current_base: Decimal
    proposed_base: Decimal
    percentage_increase: Decimal
    proposed_equity_shares: int = 0
    bonus_target_pct: Decimal = Decimal("0.15")
    individual_perf_factor: Decimal = Decimal("1.0")
    company_perf_factor: Decimal = Decimal("1.0")
    calculated_bonus: Decimal = Decimal("0.0")
    compa_ratio_after: Decimal
    rationale: str = ""


class PromotionProposal(BaseModel):
    current_level: str
    proposed_level: str
    readiness_score: float = Field(ge=0.0, le=1.0)
    business_impact_summary: str
    key_accomplishments: list[str] = Field(default_factory=list)
    competency_gaps: list[str] = Field(default_factory=list)


class ApprovalRequest(BaseModel):
    request_id: str
    workflow_id: str
    required_role: str  # e.g., "PEOPLE_PARTNER", "VP_ENGINEERING", "TOTAL_REWARDS_DIR"
    triggered_reason: str
    risk_score: float  # 0.0 to 1.0
    status: ApprovalStatus = ApprovalStatus.PENDING
    decided_by: str | None = None
    decided_at: datetime | None = None
    decision_comments: str | None = None


class DebateRole(StrEnum):
    ADVOCATE = "ADVOCATE"
    SKEPTIC = "SKEPTIC"
    EQUITY_AUDITOR = "EQUITY_AUDITOR"
    CONSENSUS_MODERATOR = "CONSENSUS_MODERATOR"


class CommitteeVerdict(StrEnum):
    PROMOTION_ENDORSED = "PROMOTION_ENDORSED"
    PROMOTION_DEFERRED = "PROMOTION_DEFERRED"
    CONDITIONAL_ENDORSEMENT = "CONDITIONAL_ENDORSEMENT"
    COMPENSATION_ACCELERATION_ONLY = "COMPENSATION_ACCELERATION_ONLY"


class DebateTurn(BaseModel):
    speaker: DebateRole
    round_number: int
    statement: str
    key_arguments: list[str] = Field(default_factory=list)
    risks_or_objections: list[str] = Field(default_factory=list)
    evidence_citations: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReflexionCritique(BaseModel):
    round_number: int
    critique_score: float = Field(ge=0.0, le=1.0)
    passed: bool
    unaddressed_objections: list[str] = Field(default_factory=list)
    coaching_specificity_issues: list[str] = Field(default_factory=list)
    budget_or_equity_warnings: list[str] = Field(default_factory=list)
    refinement_guidance: list[str] = Field(default_factory=list)
    requires_revision: bool = False


class CalibrationCommitteeDossier(BaseModel):
    verdict: CommitteeVerdict
    calibrated_level: str
    calibrated_increase_pct: Decimal
    executive_summary: str
    points_of_consensus: list[str] = Field(default_factory=list)
    points_of_friction: list[str] = Field(default_factory=list)
    actionable_coaching_milestones: list[str] = Field(default_factory=list)
    debate_transcript: list[DebateTurn] = Field(default_factory=list)
    reflexion_critiques: list[ReflexionCritique] = Field(default_factory=list)
    reflexion_iterations: int = 0
    final_equity_clearance: bool = True
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AuditEntry(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    actor: str
    action: str
    details: dict[str, Any] = Field(default_factory=dict)


class MeshState(BaseModel):
    """
    Immutable State snapshot for an active PeopleAgentMesh execution.
    Supports pause/resume checkpointing across human-in-the-loop gates.
    """

    workflow_id: str
    status: WorkflowStatus = WorkflowStatus.INITIATED
    workflow_type: WorkflowType
    jurisdiction: Jurisdiction
    employee: EmployeeProfile
    requester_id: str
    requester_role: str

    # Domain proposals
    comp_proposal: CompensationProposal | None = None
    promotion_proposal: PromotionProposal | None = None

    # Multi-Agent Calibration Committee (ADR-006)
    committee_dossier: CalibrationCommitteeDossier | None = None

    # Governance & Approval
    approval_request: ApprovalRequest | None = None
    compliance_passed: bool = False
    compliance_violations: list[str] = Field(default_factory=list)

    # Ingestion & Context
    retrieved_documents: list[dict[str, Any]] = Field(default_factory=list)
    intermediate_artifacts: dict[str, Any] = Field(default_factory=dict)
    executive_dossier: str | None = None
    audit_trail: list[AuditEntry] = Field(default_factory=list)

    # Security & Adversarial Defense
    security_assessment: dict[str, Any] | None = None
    canary_tokens: list[str] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def record_audit(
        self, actor: str, action: str, details: dict[str, Any] | None = None
    ) -> MeshState:
        entry = AuditEntry(
            actor=actor,
            action=action,
            details=details or {},
        )
        new_audit = list(self.audit_trail) + [entry]
        return self.model_copy(
            update={
                "audit_trail": new_audit,
                "updated_at": datetime.now(UTC),
            }
        )

    def to_snapshot(self) -> dict[str, Any]:
        """Serializes state to a persistent JSON-safe checkpoint."""
        return self.model_dump(mode="json")

    @classmethod
    def from_snapshot(cls, data: dict[str, Any]) -> MeshState:
        """Hydrates state from a persistent checkpoint."""
        return cls.model_validate(data)
