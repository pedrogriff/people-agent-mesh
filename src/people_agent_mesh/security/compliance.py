"""
Multi-Jurisdictional Regulatory & Labor Compliance Engine.
Evaluates proposals against statutory requirements in Brazil (CLT/LGPD),
United States (FLSA/Title VII), and Canada (PIPEDA/ESA).
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from people_agent_mesh.core.state import CompensationProposal, EmployeeProfile, Jurisdiction


class ComplianceReport(BaseModel):
    passed: bool
    jurisdiction: Jurisdiction
    violations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ComplianceEngine:
    """
    Automated pre-flight and post-flight regulatory verifier.
    """

    # US FLSA Minimum Salary Threshold for Exempt Status (Annual USD)
    US_FLSA_EXEMPT_MIN_USD = Decimal("58656")

    # Brazilian Minimum Wage / Band baseline checks
    BR_MINIMUM_BASE_BRL = Decimal("1412.00")

    @classmethod
    def verify(
        cls,
        employee: EmployeeProfile,
        comp_proposal: CompensationProposal | None = None,
        is_on_parental_leave: bool = False,
    ) -> ComplianceReport:
        jurisdiction = employee.jurisdiction
        violations: list[str] = []
        warnings: list[str] = []

        if comp_proposal:
            # Universal Rule 1: No negative salary adjustments without formal restructuring
            if comp_proposal.proposed_base < comp_proposal.current_base:
                if jurisdiction == Jurisdiction.BRAZIL:
                    violations.append(
                        "CLT Article 468 / CF Art. 7 Violation: Unilateral reduction of base salary is strictly prohibited under Brazilian labor law."
                    )
                else:
                    violations.append(
                        "Policy Violation: Proposed base salary cannot be lower than current base salary."
                    )

            # Jurisdiction: BRAZIL (CLT & LGPD)
            if jurisdiction == Jurisdiction.BRAZIL:
                if comp_proposal.proposed_base < cls.BR_MINIMUM_BASE_BRL:
                    violations.append("CLT Violation: Proposed salary is below statutory baseline.")

                # Maternity / Parental leave protection (CLT / Súmula TST)
                if is_on_parental_leave and comp_proposal.percentage_increase < Decimal("0.0"):
                    violations.append(
                        "Brazilian Labor Protection: Adverse compensation adjustment detected for an employee on statutory parental leave."
                    )

            # Jurisdiction: UNITED STATES (FLSA & Title VII)
            elif jurisdiction == Jurisdiction.UNITED_STATES:
                if comp_proposal.proposed_base < cls.US_FLSA_EXEMPT_MIN_USD:
                    warnings.append(
                        f"FLSA Warning: Proposed base salary ${comp_proposal.proposed_base} is near/below the FLSA exempt threshold of ${cls.US_FLSA_EXEMPT_MIN_USD}."
                    )

                # Extreme compa-ratio deviation warning
                if comp_proposal.compa_ratio_after < Decimal("0.80"):
                    warnings.append(
                        "Title VII / Equal Pay Warning: Compa-ratio post-adjustment remains below 0.80, risking pay compression and equity disparity."
                    )

            # Jurisdiction: CANADA (PIPEDA & Employment Standards)
            elif jurisdiction == Jurisdiction.CANADA:
                if comp_proposal.percentage_increase > Decimal("0.30"):
                    warnings.append(
                        "Canadian Pay Transparency Warning: Discretionary increase > 30% requires Total Rewards Director review under provincial pay equity guidelines."
                    )

        passed = len(violations) == 0
        return ComplianceReport(
            passed=passed,
            jurisdiction=jurisdiction,
            violations=violations,
            warnings=warnings,
        )
