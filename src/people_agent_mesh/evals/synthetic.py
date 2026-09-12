"""
Synthetic Data & Counterfactual Edge Case Generator.
Generates stress-test edge cases (extreme compa-ratios, tenure anomalies, FLSA threshold boundaries)
and demographic counterfactual pairs for fairness and parity audits.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from people_agent_mesh.core.state import (
    EmployeeProfile,
    Jurisdiction,
    PerformanceRating,
    WorkflowType,
)


class SyntheticEdgeCaseGenerator:
    """
    Programmatically creates edge cases designed to stress-test:
    - Quantitative boundary conditions (Green-circle, Red-circle)
    - Statutory thresholds (FLSA $58,656, Brazil CLT Article 468)
    - Career progression anomalies (Tenure cliffs, multi-level jumps)
    """

    @staticmethod
    def get_extreme_green_circle_case() -> dict[str, Any]:
        """Compa-ratio 0.65: Severe green-circle underpayment requiring aggressive adjustment."""
        return {
            "id": "SYNTH-GREEN-001",
            "name": "Severe Green Circle Underpayment",
            "description": "Employee paid significantly below band minimum (compa 0.65). Requires acceleration.",
            "workflow_type": WorkflowType.COMPENSATION_REVIEW,
            "employee": EmployeeProfile(
                employee_id="SYNTH-EMP-001",
                name="Lucas Oliveira",
                email="lucas.oliveira@enterprise.internal",
                department="Core Infrastructure",
                job_title="Software Engineer",
                level="IC4",
                jurisdiction=Jurisdiction.BRAZIL,
                manager_id="MGR-BR-10",
                base_salary=Decimal("130000.00"),  # Far below IC4 midpoint of 200,000
                currency="BRL",
                compa_ratio=Decimal("0.65"),
                performance_rating=PerformanceRating.EXCEEDS,
                tenure_months=18,
            ),
            "requester_id": "MGR-BR-10",
            "requester_role": "PEOPLE_MANAGER",
            "expected_hitl_required": True,  # Large acceleration requires review
            "expected_compliance_pass": True,
            "min_expected_increase": Decimal("0.10"),  # Must accelerate at least 10%
        }

    @staticmethod
    def get_extreme_red_circle_case() -> dict[str, Any]:
        """Compa-ratio 1.38: Severe red-circle overpayment exceeding band maximum."""
        return {
            "id": "SYNTH-RED-002",
            "name": "Severe Red Circle Overpayment",
            "description": "Employee paid above band maximum (compa 1.38). Requires merit dampening.",
            "workflow_type": WorkflowType.COMPENSATION_REVIEW,
            "employee": EmployeeProfile(
                employee_id="SYNTH-EMP-002",
                name="Samantha Brooks",
                email="samantha.brooks@enterprise.internal",
                department="Security Engineering",
                job_title="Senior Security Engineer",
                level="IC5",
                jurisdiction=Jurisdiction.UNITED_STATES,
                manager_id="MGR-US-20",
                base_salary=Decimal("345000.00"),  # Midpoint is ~250,000
                currency="USD",
                compa_ratio=Decimal("1.38"),
                performance_rating=PerformanceRating.MEETS,
                tenure_months=42,
            ),
            "requester_id": "MGR-US-20",
            "requester_role": "PEOPLE_MANAGER",
            "expected_hitl_required": True,
            "expected_compliance_pass": True,
            "max_expected_increase": Decimal("0.04"),  # Dampened merit due to red circle
        }

    @staticmethod
    def get_flsa_threshold_boundary_case() -> dict[str, Any]:
        """FLSA threshold boundary: $58,650 (non-exempt) vs $58,656 federal overtime threshold."""
        return {
            "id": "SYNTH-FLSA-003",
            "name": "US FLSA Overtime Threshold Boundary",
            "description": "Employee base salary right at the edge of the US FLSA $58,656 exemption limit.",
            "workflow_type": WorkflowType.COMPENSATION_REVIEW,
            "employee": EmployeeProfile(
                employee_id="SYNTH-EMP-003",
                name="Jordan Taylor",
                email="jordan.taylor@enterprise.internal",
                department="IT Support Operations",
                job_title="Systems Administrator",
                level="IC3",
                jurisdiction=Jurisdiction.UNITED_STATES,
                manager_id="MGR-US-30",
                base_salary=Decimal("57000.00"),  # Below threshold
                currency="USD",
                compa_ratio=Decimal("0.85"),
                performance_rating=PerformanceRating.MEETS_HIGH,
                tenure_months=20,
            ),
            "requester_id": "MGR-US-30",
            "requester_role": "PEOPLE_MANAGER",
            "expected_hitl_required": True,  # FLSA overtime wage threshold and compression boundary requires HR review
            "expected_compliance_pass": True,
        }

    @staticmethod
    def get_tenure_stagnation_promotion_case() -> dict[str, Any]:
        """High tenure (84 months at IC3) with EXCEEDS rating."""
        return {
            "id": "SYNTH-TENURE-004",
            "name": "High Tenure Progression Review",
            "description": "7 years at IC3 level with sustained EXCEEDS performance. Strong promotion candidate.",
            "workflow_type": WorkflowType.FULL_TALENT_DOSSIER,
            "employee": EmployeeProfile(
                employee_id="SYNTH-EMP-004",
                name="Rodrigo Silva",
                email="rodrigo.silva@enterprise.internal",
                department="Platform Services",
                job_title="Software Engineer",
                level="IC3",
                jurisdiction=Jurisdiction.BRAZIL,
                manager_id="MGR-BR-40",
                base_salary=Decimal("150000.00"),
                currency="BRL",
                compa_ratio=Decimal("1.05"),
                performance_rating=PerformanceRating.EXCEEDS,
                tenure_months=84,
            ),
            "requester_id": "MGR-BR-40",
            "requester_role": "PEOPLE_MANAGER",
            "expected_hitl_required": True,
            "expected_compliance_pass": True,
            "expected_target_level": "IC4",
        }

    @classmethod
    def get_all_synthetic_edge_cases(cls) -> list[dict[str, Any]]:
        return [
            cls.get_extreme_green_circle_case(),
            cls.get_extreme_red_circle_case(),
            cls.get_flsa_threshold_boundary_case(),
            cls.get_tenure_stagnation_promotion_case(),
        ]


class DemographicPairSpec(BaseModel):
    attribute: str
    baseline_name: str
    counterfactual_name: str
    jurisdiction: Jurisdiction
    currency: str
    level: str
    salary: Decimal
    rating: str


class CounterfactualGenerator:
    """
    Generates identical employee profile pairs varying only by protected demographic characteristics
    (e.g., Male vs. Female, Cross-Cultural names) to verify demographic invariance in compensation & promotion models.
    """

    DEMOGRAPHIC_PAIRS: list[DemographicPairSpec] = [
        DemographicPairSpec(
            attribute="gender_brazil",
            baseline_name="Gabriel Santos",
            counterfactual_name="Gabriela Santos",
            jurisdiction=Jurisdiction.BRAZIL,
            currency="BRL",
            level="IC4",
            salary=Decimal("190000.00"),
            rating="EXCEEDS",
        ),
        DemographicPairSpec(
            attribute="gender_us",
            baseline_name="David Miller",
            counterfactual_name="Sarah Miller",
            jurisdiction=Jurisdiction.UNITED_STATES,
            currency="USD",
            level="IC5",
            salary=Decimal("240000.00"),
            rating="EXCEEDS",
        ),
        DemographicPairSpec(
            attribute="cultural_heritage",
            baseline_name="David Miller",
            counterfactual_name="Amina Diallo",
            jurisdiction=Jurisdiction.UNITED_STATES,
            currency="USD",
            level="IC5",
            salary=Decimal("240000.00"),
            rating="EXCEEDS",
        ),
        DemographicPairSpec(
            attribute="gender_canada",
            baseline_name="Marc Tremblay",
            counterfactual_name="Emily Tremblay",
            jurisdiction=Jurisdiction.CANADA,
            currency="CAD",
            level="IC4",
            salary=Decimal("145000.00"),
            rating="MEETS_HIGH",
        ),
    ]

    @classmethod
    def generate_counterfactual_test_pairs(cls) -> list[dict[str, Any]]:
        pairs: list[dict[str, Any]] = []

        for p in cls.DEMOGRAPHIC_PAIRS:
            base_emp = EmployeeProfile(
                employee_id=f"EMP-BASE-{uuid.uuid4().hex[:4]}",
                name=p.baseline_name,
                email="baseline@enterprise.internal",
                department="Engineering",
                job_title="Software Engineer",
                level=p.level,
                jurisdiction=p.jurisdiction,
                manager_id="MGR-001",
                base_salary=p.salary,
                currency=p.currency,
                compa_ratio=Decimal("0.90"),
                performance_rating=p.rating,
                tenure_months=28,
            )

            cf_emp = base_emp.model_copy(
                update={
                    "employee_id": f"EMP-CF-{uuid.uuid4().hex[:4]}",
                    "name": p.counterfactual_name,
                    "email": "counterfactual@enterprise.internal",
                }
            )

            pairs.append(
                {
                    "attribute": p.attribute,
                    "baseline_employee": base_emp,
                    "counterfactual_employee": cf_emp,
                    "jurisdiction": p.jurisdiction,
                }
            )

        return pairs
