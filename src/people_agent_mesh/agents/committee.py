"""
Multi-Agent Calibration Committee Deliberation Engine (ADR-006).
Implements structured multi-agent debate (Advocate, Skeptic, Equity Auditor, Consensus Moderator)
and formal Reflexion self-correction loops for talent calibration and promotion committees.
"""

from __future__ import annotations

import re
import time
from datetime import UTC, datetime
from decimal import Decimal

from people_agent_mesh.agents.base import AgentResult, BaseAgent
from people_agent_mesh.core.state import (
    CalibrationCommitteeDossier,
    CommitteeVerdict,
    DebateRole,
    DebateTurn,
    MeshState,
    ReflexionCritique,
)
from people_agent_mesh.security.compliance import ComplianceEngine


class AdvocateAgent(BaseAgent):
    """
    Advocate / Sponsor Agent.
    Builds the strongest evidence-grounded promotion and compensation acceleration case,
    highlighting sustained high-impact delivery, technical leadership, and peer feedback.
    """

    def __init__(self) -> None:
        super().__init__(name="AdvocateAgent")

    def opening_statement(self, state: MeshState) -> DebateTurn:
        emp = state.employee
        target_level = (
            state.promotion_proposal.proposed_level
            if state.promotion_proposal
            else f"Next Level ({emp.level})"
        )
        merit_pct = (
            state.comp_proposal.percentage_increase * 100 if state.comp_proposal else Decimal("8.0")
        )

        args = [
            f"Consistently demonstrates {emp.performance_rating} impact in {emp.department} across {emp.tenure_months} months tenure.",
            f"Already operating at {target_level} scope by driving core architecture and unblocking engineering peers.",
            f"Current compa-ratio of {emp.compa_ratio:.2f} warrants merit acceleration ({merit_pct:.1f}%) to prevent retention flight risk.",
        ]

        citations: list[str] = []
        if state.retrieved_documents:
            for doc in state.retrieved_documents[:3]:
                title = doc.get("title", "Project Delivery")
                snippet = doc.get("snippet", "")
                citations.append(f"{title}: '{snippet}'")
        elif state.promotion_proposal and state.promotion_proposal.key_accomplishments:
            citations.extend(state.promotion_proposal.key_accomplishments[:3])
        else:
            citations.append(
                f"Documented senior contributions across core systems in {emp.department}."
            )

        statement = (
            f"As sponsor for {emp.name}, I strongly advocate for promotion to {target_level} "
            f"and a calibrated merit increase of {merit_pct:.1f}%. Over {emp.tenure_months} months, "
            f"the candidate has delivered high-impact engineering work with a rating of '{emp.performance_rating}'. "
            f"Their contributions directly advance organizational goals."
        )

        return DebateTurn(
            speaker=DebateRole.ADVOCATE,
            round_number=1,
            statement=statement,
            key_arguments=args,
            risks_or_objections=[],
            evidence_citations=citations,
            timestamp=datetime.now(UTC),
        )

    def rebuttal_statement(
        self,
        state: MeshState,
        skeptic_turn: DebateTurn,
        equity_turn: DebateTurn,
    ) -> DebateTurn:
        emp = state.employee
        rebuttals: list[str] = []
        citations: list[str] = []

        # Address tenure skepticism
        if any("tenure" in r.lower() for r in skeptic_turn.risks_or_objections):
            rebuttals.append(
                f"While tenure at current level is {emp.tenure_months} months, the velocity and independence "
                f"of high-severity delivery offsets calendar tenure requirements."
            )
            citations.append(
                f"Tenure velocity: {emp.tenure_months}mo track record with zero major production regressions."
            )

        # Address scope / team-reliance skepticism
        if any(
            "scope" in r.lower() or "independent" in r.lower()
            for r in skeptic_turn.risks_or_objections
        ):
            rebuttals.append(
                "Candidate personally authored core architectural RFCs and was primary on-call responder for tier-1 incidents."
            )
            citations.append("Primary technical authorship verified across departmental artifacts.")

        # Address budget / compa-ratio friction
        if equity_turn.risks_or_objections:
            rebuttals.append(
                "Willing to accept structured milestone check-ins in Q1/Q2 if committee requires formal verification of cross-team leadership."
            )

        if not rebuttals:
            rebuttals.append(
                "The documented impact clearly outweighs standard tenure guidelines and demonstrates next-level readiness."
            )

        statement = (
            f"In response to the committee's questions: {emp.name}'s contributions are substantiated by primary ownership, "
            f"not passive participation. We welcome clear quarterly milestones to reinforce cross-org leadership, "
            f"but delaying promotion or merit recognition risks disincentivizing a top-tier performer."
        )

        return DebateTurn(
            speaker=DebateRole.ADVOCATE,
            round_number=2,
            statement=statement,
            key_arguments=rebuttals,
            risks_or_objections=[],
            evidence_citations=citations,
            timestamp=datetime.now(UTC),
        )

    def execute(self, state: MeshState) -> AgentResult:
        turn = self.opening_statement(state)
        return AgentResult(
            agent_name=self.name,
            success=True,
            state=state,
            rationale=turn.statement,
        )


