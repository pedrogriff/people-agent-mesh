from decimal import Decimal

from people_agent_mesh.core.state import CompensationProposal, EmployeeProfile, Jurisdiction
from people_agent_mesh.security.compliance import ComplianceEngine


def test_brazil_clt_salary_decrease_violation() -> None:
    emp = EmployeeProfile(
        employee_id="EMP-BR-1",
        name="Camila Costa",
        email="camila@nubank.internal",
        department="Engineering",
        job_title="Software Engineer",
        level="IC4",
        jurisdiction=Jurisdiction.BRAZIL,
        manager_id="MGR-1",
        base_salary=Decimal("150000.00"),
        currency="BRL",
        compa_ratio=Decimal("0.90"),
        performance_rating="MEETS",
        tenure_months=12,
    )

    bad_proposal = CompensationProposal(
        current_base=Decimal("150000.00"),
        proposed_base=Decimal("140000.00"),  # Reduction!
        percentage_increase=Decimal("-0.0667"),
        compa_ratio_after=Decimal("0.84"),
        rationale="Cost cutting reduction.",
    )

    report = ComplianceEngine.verify(emp, bad_proposal)
    assert report.passed is False
    assert any("CLT Article 468" in v for v in report.violations)


def test_us_flsa_threshold_warning() -> None:
    emp = EmployeeProfile(
        employee_id="EMP-US-1",
        name="John Doe",
        email="john@nubank.internal",
        department="Support",
        job_title="Associate",
        level="IC2",
        jurisdiction=Jurisdiction.UNITED_STATES,
        manager_id="MGR-1",
        base_salary=Decimal("50000.00"),
        currency="USD",
        compa_ratio=Decimal("0.75"),
        performance_rating="MEETS",
        tenure_months=6,
    )

    proposal = CompensationProposal(
        current_base=Decimal("50000.00"),
        proposed_base=Decimal("52000.00"),
        percentage_increase=Decimal("0.04"),
        compa_ratio_after=Decimal("0.78"),
        rationale="Annual raise.",
    )

    report = ComplianceEngine.verify(emp, proposal)
    assert report.passed is True  # Passed but has warnings
    assert any("FLSA Warning" in w for w in report.warnings)
    assert any("Title VII" in w for w in report.warnings)


def test_canada_pay_equity_warning() -> None:
    emp = EmployeeProfile(
        employee_id="EMP-CA-1",
        name="Alexandre Roy",
        email="alex@nubank.internal",
        department="Engineering",
        job_title="Staff Engineer",
        level="IC6",
        jurisdiction=Jurisdiction.CANADA,
        manager_id="MGR-1",
        base_salary=Decimal("180000.00"),
        currency="CAD",
        compa_ratio=Decimal("0.95"),
        performance_rating="EXCEEDS",
        tenure_months=18,
    )

    # Massive discretionary jump
    huge_proposal = CompensationProposal(
        current_base=Decimal("180000.00"),
        proposed_base=Decimal("250000.00"),
        percentage_increase=Decimal("0.3889"),
        compa_ratio_after=Decimal("1.30"),
        rationale="Retention adjustment.",
    )

    report = ComplianceEngine.verify(emp, huge_proposal)
    assert any("Canadian Pay Transparency Warning" in w for w in report.warnings)
