"""
Concrete Enterprise Tool Implementations.
Wraps HRIS data systems, Market Benchmark calculations, Multi-Platform Knowledge sources,
and Slack dispatch with circuit breaking and contract validation.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from people_agent_mesh.core.state import EmployeeProfile
from people_agent_mesh.tools.contracts import (
    DocumentQueryInput,
    DocumentQueryOutput,
    HRISQueryInput,
    HRISQueryOutput,
    MarketBandInput,
    MarketBandOutput,
    SlackApprovalDispatchInput,
    SlackApprovalDispatchOutput,
)
from people_agent_mesh.tools.resilience import CircuitBreaker, IdempotencyManager


class EnterpriseHRISTool:
    """Mock HRIS system backed by in-memory records and a circuit breaker."""

    def __init__(self, profiles: list[EmployeeProfile] | None = None) -> None:
        self.breaker = CircuitBreaker(
            "HRIS_API", failure_threshold=3, recovery_timeout_seconds=10.0
        )
        self._db: dict[str, EmployeeProfile] = {p.employee_id: p for p in (profiles or [])}

    def register_employee(self, profile: EmployeeProfile) -> None:
        self._db[profile.employee_id] = profile

    def query(self, inp: HRISQueryInput) -> HRISQueryOutput:
        def _call() -> HRISQueryOutput:
            profile = self._db.get(inp.employee_id)
            if not profile:
                raise KeyError(f"Employee {inp.employee_id} not found in HRIS")

            return HRISQueryOutput(
                employee_id=profile.employee_id,
                name=profile.name,
                department=profile.department,
                level=profile.level,
                tenure_months=profile.tenure_months,
                performance_rating=profile.performance_rating,
                current_base_salary=profile.base_salary if inp.include_compensation else None,
                currency=profile.currency if inp.include_compensation else None,
                compa_ratio=profile.compa_ratio if inp.include_compensation else None,
            )

        return self.breaker.execute(_call)


class MarketBenchmarkTool:
    """Deterministic compensation band resolver using industry benchmark percentiles."""

    # Pre-calculated salary bands: (job_family, level, location_tier) -> (min, mid, max, currency)
    BANDS: dict[tuple[str, str, str], tuple[Decimal, Decimal, Decimal, str]] = {
        # Brazil - São Paulo (BRL)
        ("SOFTWARE_ENGINEERING", "IC4", "BR_SP"): (
            Decimal("180000"),
            Decimal("220000"),
            Decimal("260000"),
            "BRL",
        ),
        ("SOFTWARE_ENGINEERING", "IC5", "BR_SP"): (
            Decimal("240000"),
            Decimal("300000"),
            Decimal("360000"),
            "BRL",
        ),
        ("SOFTWARE_ENGINEERING", "IC6", "BR_SP"): (
            Decimal("330000"),
            Decimal("420000"),
            Decimal("510000"),
            "BRL",
        ),
        # United States - New York / SF Tier 1 (USD)
        ("SOFTWARE_ENGINEERING", "IC4", "US_NYC"): (
            Decimal("160000"),
            Decimal("190000"),
            Decimal("225000"),
            "USD",
        ),
        ("SOFTWARE_ENGINEERING", "IC5", "US_NYC"): (
            Decimal("210000"),
            Decimal("255000"),
            Decimal("305000"),
            "USD",
        ),
        ("SOFTWARE_ENGINEERING", "IC6", "US_NYC"): (
            Decimal("275000"),
            Decimal("340000"),
            Decimal("410000"),
            "USD",
        ),
        # Canada - Toronto Tier 1 (CAD)
        ("SOFTWARE_ENGINEERING", "IC4", "CA_TORONTO"): (
            Decimal("130000"),
            Decimal("155000"),
            Decimal("180000"),
            "CAD",
        ),
        ("SOFTWARE_ENGINEERING", "IC5", "CA_TORONTO"): (
            Decimal("170000"),
            Decimal("205000"),
            Decimal("240000"),
            "CAD",
        ),
    }

    def resolve(self, inp: MarketBandInput) -> MarketBandOutput:
        key = (inp.job_family, inp.level, inp.location_tier)
        if key not in self.BANDS:
            # Fallback to IC4 US_NYC
            key = ("SOFTWARE_ENGINEERING", "IC4", "US_NYC")

        b_min, b_mid, b_max, curr = self.BANDS[key]
        spread = (b_max - b_min) / b_min
        return MarketBandOutput(
            band_min=b_min,
            band_mid=b_mid,
            band_max=b_max,
            currency=curr,
            spread=spread.quantize(Decimal("0.0001")),
        )


class MultiPlatformKnowledgeTool:
    """Ingests and searches documents across Slack, Confluence, and Google Docs."""

    def __init__(self, initial_docs: list[dict[str, Any]] | None = None) -> None:
        self._documents: list[dict[str, Any]] = list(initial_docs or [])

    def add_document(self, doc: dict[str, Any]) -> None:
        self._documents.append(doc)

    def query(self, inp: DocumentQueryInput) -> DocumentQueryOutput:
        matches = [
            d
            for d in self._documents
            if d.get("subject_employee_id") == inp.subject_employee_id
            and d.get("category") in inp.categories
        ]
        return DocumentQueryOutput(
            documents=matches[: inp.limit],
            total_found=len(matches),
        )


class SlackApprovalTool:
    """Dispatches interactive approval blocks to Slack with idempotency keys."""

    def __init__(self, idempotency: IdempotencyManager | None = None) -> None:
        self.idempotency = idempotency or IdempotencyManager()
        self.dispatches: list[dict[str, Any]] = []

    def dispatch(self, inp: SlackApprovalDispatchInput) -> SlackApprovalDispatchOutput:
        # Check idempotency
        cached = self.idempotency.get(inp.callback_token)
        if cached:
            return SlackApprovalDispatchOutput.model_validate(cached)

        record = {
            "dispatched": True,
            "channel": f"#people-approvals-{inp.approver_role.lower()}",
            "message_ts": f"1726000000.{len(self.dispatches) + 1}",
            "callback_url": f"https://mesh.nubank.internal/api/v1/approvals/{inp.callback_token}",
        }
        self.dispatches.append({"input": inp.model_dump(), "result": record})
        self.idempotency.store(inp.callback_token, record)
        return SlackApprovalDispatchOutput.model_validate(record)