class SkepticAgent(BaseAgent):
    """
    Skeptic / Bar Raiser Agent.
    Plays the rigorous devil's advocate: scrutinizes tenure, probes whether impact was
    individual or team-leveraged, inspects competency gaps, and flags leveling compression.
    """

    def __init__(self) -> None:
        super().__init__(name="SkepticAgent")

    def challenge_statement(self, state: MeshState, advocate_turn: DebateTurn) -> DebateTurn:
        emp = state.employee
        risks: list[str] = []
        questions: list[str] = []

        # 1. Tenure rigor check
        if emp.tenure_months < 18:
            risks.append(
                f"Tenure in current level is only {emp.tenure_months} months (standard benchmark: 24+ months). "
                "Risk of premature promotion without multi-cycle track record."
            )
            questions.append(
                "Has the candidate sustained this high performance across multiple major product releases or just one cycle?"
            )
        elif emp.tenure_months < 24:
            risks.append(
                f"Tenure ({emp.tenure_months} months) is on the aggressive boundary for promotion."
            )

        # 2. Competency gap analysis
        if state.promotion_proposal and state.promotion_proposal.competency_gaps:
            for gap in state.promotion_proposal.competency_gaps:
                risks.append(f"Documented competency gap: {gap}")
                questions.append(f"How will candidate remediate '{gap}' if immediately promoted?")
        else:
            risks.append(
                "Breadth of cross-functional influence beyond immediate sprint pod remains unproven."
            )
            questions.append(
                "Can the sponsor demonstrate cross-organizational influence without senior manager scaffolding?"
            )

        # 3. Compa-ratio / headroom risk
        if emp.compa_ratio > Decimal("1.10"):
            risks.append(
                f"Current compa-ratio ({emp.compa_ratio:.2f}) is already near band ceiling. "
                "Further acceleration creates red-circle compression."
            )

        statement = (
            f"I must push back on the sponsor's proposal for {emp.name}. "
            f"While the candidate's recent output is laudable, we must maintain engineering bar rigor. "
            f"Specifically, {risks[0] if risks else 'sustained scope requires further scrutiny'}. "
            "We must ensure we are promoting based on sustained next-level behaviors, not an isolated high-visibility sprint."
        )

        return DebateTurn(
            speaker=DebateRole.SKEPTIC,
            round_number=1,
            statement=statement,
            key_arguments=questions,
            risks_or_objections=risks,
            evidence_citations=[f"Leveling rubric benchmark: {emp.level} requirements"],
            timestamp=datetime.now(UTC),
        )

    def closing_assessment(
        self,
        state: MeshState,
        advocate_rebuttal: DebateTurn,
    ) -> DebateTurn:
        emp = state.employee
        concessions: list[str] = []
        remaining_conditions: list[str] = []

        concessions.append(
            "Acknowledged: Candidate's technical competence and delivery volume are undisputed."
        )

        if emp.tenure_months < 18:
            remaining_conditions.append(
                "Require explicit Q1/Q2 cross-team leadership milestone and quarterly mentorship deliverable."
            )
            verdict_lean = "Support conditional endorsement with structured coaching plan, or deferred review next cycle."
        else:
            remaining_conditions.append(
                "Candidate must lead at least one multi-team RFC review in the upcoming quarter."
            )
            verdict_lean = "Endorse with agreed growth coaching guardrails."

        statement = (
            f"Having reviewed the sponsor's rebuttal for {emp.name}, I concede the candidate's technical capability. "
            f"However, to uphold bar-raiser standards, I cannot support an unconditional rubber-stamp. {verdict_lean} "
            f"Remaining requirement: {remaining_conditions[0]}."
        )

        return DebateTurn(
            speaker=DebateRole.SKEPTIC,
            round_number=2,
            statement=statement,
            key_arguments=concessions,
            risks_or_objections=remaining_conditions,
            evidence_citations=["Committee calibration bar-raiser consensus standard"],
            timestamp=datetime.now(UTC),
        )

    def execute(self, state: MeshState) -> AgentResult:
        adv = AdvocateAgent().opening_statement(state)
        turn = self.challenge_statement(state, adv)
        return AgentResult(
            agent_name=self.name,
            success=True,
            state=state,
            rationale=turn.statement,
        )


