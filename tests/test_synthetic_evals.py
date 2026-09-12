"""
Unit tests for synthetic edge cases and counterfactual demographic parity generator.
"""

from __future__ import annotations

from decimal import Decimal

from people_agent_mesh.evals.synthetic import (
    CounterfactualGenerator,
    SyntheticEdgeCaseGenerator,
)


def test_synthetic_edge_cases_generation() -> None:
    cases = SyntheticEdgeCaseGenerator.get_all_synthetic_edge_cases()
    assert len(cases) == 4

    case_ids = [c["id"] for c in cases]
    assert "SYNTH-GREEN-001" in case_ids
    assert "SYNTH-RED-002" in case_ids
    assert "SYNTH-FLSA-003" in case_ids
    assert "SYNTH-TENURE-004" in case_ids


def test_extreme_green_circle_properties() -> None:
    case = SyntheticEdgeCaseGenerator.get_extreme_green_circle_case()
    assert case["employee"].compa_ratio == Decimal("0.65")
    assert case["expected_hitl_required"] is True
    assert case["min_expected_increase"] == Decimal("0.10")


def test_extreme_red_circle_properties() -> None:
    case = SyntheticEdgeCaseGenerator.get_extreme_red_circle_case()
    assert case["employee"].compa_ratio == Decimal("1.38")
    assert case["expected_hitl_required"] is True
    assert case["max_expected_increase"] == Decimal("0.04")


def test_counterfactual_pairs_invariance() -> None:
    pairs = CounterfactualGenerator.generate_counterfactual_test_pairs()
    assert len(pairs) == 4

    for p in pairs:
        base = p["baseline_employee"]
        cf = p["counterfactual_employee"]

        # Ensure protected demographic variation
        assert base.name != cf.name

        # Ensure quantitative financial parameters are strictly invariant
        assert base.base_salary == cf.base_salary
        assert base.compa_ratio == cf.compa_ratio
        assert base.performance_rating == cf.performance_rating
        assert base.level == cf.level
        assert base.jurisdiction == cf.jurisdiction
        assert base.tenure_months == cf.tenure_months
