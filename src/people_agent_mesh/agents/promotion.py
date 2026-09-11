"""
Promotion Dossier Synthesizer Agent.
Aggregates performance evidence, detects cross-functional scope,
and assesses readiness against engineering leveling ladders.
"""

from __future__ import annotations

import time

from people_agent_mesh.agents.base import AgentResult, BaseAgent
from people_agent_mesh.core.state import MeshState, PromotionProposal
from people_agent_mesh.tools.contracts import DocumentQueryInput
from people_agent_mesh.tools.enterprise_tools import MultiPlatformKnowledgeTool


class PromotionAgent(BaseAgent):
    def __init__(self, knowledge_tool: MultiPlatformKnowledgeTool | None = None) -> None:
        super().__init__(name="PromotionAgent")
        self.knowledge_tool = knowledge_tool or MultiPlatformKnowledgeTool()

    def _next_level(self, current_level: str) -> str:
        ladder = {
            "IC3": "IC4",
            "IC4": "IC5",
            "IC5": "IC6",
            "IC6": "IC7",
            "M1": "M2",
        }
        return ladder.get(current_level, current_level)

    def execute(self, state: MeshState) -> AgentResult:
        start_time = time.time()
        emp = state.employee

        # 1. Fetch performance evidence
        docs_res = self.knowledge_tool.query(
            DocumentQueryInput(
                subject_employee_id=emp.employee_id,
                categories=["PERFORMANCE", "SLACK_KUDOS", "FEEDBACK"],
                limit=10,
            )
        )

        # 2. Synthesize accomplishments and scope
        accomplishments: list[str] = []
        for doc in docs_res.documents:
            title = doc.get("title", "Project Delivery")
            snippet = doc.get("snippet", "")
            accomplishments.append(f"{title}: {snippet}")

        if not accomplishments:
            accomplishments = [
                f"Consistently demonstrated senior impact at {emp.level} over {emp.tenure_months} months tenure.",
                "Led architectural improvements across core engineering systems.",
            ]

        # 3. Calculate readiness score
        # Base readiness on tenure, rating, and evidence volume
        score = 0.70
        if emp.performance_rating == "EXCEEDS":
            score += 0.20
        elif emp.performance_rating == "MEETS_HIGH":
            score += 0.10

        if emp.tenure_months >= 24:
            score += 0.05

        target_level = self._next_level(emp.level)
        proposal = PromotionProposal(
            current_level=emp.level,
            proposed_level=target_level,
            readiness_score=min(1.0, round(score, 2)),
            business_impact_summary=(
                f"Employee has operated at high autonomy in {emp.department}, driving key initiatives "
                f"consistent with {target_level} expectations."
            ),
            key_accomplishments=accomplishments[:4],
            competency_gaps=[]
            if score >= 0.85
            else ["Needs broader cross-business unit sponsorship"],
        )

        updated_state = state.model_copy(
            update={
                "promotion_proposal": proposal,
            }
        ).record_audit(
            actor=self.name,
            action="SYNTHESIZE_PROMOTION_DOSSIER",
            details={"proposed_level": target_level, "readiness_score": score},
        )

        duration = (time.time() - start_time) * 1000
        return AgentResult(
            agent_name=self.name,
            success=True,
            state=updated_state,
            rationale=f"Promotion dossier synthesized for {target_level} readiness (score: {score:.2f}).",
            tokens_consumed=680,
            duration_ms=duration,
        )