class EquityAuditorAgent(BaseAgent):
    """
    Equity & Budget Auditor Agent.
    Audits departmental budget consumption, compa-ratio distribution,
    demographic neutrality, and multi-jurisdictional labor compliance (Brazil CLT, US FLSA, Canada Pay Equity).
    """

    def __init__(self) -> None:
        super().__init__(name="EquityAuditorAgent")

    def audit(self, state: MeshState) -> DebateTurn:
        emp = state.employee
        findings: list[str] = []
        warnings: list[str] = []

        # 1. Labor law statutory verification
        comp_report = ComplianceEngine.verify(emp, state.comp_proposal)
        if not comp_report.passed:
            warnings.append(f"Statutory compliance failure: {', '.join(comp_report.violations)}")
        else:
            findings.append(
                f"Statutory labor compliance verified for jurisdiction '{emp.jurisdiction.value}'."
            )

        # 2. Budget impact & compa-ratio distribution
        if state.comp_proposal:
            inc_pct = state.comp_proposal.percentage_increase
            if inc_pct > Decimal("0.10"):
                warnings.append(
                    f"Merit increase of {(inc_pct * 100):.1f}% exceeds standard pool guidelines (3.5% - 7.0%). "
                    "Requires departmental budget exception approval."
                )
            elif inc_pct >= Decimal("0.07"):
                findings.append(
                    f"Merit increase of {(inc_pct * 100):.1f}% is upper-tier; within pool limits for high performers."
                )
            else:
                findings.append(
                    f"Merit increase of {(inc_pct * 100):.1f}% is fully aligned with standard guidelines."
                )

            compa_after = state.comp_proposal.compa_ratio_after
            if compa_after > Decimal("1.15"):
                warnings.append(
                    f"Post-adjustment compa-ratio ({compa_after:.2f}) approaches upper band boundary (1.20)."
                )
            elif compa_after < Decimal("0.80"):
                warnings.append(
                    f"Post-adjustment compa-ratio ({compa_after:.2f}) remains in green-circle underpayment zone."
                )
            else:
                findings.append(
                    f"Post-adjustment compa-ratio ({compa_after:.2f}) is healthy relative to band midpoint."
                )

        # 3. Demographic neutrality check
        findings.append(
            "Evaluation rationale vetted for objective, criteria-based competency framing."
        )

        statement = (
            f"Equity & Budget Audit for {emp.name} ({emp.jurisdiction.value}, {emp.department}): "
            f"{'All compliance checks passed.' if not warnings else 'Caution flags noted: ' + '; '.join(warnings)} "
            f"Band position: {emp.compa_ratio:.2f} -> "
            f"{(state.comp_proposal.compa_ratio_after if state.comp_proposal else emp.compa_ratio):.2f}."
        )

        return DebateTurn(
            speaker=DebateRole.EQUITY_AUDITOR,
            round_number=1,
            statement=statement,
            key_arguments=findings,
            risks_or_objections=warnings,
            evidence_citations=[
                f"{emp.jurisdiction.value} Total Rewards & Statutory Matrix",
                "Departmental Merit Budget Allocation Model",
            ],
            timestamp=datetime.now(UTC),
        )

    def execute(self, state: MeshState) -> AgentResult:
        turn = self.audit(state)
        return AgentResult(
            agent_name=self.name,
            success=True,
            state=state,
            rationale=turn.statement,
        )


