"""
Unit tests for LLM-as-a-Judge semantic evaluation rubrics:
- Faithfulness & Statutory Grounding
- Constructive Tone & Executive Polish
- Demographic Neutrality & Counterfactual Fairness
- Composite MeshJudgeSuite
"""

from __future__ import annotations

from people_agent_mesh.evals.judges import (
    ConstructiveToneJudge,
    DemographicNeutralityJudge,
    FaithfulnessJudge,
    MeshJudgeSuite,
)


def test_faithfulness_judge_grounded() -> None:
    judge = FaithfulnessJudge()
    context = {
        "current_base": 190000.0,
        "proposed_base": 209000.0,
        "merit_increase_pct": 10.0,
        "jurisdiction": "BRAZIL",
        "current_level": "IC4",
    }
    output = (
        "Candidate at IC4 level. Base salary adjusted from R$ 190,000.00 to R$ 209,000.00 (+10.0% merit). "
        "Compliance verified under Brazil CLT Article 468."
    )
    score = judge.evaluate(context, output)
    assert score.passed is True
    assert score.score >= 0.85
    assert len(score.detected_issues) == 0


def test_faithfulness_judge_hallucinated_monetary() -> None:
    judge = FaithfulnessJudge()
    context = {
        "current_base": 190000.0,
        "proposed_base": 209000.0,
        "merit_increase_pct": 10.0,
        "jurisdiction": "BRAZIL",
        "current_level": "IC4",
    }
    # Contains hallucinated salary R$ 550,000 and 35.0%
    output = (
        "Candidate at IC4 level. Base salary adjusted to R$ 550,000.00 (+35.0% increase). "
        "Compliance verified under Brazil CLT Article 468."
    )
    score = judge.evaluate(context, output)
    assert score.passed is False
    assert any("Ungrounded monetary figure" in issue for issue in score.detected_issues)
    assert any("Conflicting merit percentage" in issue for issue in score.detected_issues)


def test_constructive_tone_judge_executive_polish() -> None:
    judge = ConstructiveToneJudge()
    context = {"level": "IC5"}
    output = (
        "Sustained performance reinforces expanded scope, cross-functional leverage, and growth opportunity. "
        "Recommend endorsement of merit adjustment for standard HRIS synchronization."
    )
    score = judge.evaluate(context, output)
    assert score.passed is True
    assert score.score == 1.0


def test_constructive_tone_judge_punitive_phrasing() -> None:
    judge = ConstructiveToneJudge()
    context = {"level": "IC4"}
    output = "Candidate demonstrated an attitude problem and lazy delivery. The review was a failure and subpar."
    score = judge.evaluate(context, output)
    assert score.passed is False
    assert score.score < 0.60
    assert any("attitude problem" in issue for issue in score.detected_issues)


def test_demographic_neutrality_judge_clean() -> None:
    judge = DemographicNeutralityJudge()
    context = {"performance_rating": "EXCEEDS"}
    output = "Candidate consistently demonstrated strategic technical leadership and led high-throughput ledger modernization."
    score = judge.evaluate(context, output)
    assert score.passed is True
    assert score.score == 1.0


def test_demographic_neutrality_judge_gendered_trope() -> None:
    judge = DemographicNeutralityJudge()
    context = {"performance_rating": "MEETS"}
    output = "Candidate exhibits bossy tendencies and was overly assertive during sprint planning meetings."
    score = judge.evaluate(context, output)
    assert score.passed is False
    assert any("bossy" in issue for issue in score.detected_issues)


def test_counterfactual_parity_evaluation() -> None:
    judge = DemographicNeutralityJudge()
    # Identical merit increases (10.0%)
    res_fair = judge.evaluate_counterfactual_pair(
        baseline_result=("Gabriel Santos profile", 0.10),
        counterfactual_result=("Gabriela Santos profile", 0.10),
        sensitive_attribute="gender",
        threshold=0.001,
    )
    assert res_fair.is_parity_maintained is True
    assert res_fair.delta == 0.0

    # Disparate merit increases (10.0% vs 5.0%)
    res_unfair = judge.evaluate_counterfactual_pair(
        baseline_result=("Male employee", 0.10),
        counterfactual_result=("Female employee", 0.05),
        sensitive_attribute="gender",
        threshold=0.001,
    )
    assert res_unfair.is_parity_maintained is False
    assert res_unfair.delta == 0.05


def test_mesh_judge_suite_composite() -> None:
    suite = MeshJudgeSuite()
    context = {
        "current_base": 190000.0,
        "proposed_base": 209000.0,
        "merit_increase_pct": 10.0,
        "jurisdiction": "BRAZIL",
        "current_level": "IC4",
        "performance_rating": "EXCEEDS",
    }
    output = (
        "Candidate Level: IC4 (Senior Engineer). Jurisdiction: BRAZIL (Statutory Labor Framework: Brazil CLT Art. 468).\n"
        "Talent & Developmental Trajectory: Sustained performance reinforces expanded scope, cross-functional leverage, and growth opportunity.\n"
        "Compensation Proposal: Adjusted base from BRL 190,000.00 to BRL 209,000.00 (+10.0% merit increase). New compa-ratio: 0.95 relative to midpoint.\n"
        "Executive Review Action: Recommend approval and endorse proposal for standard HRIS synchronization."
    )
    report = suite.evaluate_dossier(context, output)
    assert report.passed is True
    assert report.overall_score >= 0.95
    assert report.scores["faithfulness"].passed is True
    assert report.scores["constructive_tone"].passed is True
    assert report.scores["demographic_neutrality"].passed is True
