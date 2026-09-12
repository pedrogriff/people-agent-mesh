"""
Interactive Command Line Interface for PeopleAgentMesh.
Provides showcase demonstrations, eval suite execution, and system diagnostics.
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal

from people_agent_mesh.agents.supervisor import MeshSupervisorAgent
from people_agent_mesh.core.state import (
    ApprovalStatus,
    EmployeeProfile,
    Jurisdiction,
    MeshState,
    WorkflowStatus,
    WorkflowType,
)
from people_agent_mesh.evals.runner import EvalSuiteRunner
from people_agent_mesh.security.abac import ABACSecurityEngine, ReportingHierarchy
from people_agent_mesh.security.tokenizer import ZeroRetentionPrivacyGateway
from people_agent_mesh.telemetry.tracer import MeshTelemetryTracer


def run_evals() -> None:
    print("=================================================================")
    print("  PEOPLE-AGENT-MESH: CI EVALUATION BENCHMARK SUITE")
    print("  Evaluating Faithfulness, Invariants, HITL Gating & Privacy")
    print("=================================================================\n")
    runner = EvalSuiteRunner()
    result = runner.run()

    for d in result.details:
        status_symbol = "✅ PASS" if d["passed"] else "❌ FAIL"
        print(f"  [{status_symbol}] Scenario: {d['id']} ({d['duration_ms']}ms)")
        for err in d.get("errors", []):
            print(f"         ⚠️  {err}")

    print("\n-----------------------------------------------------------------")
    print(f"  Total Scenarios:            {result.total_cases}")
    print(f"  Passed Scenarios:           {result.passed_cases}")
    print(f"  Accuracy Rate:              {result.accuracy_rate * 100:.1f}%")
    print(f"  Compliance Adherence:       {result.compliance_adherence_rate * 100:.1f}%")
    print(f"  HITL Routing Precision:     {result.hitl_routing_precision * 100:.1f}%")
    print(
        f"  Zero PII Leakage Verified:  {'YES (Enforced)' if result.zero_pii_leak_verified else 'NO'}"
    )
    print(f"  Average Agent Latency:      {result.avg_latency_ms:.2f} ms")
    print(
        f"  CI Quality Gate Status:     {'🟢 APPROVED FOR MERGE' if result.ci_gate_passed else '🔴 BLOCKED BY CI'}"
    )
    print("-----------------------------------------------------------------\n")

    if not result.ci_gate_passed:
        sys.exit(1)


def run_demo() -> None:
    print("=================================================================")
    print("  PEOPLE-AGENT-MESH: END-TO-END DEMONSTRATION")
    print("  Orchestrating Cross-Border Talent Calibration with HITL Interruption")
    print("=================================================================\n")

    # 1. Setup sample hierarchy
    hierarchy = ReportingHierarchy({"MGR-EXEC-01": ["EMP-BR-8821"]})
    abac = ABACSecurityEngine(hierarchy)
    privacy = ZeroRetentionPrivacyGateway()
    tracer = MeshTelemetryTracer()
    supervisor = MeshSupervisorAgent(abac_engine=abac, privacy_gateway=privacy)

    # 2. Define Employee in Brazil
    raw_cpf = "123.456.789-00"
    emp = EmployeeProfile(
        employee_id="EMP-BR-8821",
        name="Gabriel Santos",
        email="gabriel.santos@enterprise.internal",
        department="Core Banking Infrastructure",
        job_title="Senior Software Engineer",
        level="IC4",
        jurisdiction=Jurisdiction.BRAZIL,
        manager_id="MGR-EXEC-01",
        base_salary=Decimal("190000.00"),
        currency="BRL",
        compa_ratio=Decimal("0.86"),
        performance_rating="EXCEEDS",
        tenure_months=26,
    )

    print("1. [INGRESS] Initiating Full Talent Dossier Workflow...")
    print(f"   Employee:       {emp.name} ({emp.employee_id})")
    print(f"   Jurisdiction:   {emp.jurisdiction.value} (CLT / LGPD)")
    print(f"   Current Level:  {emp.level} | Current Base: R$ {emp.base_salary:,.2f}")
    print(f"   Compa-Ratio:    {emp.compa_ratio:.2f} | Rating: {emp.performance_rating}\n")

    # 3. Demonstrate PII Tokenization
    raw_prompt = f"Calibrate employee {emp.name} with CPF {raw_cpf} and current salary R$ {emp.base_salary:,.2f}."
    tokenized_prompt = privacy.tokenize(raw_prompt)
    print("2. [PRIVACY GATEWAY] Zero-Retention Boundary Tokenization:")
    print(f"   Raw Ingress:    '{raw_prompt}'")
    print(f"   Tokenized Ext:  '{tokenized_prompt}'")
    privacy.assert_zero_pii_leakage(tokenized_prompt)
    print(
        "   Zero PII Invariant Verified: ✅ Zero plaintext identifiers exposed to model context.\n"
    )

    # 4. Execute Orchestrator
    init_state = MeshState(
        workflow_id="WF-DEMO-2026-001",
        workflow_type=WorkflowType.FULL_TALENT_DOSSIER,
        jurisdiction=emp.jurisdiction,
        employee=emp,
        requester_id="MGR-EXEC-01",
        requester_role="PEOPLE_MANAGER",
    )

    span = tracer.start_span(
        trace_id="tr-8821",
        agent_name="MeshSupervisorAgent",
        workflow_id=init_state.workflow_id,
        department=emp.department,
    )

    print("3. [AGENT ORCHESTRATION] Executing Multi-Agent Mesh...")
    res = supervisor.execute(init_state)
    state = res.state

    tracer.finish_span(span, prompt_tokens=1420, completion_tokens=490)

    print(f"   Supervisor Status: {state.status.value}")
    if state.comp_proposal:
        print(
            f"   Compensation Agent Proposal: R$ {state.comp_proposal.proposed_base:,.2f} "
            f"(+{(state.comp_proposal.percentage_increase * 100):.1f}% merit)"
        )
        print(f"   Calculated Bonus Payout:     R$ {state.comp_proposal.calculated_bonus:,.2f}")
        print(f"   Compa-Ratio Post:            {state.comp_proposal.compa_ratio_after:.2f}")

    if state.promotion_proposal:
        print(
            f"   Promotion Agent Proposal:    {state.promotion_proposal.current_level} -> {state.promotion_proposal.proposed_level}"
        )
        print(
            f"   Readiness Score:             {state.promotion_proposal.readiness_score * 100:.0f}%"
        )

    print(f"   Compliance Verification:     {'Passed' if state.compliance_passed else 'Failed'}\n")

    # 5. Check HITL Interruption
    if state.status == WorkflowStatus.AWAITING_HUMAN_APPROVAL and state.approval_request:
        req = state.approval_request
        print("4. [HITL INTERRUPT] State Machine Halted at Executive Approval Gate:")
        print(f"   Request ID:        {req.request_id}")
        print(f"   Required Approver: {req.required_role}")
        print(f"   Risk Score:        {req.risk_score:.2f}")
        print(f"   Triggered Reason:  {req.triggered_reason}")
        print(
            "   Status:            AWAITING_HUMAN_APPROVAL (Interactive Slack Webhook Dispatched)\n"
        )

        print("5. [RESUMPTION] Simulating VP of Engineering Approval Sign-off...")
        resumed_state = supervisor.resume_human_decision(
            state=state,
            decision=ApprovalStatus.APPROVED,
            decided_by="vp.engineering@enterprise.internal",
            comments="Approved based on exceptional cross-border infrastructure delivery and strong team impact.",
        )
        print(f"   Workflow Resumed. Final Status: {resumed_state.status.value}")
        print(
            f"   Approval Decision: {resumed_state.approval_request.status.value if resumed_state.approval_request else 'N/A'}"
        )
        print(f"   Audit Entries:     {len(resumed_state.audit_trail)} logged.\n")

    # 6. FinOps Telemetry Summary
    costs = tracer.get_departmental_attribution()
    print("6. [AGENTOPS & TELEMETRY] Departmental FinOps Attribution:")
    for dept, attr in costs.items():
        print(f"   Department: {dept}")
        print(f"     Spans Tracked:     {attr['total_spans']}")
        print(f"     Total Tokens:      {attr['prompt_tokens'] + attr['completion_tokens']}")
        print(f"     Estimated Cost:    ${attr['total_cost_usd']} USD")
        print(f"     Average Latency:   {attr['avg_duration_ms']} ms\n")

    print("=================================================================")
    print("  DEMONSTRATION COMPLETE: Production Quality Bar Satisfied! 🚀")
    print("=================================================================")


def run_ui(host: str = "127.0.0.1", port: int = 8000) -> None:
    import uvicorn

    print("=================================================================")
    print("  PEOPLE-AGENT-MESH: LIVE ENTERPRISE WEB SHOWCASE")
    print(f"  Serving Interactive Dashboard & REST API at http://{host}:{port}")
    print("=================================================================\n")
    uvicorn.run("people_agent_mesh.server:app", host=host, port=port, reload=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="PeopleAgentMesh Staff CLI")
    parser.add_argument("--evals", action="store_true", help="Execute CI evaluation suite")
    parser.add_argument(
        "--demo", action="store_true", help="Run end-to-end talent calibration showcase"
    )
    parser.add_argument(
        "--ui", action="store_true", help="Launch interactive web showcase dashboard"
    )
    parser.add_argument(
        "--host", type=str, default="127.0.0.1", help="Server host (default: 127.0.0.1)"
    )
    parser.add_argument("--port", type=int, default=8000, help="Server port (default: 8000)")
    args = parser.parse_args()

    if args.ui:
        run_ui(host=args.host, port=args.port)
    elif args.evals:
        run_evals()
    else:
        run_demo()


if __name__ == "__main__":
    main()