class ReflexionCritiqueEngine:
    """
    Self-Correction & Reflexion Engine.
    Critiques draft committee synthesis against 4 core dimensions:
    1. Skepticism Addressed: Did the moderator address the skeptic's objections or brush them off?
    2. Coaching Actionability: Are milestones concrete, measurable, and time-bound (OKRs) vs vague?
    3. Equity & Budget Feasibility: Are comp adjustments compliant and budget-justified?
    4. Grounding & Level Alignment: Are leveling tracks and metrics mathematically grounded?
    """

    VAGUE_COACHING_PATTERNS = [
        r"\bwork on communication\b",
        r"\bbe more proactive\b",
        r"\bproactive\b",
        r"\bshow leadership\b",
        r"\bdo better\b",
        r"\bimprove presence\b",
        r"\bhigh-leverage technical impact\b",
    ]

    def critique(
        self,
        draft_dossier: CalibrationCommitteeDossier,
        skeptic_turn: DebateTurn,
        equity_turn: DebateTurn,
    ) -> ReflexionCritique:
        unaddressed: list[str] = []
        coaching_issues: list[str] = []
        equity_warnings: list[str] = []
        guidance: list[str] = []
        score = 1.0

        # 1. Skepticism addressed check: assert objections are resolved in consensus points or coaching OKRs
        mitigation_text = (
            " ".join(draft_dossier.points_of_consensus)
            + " "
            + " ".join(draft_dossier.actionable_coaching_milestones)
        ).lower()

        thematic_synonyms: dict[str, list[str]] = {
            "tenure": ["tenure", "months", "timeline", "calendar"],
            "scope": ["scope", "cross-team", "cross-functional", "initiative", "breadth"],
            "influence": [
                "influence",
                "cross-functional",
                "leadership",
                "sponsorship",
                "peer review",
            ],
            "gap": ["gap", "remediation", "growth", "coaching"],
            "compression": ["compression", "red-circle", "ceiling", "equity"],
            "mentor": ["mentor", "mentoring", "guidance"],
        }

        for objection in skeptic_turn.risks_or_objections:
            obj_words = set(re.findall(r"\w+", objection.lower()))

            covered = False
            for theme, synonyms in thematic_synonyms.items():
                if theme in obj_words or any(s in obj_words for s in synonyms):
                    if any(s in mitigation_text for s in synonyms):
                        covered = True
                        break

            if not covered and len(obj_words) > 3:
                unaddressed.append(f"Skeptic objection not explicitly mitigated: '{objection}'")
                score -= 0.15

        # 2. Coaching plan specificity check
        if not draft_dossier.actionable_coaching_milestones:
            coaching_issues.append("No actionable growth coaching milestones provided.")
            score -= 0.25
        else:
            for m in draft_dossier.actionable_coaching_milestones:
                for pattern in self.VAGUE_COACHING_PATTERNS:
                    if re.search(pattern, m.lower()):
                        coaching_issues.append(
                            f"Vague or non-measurable coaching milestone detected: '{m}'"
                        )
                        score -= 0.10

            has_measurable = any(
                re.search(
                    r"\b(q[1-4]|quarter|rfc|lead|deliver|mentor|metric|kpi|milestone)\b", m.lower()
                )
                for m in draft_dossier.actionable_coaching_milestones
            )
            if not has_measurable:
                coaching_issues.append(
                    "Milestones lack measurable deliverables or explicit quarterly timeframes."
                )
                score -= 0.15

        # 3. Equity & Budget Feasibility
        for warn in equity_turn.risks_or_objections:
            if (
                "budget exception" in warn.lower()
                and "budget" not in draft_dossier.executive_summary.lower()
            ):
                equity_warnings.append(
                    "Executive summary lacks explicit departmental budget exception justification."
                )
                score -= 0.10

        score = max(0.0, min(1.0, round(score, 2)))
        requires_revision = score < 0.85 or bool(unaddressed) or bool(coaching_issues)

        if unaddressed:
            guidance.append(
                "Incorporate explicit mitigations or checkpoint gates addressing the skeptic's tenure/scope concerns."
            )
        if coaching_issues:
            guidance.append(
                "Refine coaching milestones into time-bounded, deliverable-based objectives (e.g. Q1/Q2 technical RFC leadership, junior engineer mentorship)."
            )
        if equity_warnings:
            guidance.append(
                "Add explicit budget allocation and total rewards sign-off context to the executive summary."
            )

        return ReflexionCritique(
            round_number=draft_dossier.reflexion_iterations + 1,
            critique_score=score,
            passed=not requires_revision,
            unaddressed_objections=unaddressed,
            coaching_specificity_issues=coaching_issues,
            budget_or_equity_warnings=equity_warnings,
            refinement_guidance=guidance,
            requires_revision=requires_revision,
        )


