"""
Core Model Context Protocol (MCP) Server for PeopleAgentMesh.
Exposes deterministic compensation calculation, labor compliance verification,
and zero-retention PII tokenization as standardized MCP Tools, Resources, and Prompts.
"""

from __future__ import annotations

import json
import os
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

from people_agent_mesh.agents.compensation import CompensationAgent
from people_agent_mesh.core.state import (
    CompensationProposal,
    EmployeeProfile,
    Jurisdiction,
    MeshState,
    WorkflowType,
)
from people_agent_mesh.durable.engine import DurableWorkflowEngine
from people_agent_mesh.durable.store import SQLiteDurableStore
from people_agent_mesh.mcp.protocol import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    LATEST_PROTOCOL_VERSION,
    METHOD_NOT_FOUND,
    JSONRPCError,
    JSONRPCRequest,
    JSONRPCResponse,
    PromptArgument,
    PromptDefinition,
    PromptMessage,
    ResourceContent,
    ResourceDefinition,
    ToolCallResult,
    ToolDefinition,
)
from people_agent_mesh.security.canary import CanaryManager
from people_agent_mesh.security.compliance import ComplianceEngine
from people_agent_mesh.security.guardrails import PromptInjectionGuardrail
from people_agent_mesh.security.tokenizer import PIITokenVault, ZeroRetentionPrivacyGateway
from people_agent_mesh.tools.contracts import MarketBandInput
from people_agent_mesh.tools.enterprise_tools import MarketBenchmarkTool


