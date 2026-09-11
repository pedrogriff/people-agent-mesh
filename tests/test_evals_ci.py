from people_agent_mesh.evals.runner import EvalSuiteRunner


def test_golden_eval_suite_ci_gate() -> None:
    runner = EvalSuiteRunner()
    result = runner.run()

    assert result.total_cases >= 4
    assert result.compliance_adherence_rate == 1.0
    assert result.accuracy_rate >= 0.95
    assert result.hitl_routing_precision >= 0.95
    assert result.zero_pii_leak_verified is True
    assert result.ci_gate_passed is True