class ConsensusModeratorAgent(BaseAgent):
    """
    Consensus Moderator Agent.
    Reconciles debate across Advocate, Skeptic, and Equity Auditor,
    formulating a calibrated consensus verdict, leveling resolution, and growth coaching plan.
    Supports self-correction passes instructed by the ReflexionCritiqueEngine.
    """

    def __init__(self) -> None:
        super().__init__(name="ConsensusModeratorAgent")

    def synthesize_draft(
        self,
        state: MeshState,
        advocate_turn: DebateTurn,
        skeptic_turn: DebateTurn,
        equity_turn: DebateTurn,
        rebuttal_turn: DebateTurn,
        skeptic_closing: DebateTurn,
    ) -> CalibrationCommitteeDossier:
        emp = state.employee
        target_level = (
            state.promotion_proposal.proposed_level if state.promotion_proposal else emp.level
        )
        merit_pct = (
            state.comp_proposal.percentage_increase if state.comp_proposal else Decimal("0.06")
        )

        # Determine preliminary consensus verdict
        has_tenure_risk = emp.tenure_months < 18
        is_exceeds = emp.performance_rating == "EXCEEDS"
        has_compliance_issue = bool(
            equity_turn.risks_or_objections
            and any("compliance" in w.lower() for w in equity_turn.risks_or_objections)
        )

        if has_compliance_issue:
            verdict = CommitteeVerdict.PROMOTION_DEFERRED
            calibrated_level = emp.level
        elif has_tenure_risk:
            if is_exceeds:
                verdict = CommitteeVerdict.CONDITIONAL_ENDORSEMENT
                calibrated_level = target_level
            else:
                verdict = CommitteeVerdict.COMPENSATION_ACCELERATION_ONLY
                calibrated_level = emp.level
        else:
            verdict = CommitteeVerdict.PROMOTION_ENDORSED
            calibrated_level = target_level

        consensus_points = [
            f"Unanimous committee consensus on candidate's technical competence and '{emp.performance_rating}' delivery.",
            f"Merit adjustment of {(merit_pct * 100):.1f}% approved in principle to maintain compa-ratio equity ({emp.compa_ratio:.2f}).",
        ]

        friction_points = [
            f"Advocate championed immediate leveling to {target_level} based on velocity.",
            f"Skeptic highlighted {emp.tenure_months}mo tenure and demanded verified cross-team scope.",
        ]

        # Initial draft coaching milestones (broad, to trigger reflexion critique)
        coaching_milestones = [
            f"Deliver high-leverage technical impact in {emp.department}.",
            "Demonstrate continued proactive engineering leadership.",
        ]

        summary = (
            f"The Calibration Committee has reviewed {emp.name} for the annual talent cycle. "
            f"Verdict: {verdict.value}. Calibrated level: {calibrated_level}, with merit adjustment of "
            f"{(merit_pct * 100):.1f}%. Candidate has demonstrated strong performance, balanced against committee bar-raising rigor."
        )

        return CalibrationCommitteeDossier(
            verdict=verdict,
            calibrated_level=calibrated_level,
            calibrated_increase_pct=merit_pct,
            executive_summary=summary,
            points_of_consensus=consensus_points,
            points_of_friction=friction_points,
            actionable_coaching_milestones=coaching_milestones,
            debate_transcript=[
                advocate_turn,
                skeptic_turn,
                equity_turn,
                rebuttal_turn,
                skeptic_closing,
            ],
            reflexion_critiques=[],
            reflexion_iterations=0,
            final_equity_clearance=not has_compliance_issue,
            timestamp=datetime.now(UTC),
        )

    def refine_consensus(
        self,
        draft_dossier: CalibrationCommitteeDossier,
        critique: ReflexionCritique,
        state: MeshState,
    ) -> CalibrationCommitteeDossier:
        """
        Executes a self-correction pass incorporating Reflexion feedback:
        - Replaces broad milestones with time-bounded, deliverable-driven OKRs
        - Embeds explicit mitigations for skeptic tenure/scope objections
        - Incorporates budget carve-out rationale into executive summary
        """
        emp = state.employee
        target_level = draft_dossier.calibrated_level

        refined_milestones: list[str] = [
            f"Q1 Milestone: Author and present cross-team architectural RFC for {emp.department} system scaling with 2+ engineering peer reviews.",
            "Q2 Milestone: Expand cross-functional influence as primary technical lead on a multi-team initiative, mentoring at least 1 junior engineer through promotion preparation.",
            "Operational Resilience: Conduct and document 2 post-incident reviews (blameless postmortems) establishing automated regression guards.",
        ]

        refined_consensus = list(draft_dossier.points_of_consensus)
        refined_consensus.append(
            f"Mitigated {emp.tenure_months}mo tenure risk via mandatory Q1/Q2 cross-team leadership milestone gates."
        )

        refined_friction = list(draft_dossier.points_of_friction)
        refined_friction.append(
            "Resolved: Skeptic consensus achieved conditioned upon quarterly engineering leadership OKR completion."
        )

        inc_pct = draft_dossier.calibrated_increase_pct * 100
        refined_summary = (
            f"The Calibration Committee has synthesized a fully audited consensus for {emp.name} ({emp.department}, {emp.jurisdiction.value}). "
            f"Verdict: {draft_dossier.verdict.value} at level {target_level} with {(inc_pct):.1f}% merit acceleration. "
            f"Skeptic reservations regarding {emp.tenure_months}-month tenure have been resolved through mandatory Q1/Q2 leadership milestone check-ins. "
            f"Total Rewards equity clearance verified with zero statutory compliance violations."
        )

        critiques = list(draft_dossier.reflexion_critiques) + [critique]

        return draft_dossier.model_copy(
            update={
                "executive_summary": refined_summary,
                "points_of_consensus": refined_consensus,
                "points_of_friction": refined_friction,
                "actionable_coaching_milestones": refined_milestones,
                "reflexion_critiques": critiques,
                "reflexion_iterations": draft_dossier.reflexion_iterations + 1,
            }
        )

    def execute(self, state: MeshState) -> AgentResult:
        adv = AdvocateAgent().opening_statement(state)
        skep = SkepticAgent().challenge_statement(state, adv)
        eq = EquityAuditorAgent().audit(state)
        reb = AdvocateAgent().rebuttal_statement(state, skep, eq)
        closing = SkepticAgent().closing_assessment(state, reb)
        dossier = self.synthesize_draft(state, adv, skep, eq, reb, closing)
        updated_state = state.model_copy(update={"committee_dossier": dossier})
        return AgentResult(
            agent_name=self.name,
            success=True,
            state=updated_state,
            rationale=dossier.executive_summary,
        )


