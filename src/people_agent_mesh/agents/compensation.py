"""
Compensation Calibration Agent.
Computes deterministic merit increases, bonus payouts, and compa-ratio trajectories
using formal financial rules and Market Band benchmarks.
"""

from __future__ import annotations

import time
from decimal import Decimal

from people_agent_mesh.agents.base import AgentResult, BaseAgent
from people_agent_mesh.core.state import CompensationProposal, MeshState
from people_agent_mesh.tools.contracts import MarketBandInput
from people_agent_mesh.tools.enterprise_tools import MarketBenchmarkTool


class CompensationAgent(BaseAgent):
    def __init__(self, benchmark_tool: MarketBenchmarkTool | None = None) -> None:
        super().__init__(name="CompensationAgent")
        self.benchmark_tool = benchmark_tool or MarketBenchmarkTool()

    def _determine_merit_increase(self, rating: str, current_compa: Decimal) -> Decimal:
        """
        WorldatWork standard matrix: performance rating adjusted by compa-ratio.
        Lower compa-ratio gets an accelerated adjustment to reach midpoint.
        """
        base_rates = {
            "EXCEEDS": Decimal("0.10"),
            "MEETS_HIGH": Decimal("0.06"),
            "MEETS": Decimal("0.035"),
            "NEEDS_IMPROVEMENT": Decimal("0.00"),
        }
        rate = base_rates.get(rating, Decimal("0.03"))

        # Compa-ratio dampening / acceleration
        if current_compa < Decimal("0.85"):
            rate += Decimal("0.02")  # Acceleration to reduce pay compression
        elif current_compa > Decimal("1.15"):
            rate = max(Decimal("0.01"), rate - Decimal("0.02"))  # Dampening

        return rate

    def execute(self, state: MeshState) -> AgentResult:
        start_time = time.time()
        emp = state.employee

        # 1. Resolve market benchmark band
        loc_tier = (
            "BR_SP"
            if emp.jurisdiction.value == "BRAZIL"
            else ("CA_TORONTO" if emp.jurisdiction.value == "CANADA" else "US_NYC")
        )
        band = self.benchmark_tool.resolve(
            MarketBandInput(
                job_family="SOFTWARE_ENGINEERING",
                level=emp.level,
                location_tier=loc_tier,
            )
        )

        # 2. Determine merit percentage
        merit_pct = self._determine_merit_increase(emp.performance_rating, emp.compa_ratio)
        new_base = (emp.base_salary * (Decimal("1.0") + merit_pct)).quantize(Decimal("0.01"))
        new_compa = (new_base / band.band_mid).quantize(Decimal("0.0001"))

        # 3. Calculate Bonus: Base * Target% * IPF * CPF
        target_pct = Decimal("0.15") if emp.level in {"IC4", "IC5"} else Decimal("0.25")
        ipf_map = {
            "EXCEEDS": Decimal("1.25"),
            "MEETS_HIGH": Decimal("1.10"),
            "MEETS": Decimal("1.00"),
            "NEEDS_IMPROVEMENT": Decimal("0.50"),
        }
        ipf = ipf_map.get(emp.performance_rating, Decimal("1.00"))
        cpf = Decimal("1.05")  # Company performance factor
        bonus = (new_base * target_pct * ipf * cpf).quantize(Decimal("0.01"))

        proposal = CompensationProposal(
            current_base=emp.base_salary,
            proposed_base=new_base,
            percentage_increase=merit_pct,
            proposed_equity_shares=500
            if emp.performance_rating in {"EXCEEDS", "MEETS_HIGH"}
            else 0,
            bonus_target_pct=target_pct,
            individual_perf_factor=ipf,
            company_perf_factor=cpf,
            calculated_bonus=bonus,
            compa_ratio_after=new_compa,
            rationale=(
                f"Merit adjustment of {(merit_pct * 100):.1f}% applied based on '{emp.performance_rating}' rating "
                f"and initial compa-ratio of {emp.compa_ratio:.2f}. New compa-ratio is {new_compa:.2f} relative to midpoint {band.band_mid}."
            ),
        )

        updated_state = state.model_copy(
            update={
                "comp_proposal": proposal,
            }
        ).record_audit(
            actor=self.name,
            action="CALCULATE_COMPENSATION",
            details={"proposed_base": str(new_base), "merit_pct": str(merit_pct)},
        )

        duration = (time.time() - start_time) * 1000
        return AgentResult(
            agent_name=self.name,
            success=True,
            state=updated_state,
            rationale=proposal.rationale,
            tokens_consumed=420,
            duration_ms=duration,
        )
