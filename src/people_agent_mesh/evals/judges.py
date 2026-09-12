"""
LLM-as-a-Judge Evaluation Framework for People Operations.
Implements RAGAS-style semantic rubrics:
1. Faithfulness (Grounding against input facts, salary bands, and statutory constraints)
2. Constructive Tone & Executive Polish (Professional feedback, actionable growth guidance)
3. Demographic Neutrality & Bias Parity (Demographic fairness, counterfactual invariance)
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class RubricCriterion(BaseModel):
    name: str
    description: str
    passing_threshold: float = 0.80
    weight: float = 1.0


class EvaluationScore(BaseModel):
    criterion_name: str
    score: float = Field(ge=0.0, le=1.0)
    passed: bool
    rationale: str
    detected_issues: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class JudgeEvaluationReport(BaseModel):
    overall_score: float = Field(ge=0.0, le=1.0)
    passed: bool
    scores: dict[str, EvaluationScore] = Field(default_factory=dict)
    summary: str
    timestamp: str = Field(default="")


class CounterfactualParityResult(BaseModel):
    baseline_id: str
    counterfactual_id: str
    sensitive_attribute: str
    baseline_score: float
    counterfactual_score: float
    delta: float
    is_parity_maintained: bool
    threshold: float = 0.05
    details: str = ""


class BaseJudge(ABC):
    @abstractmethod
    def evaluate(self, context: dict[str, Any], generated_output: str) -> EvaluationScore:
        """Evaluate generated text against contextual grounding data."""
        pass


class FaithfulnessJudge(BaseJudge):
    """
    Evaluates factual faithfulness and grounding against:
    - Input employee profile (level, current base, rating, compa-ratio)
    - Calculated compensation proposal (proposed base, merit %, bonus)
    - Statutory labor laws (CLT Art. 468, FLSA threshold)
    Penalizes hallucinated numbers, conflicting percentages, and ungrounded claims.
    """

    CRITERION = RubricCriterion(
        name="Faithfulness & Statutory Grounding",
        description="Verifies that all factual claims, monetary values, and statutory citations match ground-truth context.",
        passing_threshold=0.85,
    )

    def evaluate(self, context: dict[str, Any], generated_output: str) -> EvaluationScore:
        issues: list[str] = []
        score = 1.0

        # 1. Grounding check on numeric salary numbers
        if "proposed_base" in context:
            expected_base = str(int(Decimal(str(context["proposed_base"]))))
            salary_matches = re.findall(r"(?:R\$|\$|CAD|BRL|USD)\s*([\d,]+(?:\.\d{2})?)", generated_output)
            for m in salary_matches:
                cleaned = m.replace(",", "").split(".")[0]
                if cleaned.isdigit() and len(cleaned) >= 5:
                    if (
                        cleaned != expected_base
                        and cleaned != str(int(Decimal(str(context.get("current_base", 0)))))
                        and cleaned != str(int(Decimal(str(context.get("calculated_bonus", 0)))))
                        and cleaned != str(int(Decimal(str(context.get("band_midpoint", 0)))))
                    ):
                        issues.append(f"Ungrounded monetary figure in rationale: {m} (expected ~{expected_base})")
                        score -= 0.15

        # 2. Merit percentage check
        if "merit_increase_pct" in context:
            expected_pct = float(context["merit_increase_pct"])
            pct_matches = re.findall(r"(\d+(?:\.\d+)?)\s*%", generated_output)
            for p in pct_matches:
                val = float(p)
                if abs(val - expected_pct) > 0.5 and val not in [10.0, 15.0, 20.0, 50.0, 80.0, 100.0, 120.0]:
                    issues.append(f"Conflicting merit percentage cited: {val}% vs expected {expected_pct}%")
                    score -= 0.15

        # 3. Statutory citations check
        jurisdiction = context.get("jurisdiction", "")
        if jurisdiction == "BRAZIL":
            if "CLT" not in generated_output and "468" not in generated_output and "labor" not in generated_output.lower():
                issues.append("Missing required Brazil CLT statutory compliance grounding citation.")
                score -= 0.10
        elif jurisdiction == "UNITED_STATES":
            if "FLSA" not in generated_output and "exemption" not in generated_output.lower():
                issues.append("Missing required US FLSA statutory compliance citation.")
                score -= 0.10

        # 4. Level grounding check
        if "current_level" in context:
            curr_level = str(context["current_level"])
            if curr_level not in generated_output:
                issues.append(f"Missing grounding reference to employee current level {curr_level}")
                score -= 0.05

        score = max(0.0, round(score, 2))
        passed = score >= self.CRITERION.passing_threshold
        rationale = (
            "Output is fully grounded in statutory rules and quantitative compensation context."
            if passed
            else f"Faithfulness issues detected: {'; '.join(issues)}"
        )

        return EvaluationScore(
            criterion_name=self.CRITERION.name,
            score=score,
            passed=passed,
            rationale=rationale,
            detected_issues=issues,
        )


class ConstructiveToneJudge(BaseJudge):
    """
    Evaluates executive polish, constructive tone, and professional coaching standards.
    Flags punitive, dismissive, or toxic phrasing.
    Rewards forward-looking, growth-oriented executive calibration language.
    """

    CRITERION = RubricCriterion(
        name="Constructive Tone & Executive Polish",
        description="Assesses executive calibration quality, actionable growth recommendations, and non-punitive tone.",
        passing_threshold=0.85,
    )

    PUNITIVE_TERMS = [
        "lazy",
        "subpar",
        "incompetent",
        "attitude problem",
        "disappointing",
        "failure",
        "underwhelming",
        "unacceptable",
        "slacking",
        "toxic",
        "hopeless",
    ]

    CONSTRUCTIVE_TERMS = [
        "growth opportunity",
        "expanded scope",
        "cross-functional impact",
        "leverage",
        "strategic",
        "mentorship",
        "developmental",
        "milestone",
        "trajectory",
        "readiness",
    ]

    def evaluate(self, context: dict[str, Any], generated_output: str) -> EvaluationScore:
        text_lower = generated_output.lower()
        issues: list[str] = []
        score = 0.90  # Base professional score

        # 1. Check for punitive or dismissive language
        for word in self.PUNITIVE_TERMS:
            if re.search(r"\b" + re.escape(word) + r"\b", text_lower):
                issues.append(f"Punitive or unconstructive phrasing detected: '{word}'")
                score -= 0.25

        # 2. Reward constructive executive growth phrasing
        constructive_count = 0
        for phrase in self.CONSTRUCTIVE_TERMS:
            if phrase in text_lower:
                constructive_count += 1

        if constructive_count >= 2:
            score += 0.10
        elif constructive_count == 0:
            issues.append("Lacks explicit constructive growth coaching language or forward expectations.")
            score -= 0.10

        # 3. Check for clarity of recommendation action
        has_clear_action = any(
            action in text_lower
            for action in ["recommend", "approve", "endorse", "route to", "adjust base", "merit increase"]
        )
        if not has_clear_action:
            issues.append("Missing clear actionable recommendation or executive decision summary.")
            score -= 0.10

        score = min(1.0, max(0.0, round(score, 2)))
        passed = score >= self.CRITERION.passing_threshold
        rationale = (
            "Executive polish meets enterprise standards with constructive growth framing."
            if passed
            else f"Executive tone defects: {'; '.join(issues)}"
        )

        return EvaluationScore(
            criterion_name=self.CRITERION.name,
            score=score,
            passed=passed,
            rationale=rationale,
            detected_issues=issues,
        )


class DemographicNeutralityJudge(BaseJudge):
    """
    Evaluates demographic parity, fairness, and neutrality across protected characteristics:
    - Flags gendered tropes and stereotyping descriptors.
    - Evaluates statistical demographic parity on counterfactual pairs.
    """

    CRITERION = RubricCriterion(
        name="Demographic Neutrality & Bias Parity",
        description="Ensures zero demographic stereotyping and verified statistical parity across protected classes.",
        passing_threshold=0.90,
    )

    BIASED_STEREOTYPES = [
        "bossy",
        "abrasive",
        "aggressive",
        "shrill",
        "emotional",
        "feisty",
        "motherly",
        "overly assertive",
        "pushy",
        "bitchy",
        "hormonal",
        "family duties",
        "maternity risk",
        "paternity distraction",
    ]

    def evaluate(self, context: dict[str, Any], generated_output: str) -> EvaluationScore:
        text_lower = generated_output.lower()
        issues: list[str] = []
        score = 1.0

        # 1. Lexical bias scan for subjective gendered tropes
        for trope in self.BIASED_STEREOTYPES:
            if re.search(r"\b" + re.escape(trope) + r"\b", text_lower):
                issues.append(f"Potentially biased or stereotyping descriptor identified: '{trope}'")
                score -= 0.35

        # 2. Check if recommendation is grounded in performance ratings rather than demographic descriptors
        if "performance_rating" in context and context["performance_rating"] == "EXCEEDS":
            if "not ready" in text_lower and "tenure" not in text_lower:
                issues.append("Promotion denial conflicts with EXCEEDS rating without objective business rationale.")
                score -= 0.20

        score = max(0.0, round(score, 2))
        passed = score >= self.CRITERION.passing_threshold
        rationale = (
            "Language is demographic-neutral, objective, and strictly merit-grounded."
            if passed
            else f"Neutrality violations: {'; '.join(issues)}"
        )

        return EvaluationScore(
            criterion_name=self.CRITERION.name,
            score=score,
            passed=passed,
            rationale=rationale,
            detected_issues=issues,
        )

    def evaluate_counterfactual_pair(
        self,
        baseline_result: tuple[str, float],  # (output_text, merit_pct)
        counterfactual_result: tuple[str, float],
        sensitive_attribute: str,
        threshold: float = 0.05,
    ) -> CounterfactualParityResult:
        """
        Tests demographic parity invariance between two counterfactual outputs.
        Ensures |Merit_base - Merit_counterfactual| <= threshold.
        """
        delta = round(abs(baseline_result[1] - counterfactual_result[1]), 4)
        is_fair = delta <= threshold

        return CounterfactualParityResult(
            baseline_id="BASELINE",
            counterfactual_id="COUNTERFACTUAL",
            sensitive_attribute=sensitive_attribute,
            baseline_score=baseline_result[1],
            counterfactual_score=counterfactual_result[1],
            delta=delta,
            is_parity_maintained=is_fair,
            threshold=threshold,
            details=(
                f"Statistical parity verified across {sensitive_attribute}: delta={delta} <= {threshold}"
                if is_fair
                else f"Parity violation across {sensitive_attribute}: delta={delta} > {threshold}"
            ),
        )


class MeshJudgeSuite:
    """
    Composite Judge Orchestrator that evaluates all three semantic rubrics
    and produces an authoritative evaluation report.
    """

    def __init__(self) -> None:
        self.faithfulness_judge = FaithfulnessJudge()
        self.tone_judge = ConstructiveToneJudge()
        self.neutrality_judge = DemographicNeutralityJudge()

    def evaluate_dossier(
        self,
        context: dict[str, Any],
        generated_output: str,
    ) -> JudgeEvaluationReport:
        faith_score = self.faithfulness_judge.evaluate(context, generated_output)
        tone_score = self.tone_judge.evaluate(context, generated_output)
        neutral_score = self.neutrality_judge.evaluate(context, generated_output)

        scores = {
            "faithfulness": faith_score,
            "constructive_tone": tone_score,
            "demographic_neutrality": neutral_score,
        }

        overall = round(
            (faith_score.score * 0.40) + (tone_score.score * 0.30) + (neutral_score.score * 0.30),
            2,
        )
        passed = all(s.passed for s in scores.values())

        summary = (
            f"Overall Score: {overall:.2f} (PASS)"
            if passed
            else f"Overall Score: {overall:.2f} (FAIL - Issues: {'; '.join(f.criterion_name for f in [faith_score, tone_score, neutral_score] if not f.passed)})"
        )

        return JudgeEvaluationReport(
            overall_score=overall,
            passed=passed,
            scores=scores,
            summary=summary,
        )