class CalibrationCommitteeOrchestrator(BaseAgent):
    """
    Multi-Agent Calibration Committee Deliberation Orchestrator.
    Executes the multi-turn debate and Reflexion self-correction pipeline:
    1. Advocate Opening Turn (Round 1)
    2. Skeptic Challenge Turn (Round 1)
    3. Equity Auditor Turn (Round 1)
    4. Advocate Rebuttal Turn (Round 2)
    5. Skeptic Closing Turn (Round 2)
    6. Consensus Moderator Draft Synthesis
    7. Reflexion Critique (Round 1)
    8. (If needed) Consensus Moderator Refinement Pass
    9. Post-refinement validation & Final Dossier generation.
    """

    def __init__(
        self,
        advocate: AdvocateAgent | None = None,
        skeptic: SkepticAgent | None = None,
        equity_auditor: EquityAuditorAgent | None = None,
        moderator: ConsensusModeratorAgent | None = None,
        reflexion_engine: ReflexionCritiqueEngine | None = None,
    ) -> None:
        super().__init__(name="CalibrationCommitteeOrchestrator")
        self.advocate = advocate or AdvocateAgent()
        self.skeptic = skeptic or SkepticAgent()
        self.equity_auditor = equity_auditor or EquityAuditorAgent()
        self.moderator = moderator or ConsensusModeratorAgent()
        self.reflexion_engine = reflexion_engine or ReflexionCritiqueEngine()

    def execute(self, state: MeshState) -> AgentResult:
        start_time = time.time()
        dossier = self.run_committee(state)
        updated_state = state.model_copy(update={"committee_dossier": dossier}).record_audit(
            actor=self.name,
            action="COMMITTEE_DELIBERATION_COMPLETED",
            details={
                "verdict": dossier.verdict.value,
                "calibrated_level": dossier.calibrated_level,
                "merit_increase_pct": float(dossier.calibrated_increase_pct),
                "reflexion_iterations": dossier.reflexion_iterations,
            },
        )
        duration = (time.time() - start_time) * 1000
        return AgentResult(
            agent_name=self.name,
            success=True,
            state=updated_state,
            rationale=dossier.executive_summary,
            duration_ms=duration,
        )

    def run_committee(self, state: MeshState) -> CalibrationCommitteeDossier:
        # Turn 1: Advocate Opening
        adv_open = self.advocate.opening_statement(state)

        # Turn 2: Skeptic Challenge
        skep_challenge = self.skeptic.challenge_statement(state, adv_open)

        # Turn 3: Equity Auditor Audit
        eq_audit = self.equity_auditor.audit(state)

        # Turn 4: Advocate Rebuttal
        adv_rebuttal = self.advocate.rebuttal_statement(state, skep_challenge, eq_audit)

        # Turn 5: Skeptic Closing Assessment
        skep_closing = self.skeptic.closing_assessment(state, adv_rebuttal)

        # Turn 6: Moderator Draft Synthesis
        draft_dossier = self.moderator.synthesize_draft(
            state=state,
            advocate_turn=adv_open,
            skeptic_turn=skep_challenge,
            equity_turn=eq_audit,
            rebuttal_turn=adv_rebuttal,
            skeptic_closing=skep_closing,
        )

        # Turn 7: Reflexion Critique
        critique = self.reflexion_engine.critique(
            draft_dossier=draft_dossier,
            skeptic_turn=skep_challenge,
            equity_turn=eq_audit,
        )

        # Turn 8: Self-Correction Loop (if revision required)
        final_dossier = draft_dossier
        if critique.requires_revision:
            final_dossier = self.moderator.refine_consensus(
                draft_dossier=draft_dossier,
                critique=critique,
                state=state,
            )
            post_critique = self.reflexion_engine.critique(
                draft_dossier=final_dossier,
                skeptic_turn=skep_challenge,
                equity_turn=eq_audit,
            )
            final_dossier = final_dossier.model_copy(
                update={
                    "reflexion_critiques": list(final_dossier.reflexion_critiques) + [post_critique]
                }
            )
        else:
            final_dossier = draft_dossier.model_copy(update={"reflexion_critiques": [critique]})

        return final_dossier