class PeopleMeshMCPServer:
    """
    Enterprise MCP Server complying with Anthropic MCP specification (2024-11-05).
    Provides JSON-RPC 2.0 dispatching over Stdio and HTTP/SSE transports.
    """

    SERVER_NAME = "people-agent-mesh-mcp"
    SERVER_VERSION = "0.1.0"

    def __init__(
        self,
        privacy_gateway: ZeroRetentionPrivacyGateway | None = None,
        benchmark_tool: MarketBenchmarkTool | None = None,
        guardrail: PromptInjectionGuardrail | None = None,
        canary_manager: CanaryManager | None = None,
    ) -> None:
        self.privacy_gateway = privacy_gateway or ZeroRetentionPrivacyGateway(PIITokenVault())
        self.benchmark_tool = benchmark_tool or MarketBenchmarkTool()
        self.compensation_agent = CompensationAgent(benchmark_tool=self.benchmark_tool)
        self.guardrail = guardrail or PromptInjectionGuardrail()
        self.canary_manager = canary_manager or CanaryManager()
        self.session_vaults: dict[str, ZeroRetentionPrivacyGateway] = {}

        # Durable Execution Engine & Store (ADR-007)
        durable_db = os.getenv(
            "DURABLE_STORE_PATH",
            str(Path(os.path.expanduser("~")) / ".people_agent_mesh" / "durable_workflows.db"),
        )
        self.durable_store = SQLiteDurableStore(db_path=durable_db)
        self.durable_engine = DurableWorkflowEngine(store=self.durable_store)

    def _get_gateway(self, session_id: str | None) -> ZeroRetentionPrivacyGateway:
        if not session_id:
            return self.privacy_gateway
        if session_id not in self.session_vaults:
            self.session_vaults[session_id] = ZeroRetentionPrivacyGateway(PIITokenVault())
        return self.session_vaults[session_id]

    # --- Tool Definitions ---

    def list_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="validate_clt_compliance",
                description=(
                    "Deterministically verifies Brazilian labor law (CLT Article 468, CF Art. 7) compliance. "
                    "Enforces the strict prohibition of unilateral salary reductions, parental leave wage protections, "
                    "and statutory minimum baseline standards."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "current_base": {
                            "type": "number",
                            "description": "Current base salary in local currency (BRL).",
                        },
                        "proposed_base": {
                            "type": "number",
                            "description": "Proposed base salary post-adjustment in local currency (BRL).",
                        },
                        "is_on_parental_leave": {
                            "type": "boolean",
                            "default": False,
                            "description": "Flag indicating if the employee is currently on statutory parental/maternity leave.",
                        },
                        "employee_id": {
                            "type": "string",
                            "default": "EMP-ANON",
                            "description": "Optional employee identifier for auditing.",
                        },
                    },
                    "required": ["current_base", "proposed_base"],
                },
            ),
            ToolDefinition(
                name="resolve_salary_band",
                description=(
                    "Fetches verified market benchmark compensation bands (min, mid, max, currency, and spread) "
                    "for a job family, seniority level, and geographic location tier."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "job_family": {
                            "type": "string",
                            "description": "Job family title (e.g., 'SOFTWARE_ENGINEERING', 'PRODUCT_MANAGEMENT').",
                            "default": "SOFTWARE_ENGINEERING",
                        },
                        "level": {
                            "type": "string",
                            "description": "Standard engineering level: 'IC4' (Mid), 'IC5' (Senior), 'IC6' (Staff/Principal).",
                            "default": "IC5",
                        },
                        "location_tier": {
                            "type": "string",
                            "description": "Geographic market tier: 'BR_SP' (São Paulo), 'US_NYC' (New York), 'CA_TORONTO' (Toronto).",
                            "default": "BR_SP",
                        },
                    },
                    "required": ["job_family", "level", "location_tier"],
                },
            ),
            ToolDefinition(
                name="calculate_compa_ratio",
                description=(
                    "Calculates mathematical compa-ratio (Base / Midpoint) and range penetration "
                    "((Base - Min) / (Max - Min)) with green-circle and red-circle zone classification."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "base_salary": {
                            "type": "number",
                            "description": "Actual employee base salary.",
                        },
                        "band_midpoint": {
                            "type": "number",
                            "description": "Approved benchmark band midpoint.",
                        },
                        "band_min": {
                            "type": "number",
                            "description": "Optional band minimum for range penetration.",
                        },
                        "band_max": {
                            "type": "number",
                            "description": "Optional band maximum for range penetration.",
                        },
                    },
                    "required": ["base_salary", "band_midpoint"],
                },
            ),
            ToolDefinition(
                name="evaluate_merit_proposal",
                description=(
                    "Executes a deterministic compensation calibration model: calculates merit percentage, "
                    "new base salary, formulaic annual bonus (Base * Target% * IPF * CPF), and equity guidelines."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "current_base": {
                            "type": "number",
                            "description": "Current employee annual base salary.",
                        },
                        "performance_rating": {
                            "type": "string",
                            "enum": ["EXCEEDS", "MEETS_HIGH", "MEETS", "NEEDS_IMPROVEMENT"],
                            "description": "Performance calibration rating.",
                        },
                        "level": {
                            "type": "string",
                            "description": "Seniority level ('IC4', 'IC5', 'IC6').",
                            "default": "IC5",
                        },
                        "jurisdiction": {
                            "type": "string",
                            "enum": ["BRAZIL", "UNITED_STATES", "CANADA"],
                            "description": "Employee employment jurisdiction.",
                            "default": "BRAZIL",
                        },
                        "compa_ratio": {
                            "type": "number",
                            "description": "Current compa-ratio prior to adjustment (e.g. 0.92).",
                            "default": 1.0,
                        },
                    },
                    "required": [
                        "current_base",
                        "performance_rating",
                        "level",
                        "jurisdiction",
                        "compa_ratio",
                    ],
                },
            ),
            ToolDefinition(
                name="tokenize_pii",
                description=(
                    "Perimeter privacy scrubber: replaces sensitive identifiers (Brazilian CPF, US SSN, "
                    "Canadian SIN, compensation amounts, and emails) with reversible surrogate tokens for zero-retention LLM inference."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Raw un-sanitized text containing potential PII/SPII.",
                        },
                        "session_id": {
                            "type": "string",
                            "description": "Optional session ID for tenant isolation.",
                        },
                    },
                    "required": ["text"],
                },
            ),
            ToolDefinition(
                name="detokenize_pii",
                description=(
                    "Restores surrogate tokens ([TOKEN_...]) back to plaintext identifiers within the trusted perimeter."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "tokenized_text": {
                            "type": "string",
                            "description": "Text containing surrogate tokens.",
                        },
                        "session_id": {
                            "type": "string",
                            "description": "Optional session ID used during tokenization.",
                        },
                    },
                    "required": ["tokenized_text"],
                },
            ),
            ToolDefinition(
                name="shred_pii_vault",
                description=(
                    "Cryptographically shreds token-to-plaintext mapping in the vault, permanently rendering "
                    "all external logs irreversible for LGPD Art. 18 / GDPR 'Right to be Forgotten'."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "Optional session ID to shred.",
                        }
                    },
                },
            ),
            ToolDefinition(
                name="scan_prompt_injection",
                description=(
                    "Evaluates untrusted employee notes, self-evaluations, or RAG documents "
                    "for prompt injection, jailbreaks, delimiter escape, and privilege escalation attacks. "
                    "Returns normalized threat score (0.0 - 1.0), severity, matched patterns, and sanitized text."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Raw untrusted text to inspect for adversarial attacks.",
                        },
                    },
                    "required": ["text"],
                },
            ),
            ToolDefinition(
                name="verify_canary_integrity",
                description=(
                    "Scans text payloads for cryptographic tripwires (canary tokens). "
                    "Asserts zero canary leakage to detect exfiltration of confidential context."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Output text to verify for canary tripwire leakage.",
                        },
                    },
                    "required": ["text"],
                },
            ),
            ToolDefinition(
                name="run_calibration_committee",
                description=(
                    "Executes a Multi-Agent Talent Calibration Committee deliberation (ADR-006). "
                    "Convenes Advocate, Skeptic (Bar Raiser), Equity Auditor, and Consensus Moderator agents "
                    "with formal Reflexion self-correction to audit promotion proposals and generate consensus coaching OKRs."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "employee_id": {
                            "type": "string",
                            "description": "Unique employee identifier (e.g. 'EMP-101').",
                            "default": "EMP-CALIB-01",
                        },
                        "name": {
                            "type": "string",
                            "description": "Employee name or token.",
                            "default": "Senior Staff Candidate",
                        },
                        "department": {
                            "type": "string",
                            "description": "Department name.",
                            "default": "Core Engineering",
                        },
                        "level": {
                            "type": "string",
                            "description": "Current engineering level (e.g. 'IC4', 'IC5').",
                            "default": "IC4",
                        },
                        "target_level": {
                            "type": "string",
                            "description": "Proposed promotion target level (e.g. 'IC5').",
                            "default": "IC5",
                        },
                        "jurisdiction": {
                            "type": "string",
                            "enum": ["BRAZIL", "UNITED_STATES", "CANADA"],
                            "description": "Jurisdiction governing labor compliance.",
                            "default": "UNITED_STATES",
                        },
                        "base_salary": {
                            "type": "number",
                            "description": "Current base salary amount.",
                            "default": 175000.0,
                        },
                        "currency": {
                            "type": "string",
                            "description": "Currency code ('USD', 'BRL', 'CAD').",
                            "default": "USD",
                        },
                        "performance_rating": {
                            "type": "string",
                            "enum": ["EXCEEDS", "MEETS_HIGH", "MEETS", "NEEDS_IMPROVEMENT"],
                            "description": "Current performance rating.",
                            "default": "EXCEEDS",
                        },
                        "tenure_months": {
                            "type": "integer",
                            "description": "Tenure in current level in months.",
                            "default": 16,
                        },
                        "compa_ratio": {
                            "type": "number",
                            "description": "Current compa-ratio (e.g. 0.95).",
                            "default": 0.95,
                        },
                    },
                    "required": ["level", "performance_rating"],
                },
            ),
            ToolDefinition(
                name="start_durable_workflow",
                description=(
                    "Initiates an event-sourced durable workflow with Write-Ahead Logging (WAL) "
                    "and crash resilience (ADR-007). Suspends asynchronously on HITL gating."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "employee_id": {
                            "type": "string",
                            "description": "Employee ID (e.g. 'EMP-DUR-01').",
                            "default": "EMP-DUR-01",
                        },
                        "name": {
                            "type": "string",
                            "description": "Employee full name.",
                            "default": "Elena Rostova",
                        },
                        "level": {
                            "type": "string",
                            "description": "Current engineering level (e.g. 'IC4').",
                            "default": "IC4",
                        },
                        "jurisdiction": {
                            "type": "string",
                            "enum": ["BRAZIL", "UNITED_STATES", "CANADA"],
                            "description": "Statutory labor jurisdiction.",
                            "default": "UNITED_STATES",
                        },
                        "base_salary": {
                            "type": "number",
                            "description": "Base salary amount.",
                            "default": 175000.0,
                        },
                        "currency": {
                            "type": "string",
                            "description": "Currency code ('USD', 'BRL', 'CAD').",
                            "default": "USD",
                        },
                        "performance_rating": {
                            "type": "string",
                            "enum": ["EXCEEDS", "MEETS_HIGH", "MEETS", "NEEDS_IMPROVEMENT"],
                            "description": "Performance appraisal rating.",
                            "default": "EXCEEDS",
                        },
                        "tenure_months": {
                            "type": "integer",
                            "description": "Tenure at level in months.",
                            "default": 20,
                        },
                        "workflow_type": {
                            "type": "string",
                            "description": "Workflow type.",
                            "default": "FULL_TALENT_DOSSIER",
                        },
                    },
                    "required": ["name", "level", "performance_rating"],
                },
            ),
            ToolDefinition(
                name="signal_durable_workflow",
                description=(
                    "Delivers an asynchronous human decision or timer signal to a suspended "
                    "durable workflow, triggering forward completion or backward saga rollback (ADR-007)."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "workflow_id": {
                            "type": "string",
                            "description": "Target workflow ID.",
                        },
                        "decision": {
                            "type": "string",
                            "enum": ["APPROVED", "REJECTED", "REVISION_REQUESTED"],
                            "description": "Human decision outcome.",
                            "default": "APPROVED",
                        },
                        "decided_by": {
                            "type": "string",
                            "description": "Sign-off authority identifier.",
                            "default": "vp.engineering@enterprise.internal",
                        },
                        "comments": {
                            "type": "string",
                            "description": "Reviewer comments or justification.",
                            "default": "Endorsed via MCP tool invocation.",
                        },
                    },
                    "required": ["workflow_id", "decision"],
                },
            ),
            ToolDefinition(
                name="get_durable_workflow_history",
                description=(
                    "Inspects the append-only event stream and audit trail for an event-sourced "
                    "durable workflow from sequence #1 (ADR-007)."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "workflow_id": {
                            "type": "string",
                            "description": "Workflow identifier to inspect.",
                        },
                    },
                    "required": ["workflow_id"],
                },
            ),
            ToolDefinition(
                name="replay_durable_workflow",
                description=(
                    "Deterministically replays the event history from sequence #1 to verify zero "
                    "divergence and crash recovery without re-invoking external side-effects (ADR-007)."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "workflow_id": {
                            "type": "string",
                            "description": "Workflow identifier to replay.",
                        },
                    },
                    "required": ["workflow_id"],
                },
            ),
        ]

    # --- Resource Definitions ---

    def list_resources(self) -> list[ResourceDefinition]:
        return [
            ResourceDefinition(
                uri="policy://brazil/clt-article-468",
                name="Brazil CLT Article 468 Labor Invariants",
                description="Statutory legal requirements prohibiting unilateral employment contract alterations and base salary reductions in Brazil.",
                mimeType="text/markdown",
            ),
            ResourceDefinition(
                uri="policy://us/flsa-exemption",
                name="United States FLSA Exemption Thresholds",
                description="Fair Labor Standards Act salary thresholds and duties tests for overtime-exempt status.",
                mimeType="text/markdown",
            ),
            ResourceDefinition(
                uri="policy://canada/pay-equity",
                name="Canada Pay Equity Act & Discretionary Adjustments",
                description="Guidelines for Canadian equal value compensation and managerial discretion bounds.",
                mimeType="text/markdown",
            ),
            ResourceDefinition(
                uri="bands://software-engineering",
                name="Global Software Engineering Benchmark Bands",
                description="Official 2025 engineering benchmark ranges (IC4-IC6) across São Paulo, New York, and Toronto.",
                mimeType="application/json",
            ),
        ]

    def read_resource(self, uri: str) -> ResourceContent:
        if uri == "policy://brazil/clt-article-468":
            text = (
                "# Brazil CLT Article 468 — Legal Invariant Specification\n\n"
                "**Consolidação das Leis do Trabalho (CLT), Art. 468**:\n"
                "> *Nos contratos individuais de trabalho só é lícita a alteração das respectivas condições por mútuo consentimento, "
                "e ainda assim desde que não resultem, direta ou indiretamente, prejuízos ao empregado, sob pena de nulidade da cláusula infringente desta garantia.*\n\n"
                "### Invariant Rules for Autonomous Agents\n"
                "1. **Salary Inviolability**: `proposed_base < current_base` is strictly PROHIBITED and invalidates any automated workflow.\n"
                "2. **Parental Leave Protection**: Súmula 244 TST prohibits adverse adjustments during statutory maternity and parental leave.\n"
                "3. **Statutory Baseline**: Base compensation must never fall below federal minimum wage (R$ 1,412.00)."
            )
            return ResourceContent(uri=uri, mimeType="text/markdown", text=text)

        elif uri == "policy://us/flsa-exemption":
            text = (
                "# US Fair Labor Standards Act (FLSA) Exemption Specification\n\n"
                "**Standard Exemption Threshold**:\n"
                "- Minimum annual salary requirement for executive, administrative, and professional exemptions: **$58,656 USD**.\n"
                "- Employees compensated below this boundary must be classified as non-exempt, requiring overtime tracking.\n\n"
                "**Title VII & Equal Pay Act Guardrail**:\n"
                "- Compa-ratio post-adjustment should remain >= 0.80 unless substantiated by structured documentation."
            )
            return ResourceContent(uri=uri, mimeType="text/markdown", text=text)

        elif uri == "policy://canada/pay-equity":
            text = (
                "# Canada Pay Equity Act & Employment Standards\n\n"
                "**Equal Value Remuneration**:\n"
                "- Equal remuneration for work of equal value regardless of gender.\n"
                "- Discretionary compensation increases exceeding 30% trigger Total Rewards Director human sign-off."
            )
            return ResourceContent(uri=uri, mimeType="text/markdown", text=text)

        elif uri == "bands://software-engineering":
            bands_data = {
                "currency_units": "Annual Base",
                "bands": [
                    {
                        "level": "IC4",
                        "geo": "BR_SP",
                        "currency": "BRL",
                        "min": 180000,
                        "mid": 220000,
                        "max": 260000,
                    },
                    {
                        "level": "IC5",
                        "geo": "BR_SP",
                        "currency": "BRL",
                        "min": 240000,
                        "mid": 300000,
                        "max": 360000,
                    },
                    {
                        "level": "IC6",
                        "geo": "BR_SP",
                        "currency": "BRL",
                        "min": 330000,
                        "mid": 420000,
                        "max": 510000,
                    },
                    {
                        "level": "IC4",
                        "geo": "US_NYC",
                        "currency": "USD",
                        "min": 160000,
                        "mid": 190000,
                        "max": 225000,
                    },
                    {
                        "level": "IC5",
                        "geo": "US_NYC",
                        "currency": "USD",
                        "min": 210000,
                        "mid": 255000,
                        "max": 305000,
                    },
                    {
                        "level": "IC6",
                        "geo": "US_NYC",
                        "currency": "USD",
                        "min": 275000,
                        "mid": 340000,
                        "max": 410000,
                    },
                    {
                        "level": "IC4",
                        "geo": "CA_TORONTO",
                        "currency": "CAD",
                        "min": 130000,
                        "mid": 155000,
                        "max": 180000,
                    },
                    {
                        "level": "IC5",
                        "geo": "CA_TORONTO",
                        "currency": "CAD",
                        "min": 170000,
                        "mid": 205000,
                        "max": 240000,
                    },
                ],
            }
            return ResourceContent(
                uri=uri, mimeType="application/json", text=json.dumps(bands_data, indent=2)
            )

        raise KeyError(f"Resource not found: {uri}")

    # --- Prompt Definitions ---

    def list_prompts(self) -> list[PromptDefinition]:
        return [
            PromptDefinition(
                name="audit_compensation_proposal",
                description="Conducts a multi-jurisdictional compliance and financial audit of an employee compensation adjustment.",
                arguments=[
                    PromptArgument(
                        name="employee_id", description="Employee identifier", required=True
                    ),
                    PromptArgument(
                        name="jurisdiction",
                        description="BRAZIL, UNITED_STATES, or CANADA",
                        required=True,
                    ),
                    PromptArgument(
                        name="current_base", description="Current base salary", required=True
                    ),
                    PromptArgument(
                        name="proposed_base", description="Proposed base salary", required=True
                    ),
                    PromptArgument(
                        name="performance_rating",
                        description="EXCEEDS, MEETS_HIGH, etc.",
                        required=True,
                    ),
                ],
            ),
            PromptDefinition(
                name="pii_scrub_and_evaluate",
                description="Instructs the model to inspect text for sensitive People identifiers, invoke tokenize_pii, and produce an anonymized summary.",
                arguments=[
                    PromptArgument(
                        name="raw_text",
                        description="Un-sanitized People document text",
                        required=True,
                    ),
                ],
            ),
        ]

    def get_prompt(self, name: str, arguments: dict[str, str]) -> list[PromptMessage]:
        if name == "audit_compensation_proposal":
            emp_id = arguments.get("employee_id", "EMP-UNKNOWN")
            jur = arguments.get("jurisdiction", "BRAZIL")
            c_base = arguments.get("current_base", "0")
            p_base = arguments.get("proposed_base", "0")
            rating = arguments.get("performance_rating", "MEETS")

            prompt_text = (
                f"You are the People Agent Mesh Compensation Auditor.\n"
                f"Audit the following adjustment proposal for employee {emp_id} in {jur}:\n"
                f"- Current Base Salary: {c_base}\n"
                f"- Proposed Base Salary: {p_base}\n"
                f"- Performance Rating: {rating}\n\n"
                f"Step 1: Invoke tool 'validate_clt_compliance' if jurisdiction is BRAZIL.\n"
                f"Step 2: Invoke tool 'resolve_salary_band' and 'calculate_compa_ratio'.\n"
                f"Step 3: If any violation or out-of-band condition is detected, flag for Human-in-the-Loop (HITL) review."
            )
            return [PromptMessage(role="user", content={"type": "text", "text": prompt_text})]

        elif name == "pii_scrub_and_evaluate":
            raw = arguments.get("raw_text", "")
            prompt_text = (
                f"You are a Zero-Retention Privacy Gateway Agent.\n"
                f"Below is sensitive People Operations text:\n"
                f"'''{raw}'''\n\n"
                f"Step 1: Invoke 'tokenize_pii' to replace all CPFs, SSNs, SINs, salaries, and emails with surrogate tokens.\n"
                f"Step 2: Summarize the key operational feedback without exposing sensitive plaintext."
            )
            return [PromptMessage(role="user", content={"type": "text", "text": prompt_text})]

        raise KeyError(f"Prompt not found: {name}")

    # --- Tool Execution Dispatcher ---

    def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolCallResult:
        try:
            if name == "validate_clt_compliance":
                curr = Decimal(str(arguments["current_base"]))
                prop = Decimal(str(arguments["proposed_base"]))
                on_leave = bool(arguments.get("is_on_parental_leave", False))
                emp_id = str(arguments.get("employee_id", "EMP-ANON"))

                mock_emp = EmployeeProfile(
                    employee_id=emp_id,
                    name="Candidate Subject",
                    email="subject@enterprise.internal",
                    department="ENGINEERING",
                    job_title="Software Engineer",
                    level="IC5",
                    jurisdiction=Jurisdiction.BRAZIL,
                    manager_id="MGR-01",
                    base_salary=curr,
                    currency="BRL",
                    compa_ratio=Decimal("1.0"),
                    performance_rating="MEETS",
                    tenure_months=24,
                )

                pct = (prop - curr) / curr if curr > 0 else Decimal("0.0")
                proposal = CompensationProposal(
                    current_base=curr,
                    proposed_base=prop,
                    percentage_increase=pct,
                    proposed_equity_shares=0,
                    bonus_target_pct=Decimal("0.15"),
                    individual_perf_factor=Decimal("1.0"),
                    company_perf_factor=Decimal("1.0"),
                    calculated_bonus=Decimal("0"),
                    compa_ratio_after=Decimal("1.0"),
                    rationale="Audit proposal",
                )

                report = ComplianceEngine.verify(
                    employee=mock_emp,
                    comp_proposal=proposal,
                    is_on_parental_leave=on_leave,
                )

                report_data: dict[str, Any] = {
                    "passed": report.passed,
                    "jurisdiction": report.jurisdiction.value,
                    "violations": report.violations,
                    "warnings": report.warnings,
                    "statutory_citations": [
                        "CLT Art. 468 (Prohibition of unilateral adverse alterations)",
                        "CF/88 Art. 7, VI (Irreducibility of compensation)",
                    ]
                    if not report.passed
                    else ["CLT Compliant"],
                }
                return ToolCallResult(
                    content=[{"type": "text", "text": json.dumps(report_data, indent=2)}],
                    isError=not report.passed,
                )

            elif name == "resolve_salary_band":
                inp = MarketBandInput(
                    job_family=str(arguments.get("job_family", "SOFTWARE_ENGINEERING")),
                    level=str(arguments.get("level", "IC5")),
                    location_tier=str(arguments.get("location_tier", "BR_SP")),
                )
                band = self.benchmark_tool.resolve(inp)
                band_data: dict[str, Any] = {
                    "job_family": inp.job_family,
                    "level": inp.level,
                    "location_tier": inp.location_tier,
                    "currency": band.currency,
                    "band_min": float(band.band_min),
                    "band_mid": float(band.band_mid),
                    "band_max": float(band.band_max),
                    "spread_percentage": float(band.spread * 100),
                }
                return ToolCallResult(
                    content=[{"type": "text", "text": json.dumps(band_data, indent=2)}],
                    isError=False,
                )

            elif name == "calculate_compa_ratio":
                base = Decimal(str(arguments["base_salary"]))
                mid = Decimal(str(arguments["band_midpoint"]))
                compa = (base / mid).quantize(Decimal("0.0001"))

                compa_data: dict[str, Any] = {
                    "base_salary": float(base),
                    "band_midpoint": float(mid),
                    "compa_ratio": float(compa),
                }

                if "band_min" in arguments and "band_max" in arguments:
                    b_min = Decimal(str(arguments["band_min"]))
                    b_max = Decimal(str(arguments["band_max"]))
                    if b_max > b_min:
                        penetration = ((base - b_min) / (b_max - b_min)).quantize(Decimal("0.0001"))
                        compa_data["range_penetration"] = float(penetration)

                if compa < Decimal("0.80"):
                    compa_data["classification"] = "GREEN_CIRCLE_LOW"
                    compa_data["guidance"] = (
                        "Compensation is significantly below midpoint. Risk of attrition and compression."
                    )
                elif compa > Decimal("1.20"):
                    compa_data["classification"] = "RED_CIRCLE_HIGH"
                    compa_data["guidance"] = (
                        "Compensation exceeds standard band ceiling. Requires VP exception sign-off."
                    )
                else:
                    compa_data["classification"] = "WITHIN_TARGET_BAND"
                    compa_data["guidance"] = (
                        "Compensation is within healthy market competitive boundaries (0.80 - 1.20)."
                    )

                return ToolCallResult(
                    content=[{"type": "text", "text": json.dumps(compa_data, indent=2)}],
                    isError=False,
                )

            elif name == "evaluate_merit_proposal":
                curr = Decimal(str(arguments["current_base"]))
                rating = str(arguments["performance_rating"])
                level = str(arguments.get("level", "IC5"))
                jur_str = str(arguments.get("jurisdiction", "BRAZIL")).upper()
                jurisdiction = Jurisdiction(jur_str)
                compa = Decimal(str(arguments.get("compa_ratio", "1.0")))

                loc_tier = (
                    "BR_SP"
                    if jurisdiction == Jurisdiction.BRAZIL
                    else ("CA_TORONTO" if jurisdiction == Jurisdiction.CANADA else "US_NYC")
                )
                band = self.benchmark_tool.resolve(
                    MarketBandInput(
                        job_family="SOFTWARE_ENGINEERING",
                        level=level,
                        location_tier=loc_tier,
                    )
                )

                merit_pct = self.compensation_agent._determine_merit_increase(rating, compa)
                new_base = (curr * (Decimal("1.0") + merit_pct)).quantize(Decimal("0.01"))
                new_compa = (new_base / band.band_mid).quantize(Decimal("0.0001"))

                target_pct = Decimal("0.15") if level in {"IC4", "IC5"} else Decimal("0.25")
                ipf_map = {
                    "EXCEEDS": Decimal("1.25"),
                    "MEETS_HIGH": Decimal("1.10"),
                    "MEETS": Decimal("1.00"),
                    "NEEDS_IMPROVEMENT": Decimal("0.50"),
                }
                ipf = ipf_map.get(rating, Decimal("1.00"))
                cpf = Decimal("1.05")
                bonus = (new_base * target_pct * ipf * cpf).quantize(Decimal("0.01"))
                equity_shares = 500 if rating in {"EXCEEDS", "MEETS_HIGH"} else 0

                merit_data: dict[str, Any] = {
                    "current_base": float(curr),
                    "merit_increase_pct": float(merit_pct * 100),
                    "proposed_base": float(new_base),
                    "currency": band.currency,
                    "target_bonus_pct": float(target_pct * 100),
                    "calculated_bonus": float(bonus),
                    "equity_grant_shares": equity_shares,
                    "compa_ratio_after": float(new_compa),
                    "requires_hitl": (merit_pct >= Decimal("0.10") or new_compa > Decimal("1.15")),
                }
                return ToolCallResult(
                    content=[{"type": "text", "text": json.dumps(merit_data, indent=2)}],
                    isError=False,
                )

            elif name == "tokenize_pii":
                gateway = self._get_gateway(arguments.get("session_id"))
                raw_text = str(arguments["text"])
                tokenized = gateway.tokenize(raw_text)
                gateway.assert_zero_pii_leakage(tokenized)
                token_data: dict[str, Any] = {
                    "tokenized_text": tokenized,
                    "zero_pii_verified": True,
                    "session_id": arguments.get("session_id"),
                }
                return ToolCallResult(
                    content=[{"type": "text", "text": json.dumps(token_data, indent=2)}],
                    isError=False,
                )

            elif name == "detokenize_pii":
                gateway = self._get_gateway(arguments.get("session_id"))
                tok_text = str(arguments["tokenized_text"])
                restored = gateway.detokenize(tok_text)
                detok_data: dict[str, Any] = {
                    "detokenized_text": restored,
                }
                return ToolCallResult(
                    content=[{"type": "text", "text": json.dumps(detok_data, indent=2)}],
                    isError=False,
                )

            elif name == "shred_pii_vault":
                gateway = self._get_gateway(arguments.get("session_id"))
                shredded = gateway.vault.shred()
                shred_data: dict[str, Any] = {
                    "shredded_tokens_count": shredded,
                    "status": "CRYPTOGRAPHICALLY_DESTROYED",
                    "compliance": "LGPD Art. 18 / GDPR Right to be Forgotten",
                }
                return ToolCallResult(
                    content=[{"type": "text", "text": json.dumps(shred_data, indent=2)}],
                    isError=False,
                )

            elif name == "scan_prompt_injection":
                raw_text = str(arguments["text"])
                assessment = self.guardrail.evaluate_threat(raw_text)
                scan_data: dict[str, Any] = {
                    "is_blocked": assessment.is_blocked,
                    "threat_score": assessment.threat_score,
                    "severity": assessment.severity.value,
                    "matched_patterns": assessment.matched_patterns,
                    "sanitized_text": assessment.sanitized_text,
                    "explanation": assessment.explanation,
                }
                return ToolCallResult(
                    content=[{"type": "text", "text": json.dumps(scan_data, indent=2)}],
                    isError=assessment.is_blocked,
                )

            elif name == "verify_canary_integrity":
                out_text = str(arguments["text"])
                leaks = self.canary_manager.scan_for_leaks(out_text)
                canary_data: dict[str, Any] = {
                    "canary_leak_detected": len(leaks) > 0,
                    "leaked_tokens": leaks,
                    "status": "COMPROMISED" if leaks else "INTACT",
                }
                return ToolCallResult(
                    content=[{"type": "text", "text": json.dumps(canary_data, indent=2)}],
                    isError=len(leaks) > 0,
                )

            elif name == "run_calibration_committee":
                from people_agent_mesh.agents.committee import CalibrationCommitteeOrchestrator
                from people_agent_mesh.agents.promotion import PromotionAgent

                jur_str = str(arguments.get("jurisdiction", "UNITED_STATES")).upper()
                jur = (
                    Jurisdiction.BRAZIL
                    if "BRAZIL" in jur_str
                    else (
                        Jurisdiction.CANADA if "CANADA" in jur_str else Jurisdiction.UNITED_STATES
                    )
                )

                emp = EmployeeProfile(
                    employee_id=str(arguments.get("employee_id", "EMP-CALIB-01")),
                    name=str(arguments.get("name", "Senior Staff Candidate")),
                    email="candidate@enterprise.internal",
                    department=str(arguments.get("department", "Core Engineering")),
                    job_title="Software Engineer",
                    level=str(arguments.get("level", "IC4")),
                    jurisdiction=jur,
                    manager_id="MGR-001",
                    base_salary=Decimal(str(arguments.get("base_salary", 175000.0))),
                    currency=str(
                        arguments.get("currency", "USD" if jur != Jurisdiction.BRAZIL else "BRL")
                    ),
                    compa_ratio=Decimal(str(arguments.get("compa_ratio", 0.95))),
                    performance_rating=str(arguments.get("performance_rating", "EXCEEDS")),
                    tenure_months=int(arguments.get("tenure_months", 16)),
                )

                state = MeshState(
                    workflow_id=f"wf-mcp-committee-{uuid.uuid4().hex[:8]}",
                    workflow_type=WorkflowType.ANNUAL_CALIBRATION_COMMITTEE,
                    jurisdiction=jur,
                    employee=emp,
                    requester_id="REQ-MCP",
                    requester_role="HRBP_LEAD",
                )

                # Initialize baseline proposals
                comp_agent = CompensationAgent()
                promo_agent = PromotionAgent()
                state = comp_agent.execute(state).state
                state = promo_agent.execute(state).state

                orchestrator = CalibrationCommitteeOrchestrator()
                dossier = orchestrator.run_committee(state)

                res_payload: dict[str, Any] = {
                    "verdict": dossier.verdict.value,
                    "calibrated_level": dossier.calibrated_level,
                    "calibrated_increase_pct": float(dossier.calibrated_increase_pct * 100),
                    "executive_summary": dossier.executive_summary,
                    "points_of_consensus": dossier.points_of_consensus,
                    "points_of_friction": dossier.points_of_friction,
                    "actionable_coaching_milestones": dossier.actionable_coaching_milestones,
                    "reflexion_iterations": dossier.reflexion_iterations,
                    "reflexion_critiques": [c.model_dump() for c in dossier.reflexion_critiques],
                    "debate_transcript_count": len(dossier.debate_transcript),
                    "transcript_summary": [
                        {
                            "speaker": t.speaker.value,
                            "round": t.round_number,
                            "statement": t.statement,
                        }
                        for t in dossier.debate_transcript
                    ],
                }

                return ToolCallResult(
                    content=[{"type": "text", "text": json.dumps(res_payload, indent=2)}],
                    isError=False,
                )

            elif name == "start_durable_workflow":
                jur_str = arguments.get("jurisdiction", "UNITED_STATES").upper()
                jur = (
                    Jurisdiction.BRAZIL
                    if "BRAZIL" in jur_str
                    else (
                        Jurisdiction.CANADA if "CANADA" in jur_str else Jurisdiction.UNITED_STATES
                    )
                )

                emp = EmployeeProfile(
                    employee_id=arguments.get("employee_id", "EMP-DUR-01"),
                    name=arguments.get("name", "Elena Rostova"),
                    email=f"{arguments.get('name', 'elena').lower().replace(' ', '.')}@enterprise.internal",
                    department="Core Infrastructure",
                    job_title="Senior Software Engineer",
                    level=arguments.get("level", "IC4"),
                    jurisdiction=jur,
                    manager_id="MGR-MCP-01",
                    base_salary=Decimal(str(arguments.get("base_salary", 175000.0))),
                    currency=arguments.get("currency", "USD"),
                    compa_ratio=Decimal("0.95"),
                    performance_rating=arguments.get("performance_rating", "EXCEEDS"),
                    tenure_months=int(arguments.get("tenure_months", 20)),
                )

                wf_id = f"wf-mcp-dur-{uuid.uuid4().hex[:8]}"
                state = MeshState(
                    workflow_id=wf_id,
                    workflow_type=WorkflowType.FULL_TALENT_DOSSIER,
                    jurisdiction=jur,
                    employee=emp,
                    requester_id="REQ-MCP",
                    requester_role="HRBP_LEAD",
                )

                res_state = self.durable_engine.start_workflow(state)
                events = self.durable_store.get_events(wf_id)
                output_payload: dict[str, Any] = {
                    "workflow_id": wf_id,
                    "status": res_state.status.value,
                    "events_logged": len(events),
                    "suspended_for_hitl": res_state.status.value == "AWAITING_HUMAN_APPROVAL",
                    "required_role": (
                        res_state.approval_request.required_role
                        if res_state.approval_request
                        else "NONE"
                    ),
                    "risk_score": (
                        res_state.approval_request.risk_score if res_state.approval_request else 0.0
                    ),
                }
                return ToolCallResult(
                    content=[{"type": "text", "text": json.dumps(output_payload, indent=2)}],
                    isError=False,
                )

            elif name == "signal_durable_workflow":
                wf_id = arguments["workflow_id"]
                decision = arguments.get("decision", "APPROVED")
                decided_by = arguments.get("decided_by", "vp.engineering@enterprise.internal")
                comments = arguments.get("comments", "Endorsed via MCP.")

                res_state = self.durable_engine.signal_workflow(
                    workflow_id=wf_id,
                    signal_name="HUMAN_DECISION",
                    payload={
                        "decision": decision,
                        "decided_by": decided_by,
                        "comments": comments,
                    },
                )
                events = self.durable_store.get_events(wf_id)
                output_payload_sig: dict[str, Any] = {
                    "workflow_id": wf_id,
                    "status": res_state.status.value,
                    "final_events_count": len(events),
                    "approval_status": (
                        res_state.approval_request.status.value
                        if res_state.approval_request
                        else "NONE"
                    ),
                }
                return ToolCallResult(
                    content=[{"type": "text", "text": json.dumps(output_payload_sig, indent=2)}],
                    isError=False,
                )

            elif name == "get_durable_workflow_history":
                wf_id = arguments["workflow_id"]
                events = self.durable_store.get_events(wf_id)
                output_payload_hist: dict[str, Any] = {
                    "workflow_id": wf_id,
                    "total_events": len(events),
                    "timeline": [
                        {
                            "seq": e.sequence_number,
                            "type": e.event_type.value,
                            "timestamp": e.timestamp.isoformat(),
                            "checksum": e.checksum,
                            "payload_keys": list(e.payload.keys()),
                        }
                        for e in events
                    ],
                }
                return ToolCallResult(
                    content=[{"type": "text", "text": json.dumps(output_payload_hist, indent=2)}],
                    isError=False,
                )

            elif name == "replay_durable_workflow":
                wf_id = arguments["workflow_id"]
                replayed_state, count = self.durable_engine.replay_workflow(wf_id)
                output_payload_replay: dict[str, Any] = {
                    "workflow_id": wf_id,
                    "replayed_events_count": count,
                    "reconstructed_status": replayed_state.status.value,
                    "parity_verified": True,
                }
                return ToolCallResult(
                    content=[{"type": "text", "text": json.dumps(output_payload_replay, indent=2)}],
                    isError=False,
                )

            else:
                return ToolCallResult(
                    content=[{"type": "text", "text": f"Unknown tool: {name}"}],
                    isError=True,
                )

        except Exception as e:
            return ToolCallResult(
                content=[{"type": "text", "text": f"Error executing tool '{name}': {e!s}"}],
                isError=True,
            )

    # --- JSON-RPC 2.0 Request Dispatcher ---

    def handle_message(self, message: dict[str, Any] | JSONRPCRequest) -> dict[str, Any] | None:
        """
        Processes an incoming JSON-RPC 2.0 message. Returns response dict or None for notifications.
        """
        if isinstance(message, dict):
            try:
                req = JSONRPCRequest.model_validate(message)
            except Exception as e:
                return JSONRPCResponse(
                    id=message.get("id"),
                    error=JSONRPCError(
                        code=INVALID_REQUEST, message=f"Invalid JSON-RPC request: {e}"
                    ),
                ).model_dump_clean()
        else:
            req = message

        msg_id = req.id
        method = req.method
        params = req.params or {}

        # 1. Notifications (no response expected)
        if method == "notifications/initialized":
            return None

        # 2. Ping
        if method == "ping":
            return JSONRPCResponse(id=msg_id, result={}).model_dump_clean()

        # 3. Initialize
        if method == "initialize":
            result = {
                "protocolVersion": LATEST_PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False},
                    "prompts": {"listChanged": False},
                },
                "serverInfo": {
                    "name": self.SERVER_NAME,
                    "version": self.SERVER_VERSION,
                },
                "instructions": (
                    "PeopleAgentMesh MCP Server provides deterministic compensation modeling, "
                    "Brazilian CLT Art. 468 labor compliance checks, and zero-retention PII tokenization."
                ),
            }
            return JSONRPCResponse(id=msg_id, result=result).model_dump_clean()

        # 4. Tools
        if method == "tools/list":
            tools = [t.model_dump() for t in self.list_tools()]
            return JSONRPCResponse(id=msg_id, result={"tools": tools}).model_dump_clean()

        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            if not tool_name:
                return JSONRPCResponse(
                    id=msg_id,
                    error=JSONRPCError(code=INVALID_PARAMS, message="Missing 'name' in tools/call"),
                ).model_dump_clean()

            res = self.call_tool(tool_name, arguments)
            return JSONRPCResponse(id=msg_id, result=res.model_dump()).model_dump_clean()

        # 5. Resources
        if method == "resources/list":
            resources = [r.model_dump() for r in self.list_resources()]
            return JSONRPCResponse(id=msg_id, result={"resources": resources}).model_dump_clean()

        if method == "resources/read":
            uri = params.get("uri")
            if not uri:
                return JSONRPCResponse(
                    id=msg_id,
                    error=JSONRPCError(
                        code=INVALID_PARAMS, message="Missing 'uri' in resources/read"
                    ),
                ).model_dump_clean()
            try:
                content = self.read_resource(uri)
                return JSONRPCResponse(
                    id=msg_id,
                    result={"contents": [content.model_dump(exclude_none=True)]},
                ).model_dump_clean()
            except KeyError as ke:
                return JSONRPCResponse(
                    id=msg_id,
                    error=JSONRPCError(code=INVALID_PARAMS, message=str(ke)),
                ).model_dump_clean()

        # 6. Prompts
        if method == "prompts/list":
            prompts = [p.model_dump() for p in self.list_prompts()]
            return JSONRPCResponse(id=msg_id, result={"prompts": prompts}).model_dump_clean()

        if method == "prompts/get":
            prompt_name = params.get("name")
            arguments = params.get("arguments", {})
            if not prompt_name:
                return JSONRPCResponse(
                    id=msg_id,
                    error=JSONRPCError(
                        code=INVALID_PARAMS, message="Missing 'name' in prompts/get"
                    ),
                ).model_dump_clean()
            try:
                messages = self.get_prompt(prompt_name, arguments)
                return JSONRPCResponse(
                    id=msg_id,
                    result={"messages": [m.model_dump() for m in messages]},
                ).model_dump_clean()
            except KeyError as ke:
                return JSONRPCResponse(
                    id=msg_id,
                    error=JSONRPCError(code=INVALID_PARAMS, message=str(ke)),
                ).model_dump_clean()

        # Unknown method
        return JSONRPCResponse(
            id=msg_id,
            error=JSONRPCError(code=METHOD_NOT_FOUND, message=f"Method '{method}' not found"),
        ).model_dump_clean()
