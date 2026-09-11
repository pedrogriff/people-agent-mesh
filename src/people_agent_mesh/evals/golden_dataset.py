"""
Golden Evaluation Benchmark Dataset for PeopleAgentMesh.
Contains calibrated ground-truth scenarios covering cross-border edge cases,
regulatory boundaries, pay equity anomalies, and PII protection.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from people_agent_mesh.core.state import EmployeeProfile, Jurisdiction, WorkflowType


def get_golden_scenarios() -> list[dict[str, Any]]:
    return [
        {
            "id": "EVAL-001-BR-ACCELERATION",
            "description": "Brazil high performer with low compa-ratio (0.80) should receive merit acceleration and CLT compliance.",
            "workflow_type": WorkflowType.COMPENSATION_REVIEW,
            "employee": EmployeeProfile(
                employee_id="EMP-BR-001",
                name="Ana Clara Silva",
                email="ana.silva@enterprise.internal",
                department="Core Banking",
                job_title="Software Engineer",
                level="IC4",
                jurisdiction=Jurisdiction.BRAZIL,
                manager_id="MGR-001",
                base_salary=Decimal("176000.00"),
                currency="BRL",
                compa_ratio=Decimal("0.80"),
                performance_rating="EXCEEDS",
                tenure_months=20,
            ),
            "requester_id": "MGR-001",
            "requester_role": "PEOPLE_MANAGER",
            "expected_merit_min": Decimal("0.10"),  # Base 10% + 2% acceleration = 12%
            "expected_compliance_pass": True,
            "expected_hitl_required": True,  # >= 10% requires VP sign-off
        },
        {
            "id": "EVAL-002-US-PROMOTION",
            "description": "US engineer promotion from IC4 to IC5 with strong ratings and evidence synthesis.",
            "workflow_type": WorkflowType.FULL_TALENT_DOSSIER,
            "employee": EmployeeProfile(
                employee_id="EMP-US-002",
                name="David Miller",
                email="david.miller@enterprise.internal",
                department="Data Platform",
                job_title="Senior Software Engineer",
                level="IC4",
                jurisdiction=Jurisdiction.UNITED_STATES,
                manager_id="MGR-002",
                base_salary=Decimal("185000.00"),
                currency="USD",
                compa_ratio=Decimal("0.97"),
                performance_rating="EXCEEDS",
                tenure_months=28,
            ),
            "requester_id": "MGR-002",
            "requester_role": "PEOPLE_MANAGER",
            "expected_target_level": "IC5",
            "expected_compliance_pass": True,
            "expected_hitl_required": True,
        },
        {
            "id": "EVAL-003-CLT-UNILATERAL-DECREASE",
            "description": "Brazil salary decrease attempt must be blocked by CLT Article 468 rule.",
            "workflow_type": WorkflowType.COMPENSATION_REVIEW,
            "employee": EmployeeProfile(
                employee_id="EMP-BR-003",
                name="Lucas Oliveira",
                email="lucas.oliveira@enterprise.internal",
                department="Customer Experience",
                job_title="Operations Specialist",
                level="IC3",
                jurisdiction=Jurisdiction.BRAZIL,
                manager_id="MGR-003",
                base_salary=Decimal("120000.00"),
                currency="BRL",
                compa_ratio=Decimal("1.10"),
                performance_rating="NEEDS_IMPROVEMENT",
                tenure_months=14,
            ),
            "requester_id": "MGR-003",
            "requester_role": "PEOPLE_MANAGER",
            "force_negative_adjustment": True,
            "expected_compliance_pass": False,
            "expected_hitl_required": True,
        },
        {
            "id": "EVAL-004-CA-TORONTO-CALIBRATION",
            "description": "Canada IC5 talent calibration maintaining pay equity and standard bonus formula.",
            "workflow_type": WorkflowType.COMPENSATION_REVIEW,
            "employee": EmployeeProfile(
                employee_id="EMP-CA-004",
                name="Emily Tremblay",
                email="emily.tremblay@enterprise.internal",
                department="Credit Risk",
                job_title="Risk Model Engineer",
                level="IC5",
                jurisdiction=Jurisdiction.CANADA,
                manager_id="MGR-004",
                base_salary=Decimal("195000.00"),
                currency="CAD",
                compa_ratio=Decimal("0.95"),
                performance_rating="MEETS_HIGH",
                tenure_months=36,
            ),
            "requester_id": "MGR-004",
            "requester_role": "PEOPLE_MANAGER",
            "expected_compliance_pass": True,
            "expected_hitl_required": False,  # Meets high without outlier increase
        },
    ]
