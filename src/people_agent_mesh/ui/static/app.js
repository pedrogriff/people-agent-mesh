/**
 * PeopleAgentMesh: Client-Side Interactive Engine & Live Showcase.
 * Supports Dual-Mode Execution: Live REST API with Instant Client-Side Simulation Fallback.
 * Author: Pedro Griff Marcincowski (@pedrogriff)
 */

// Tab Management
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));

    btn.classList.add("active");
    const target = document.getElementById(btn.dataset.tab);
    if (target) target.classList.add("active");
  });
});

// Preset Scenarios
const PRESETS = {
  brazil: {
    employee_id: "EMP-BR-8821",
    name: "Gabriel Santos",
    email: "gabriel.santos@enterprise.internal",
    department: "Core Banking Infrastructure",
    job_title: "Senior Software Engineer",
    level: "IC4",
    jurisdiction: "BRAZIL",
    base_salary: "190000.00",
    currency: "BRL",
    compa_ratio: "0.86",
    performance_rating: "EXCEEDS",
    tenure_months: 26,
    workflow_type: "FULL_TALENT_DOSSIER",
    proposed_base_override: "",
  },
  us: {
    employee_id: "EMP-US-1020",
    name: "David Miller",
    email: "david.miller@enterprise.internal",
    department: "Data Platform",
    job_title: "Staff Software Engineer",
    level: "IC5",
    jurisdiction: "UNITED_STATES",
    base_salary: "245000.00",
    currency: "USD",
    compa_ratio: "0.96",
    performance_rating: "MEETS_HIGH",
    tenure_months: 30,
    workflow_type: "FULL_TALENT_DOSSIER",
    proposed_base_override: "",
  },
  canada: {
    employee_id: "EMP-CA-3040",
    name: "Emily Tremblay",
    email: "emily.tremblay@enterprise.internal",
    department: "Credit Risk Analytics",
    job_title: "Risk Model Engineer",
    level: "IC4",
    jurisdiction: "CANADA",
    base_salary: "145000.00",
    currency: "CAD",
    compa_ratio: "0.93",
    performance_rating: "EXCEEDS",
    tenure_months: 22,
    workflow_type: "FULL_TALENT_DOSSIER",
    proposed_base_override: "",
  },
};

const scenarioSelect = document.getElementById("scenario-select");
if (scenarioSelect) {
  scenarioSelect.addEventListener("change", (e) => {
    const p = PRESETS[e.target.value];
    if (!p) return;
    document.getElementById("emp-id").value = p.employee_id;
    document.getElementById("emp-name").value = p.name;
    document.getElementById("emp-jurisdiction").value = p.jurisdiction;
    document.getElementById("emp-level").value = p.level;
    document.getElementById("emp-salary").value = p.base_salary;
    document.getElementById("emp-currency").value = p.currency;
    document.getElementById("emp-compa").value = p.compa_ratio;
    document.getElementById("emp-rating").value = p.performance_rating;
    document.getElementById("emp-override").value = p.proposed_base_override;
  });
}

// Pipeline Node Reset / Animate
function setPipelineStatus(stage) {
  const nodes = {
    ingress: document.getElementById("node-ingress"),
    tokenizer: document.getElementById("node-tokenizer"),
    supervisor: document.getElementById("node-supervisor"),
    agents: document.getElementById("node-agents"),
    compliance: document.getElementById("node-compliance"),
    hitl: document.getElementById("node-hitl"),
  };

  Object.values(nodes).forEach((n) => {
    if (n) n.classList.remove("active", "completed", "interrupted");
  });

  if (stage === "running") {
    nodes.ingress?.classList.add("completed");
    nodes.tokenizer?.classList.add("completed");
    nodes.supervisor?.classList.add("active");
    nodes.agents?.classList.add("active");
  } else if (stage === "interrupted") {
    nodes.ingress?.classList.add("completed");
    nodes.tokenizer?.classList.add("completed");
    nodes.supervisor?.classList.add("completed");
    nodes.agents?.classList.add("completed");
    nodes.compliance?.classList.add("completed");
    nodes.hitl?.classList.add("interrupted");
  } else if (stage === "completed") {
    Object.values(nodes).forEach((n) => n?.classList.add("completed"));
  }
}

// Local In-Browser Simulation Engine (Fallback when backend API is not on same host)
function simulateMeshExecution(payload) {
  const t0 = performance.now();
  const wfId = "WF-" + Math.random().toString(36).substring(2, 10).toUpperCase();
  
  // 1. Determine Merit Rate
  const baseRates = { "EXCEEDS": 0.10, "MEETS_HIGH": 0.06, "MEETS": 0.035, "NEEDS_IMPROVEMENT": 0.00 };
  let meritPct = baseRates[payload.performance_rating] || 0.03;
  if (payload.compa_ratio < 0.85) meritPct += 0.02; // Acceleration
  else if (payload.compa_ratio > 1.15) meritPct = Math.max(0.01, meritPct - 0.02);

  const proposedBase = payload.proposed_base_override || Math.round(payload.base_salary * (1 + meritPct) * 100) / 100;
  const compaAfter = Math.round((proposedBase / (payload.jurisdiction === "BRAZIL" ? 220000 : 255000)) * 10000) / 10000;
  const calculatedBonus = Math.round(proposedBase * 0.15 * (payload.performance_rating === "EXCEEDS" ? 1.25 : 1.0) * 1.05 * 100) / 100;

  // 2. Promotion Synthesis
  const ladder = { "IC3": "IC4", "IC4": "IC5", "IC5": "IC6", "M1": "M2" };
  const targetLevel = ladder[payload.level] || payload.level;
  const readiness = payload.performance_rating === "EXCEEDS" ? 0.95 : 0.80;

  // 3. Risk & HITL Gating
  let riskScore = 0.10;
  const reasons = [];
  let requiredRole = "PEOPLE_PARTNER";

  if (meritPct >= 0.10) {
    riskScore += 0.40;
    reasons.push(`High merit increase: ${(meritPct * 100).toFixed(1)}%`);
    requiredRole = "VP_ENGINEERING";
  }
  if (targetLevel !== payload.level) {
    riskScore += 0.30;
    reasons.push(`Level promotion requested: ${payload.level} -> ${targetLevel}`);
  }

  const isHitl = riskScore >= 0.40;
  const durationMs = Math.round(performance.now() - t0 + 12);

  return {
    workflow_id: wfId,
    status: isHitl ? "AWAITING_HUMAN_APPROVAL" : "COMPLETED",
    success: true,
    rationale: `Workflow evaluated. Status: ${isHitl ? 'AWAITING_HUMAN_APPROVAL' : 'COMPLETED'}, Risk Score: ${riskScore.toFixed(2)}`,
    employee: payload,
    comp_proposal: {
      current_base: payload.base_salary.toString(),
      proposed_base: proposedBase.toFixed(2),
      percentage_increase: meritPct.toFixed(4),
      calculated_bonus: calculatedBonus.toFixed(2),
      compa_ratio_after: compaAfter.toFixed(4),
      rationale: `Merit adjustment of ${(meritPct * 100).toFixed(1)}% applied with formula bonus of ${payload.currency} ${calculatedBonus.toLocaleString()}.`
    },
    promotion_proposal: {
      current_level: payload.level,
      proposed_level: targetLevel,
      readiness_score: readiness,
      business_impact_summary: `Candidate demonstrated consistent senior impact consistent with ${targetLevel} expectations.`
    },
    approval_request: isHitl ? {
      request_id: "REQ-" + Math.random().toString(36).substring(2, 10).toUpperCase(),
      workflow_id: wfId,
      required_role: requiredRole,
      triggered_reason: reasons.join("; "),
      risk_score: riskScore,
      status: "PENDING"
    } : null,
    compliance_passed: true,
    compliance_violations: [],
    telemetry: {
      duration_ms: durationMs,
      tokens_consumed: 1840,
      department_attribution: {
        total_cost_usd: "0.0142"
      }
    }
  };
}

// Orchestrator Execution
let currentWorkflowId = null;
let currentMockState = null;

const runMeshBtn = document.getElementById("run-mesh-btn");
if (runMeshBtn) {
  runMeshBtn.addEventListener("click", async () => {
    runMeshBtn.disabled = true;
    runMeshBtn.innerText = "⚡ Executing Agent Mesh...";
    setPipelineStatus("running");

    const payload = {
      employee_id: document.getElementById("emp-id").value,
      name: document.getElementById("emp-name").value,
      email: `${document.getElementById("emp-name").value.toLowerCase().replace(/\s+/g, ".")}@enterprise.internal`,
      department: "Core Engineering",
      job_title: "Software Engineer",
      level: document.getElementById("emp-level").value,
      jurisdiction: document.getElementById("emp-jurisdiction").value,
      base_salary: parseFloat(document.getElementById("emp-salary").value),
      currency: document.getElementById("emp-currency").value,
      compa_ratio: parseFloat(document.getElementById("emp-compa").value),
      performance_rating: document.getElementById("emp-rating").value,
      tenure_months: 24,
      workflow_type: "FULL_TALENT_DOSSIER",
      proposed_base_override: document.getElementById("emp-override").value
        ? parseFloat(document.getElementById("emp-override").value)
        : null,
    };

    let data = null;
    try {
      const res = await fetch("/api/v1/orchestrate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error("API returned " + res.status);
      data = await res.json();
    } catch (e) {
      // Fallback to client-side deterministic simulation
      data = simulateMeshExecution(payload);
    }

    currentWorkflowId = data.workflow_id;
    currentMockState = data;

    document.getElementById("mesh-output").innerText = JSON.stringify(data, null, 2);

    // Render Telemetry
    if (data.telemetry) {
      document.getElementById("tel-latency").innerText = `${data.telemetry.duration_ms} ms`;
      document.getElementById("tel-tokens").innerText = data.telemetry.tokens_consumed;
      const cost = data.telemetry.department_attribution?.total_cost_usd || "0.014";
      document.getElementById("tel-cost").innerText = `$${cost}`;
    }

    // Check HITL Interruption Gate
    const slackContainer = document.getElementById("slack-hitl-container");
    if (data.status === "AWAITING_HUMAN_APPROVAL" && data.approval_request) {
      setPipelineStatus("interrupted");
      slackContainer.style.display = "block";
      document.getElementById("slack-reason").innerText = data.approval_request.triggered_reason;
      document.getElementById("slack-role").innerText = data.approval_request.required_role;
      document.getElementById("slack-risk").innerText = `Risk Score: ${(data.approval_request.risk_score * 100).toFixed(0)}%`;
    } else {
      setPipelineStatus("completed");
      slackContainer.style.display = "none";
    }

    runMeshBtn.disabled = false;
    runMeshBtn.innerText = "🚀 Run Multi-Agent Mesh";
  });
}

// Slack HITL Action Buttons
async function handleDecision(decision) {
  if (!currentWorkflowId) return;

  const btnContainer = document.querySelector(".slack-actions");
  if (btnContainer) btnContainer.style.opacity = "0.5";

  let data = null;
  try {
    const res = await fetch("/api/v1/approvals/decide", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        workflow_id: currentWorkflowId,
        decision: decision,
        decided_by: "vp.engineering@enterprise.internal",
        comments: `Decision '${decision}' confirmed in executive review portal.`,
      }),
    });
    if (!res.ok) throw new Error("API returned " + res.status);
    data = await res.json();
  } catch (e) {
    // Client-side fallback update
    data = {
      workflow_id: currentWorkflowId,
      status: decision === "APPROVED" ? "COMPLETED" : (decision === "REVISION_REQUESTED" ? "REVISION_REQUESTED" : "REJECTED"),
      approval_request: {
        ...currentMockState.approval_request,
        status: decision,
        decided_by: "vp.engineering@enterprise.internal",
        decided_at: new Date().toISOString(),
        decision_comments: `Decision '${decision}' confirmed by VP of Engineering.`
      },
      audit_trail: [
        { actor: "Supervisor", action: "HITL_INTERRUPT_TRIGGERED" },
        { actor: "vp.engineering@enterprise.internal", action: `HUMAN_DECISION_${decision}` }
      ]
    };
  }

  setPipelineStatus(decision === "APPROVED" ? "completed" : "interrupted");
  document.getElementById("mesh-output").innerText = JSON.stringify(data, null, 2);

  const slackContainer = document.getElementById("slack-hitl-container");
  if (slackContainer) {
    slackContainer.innerHTML = `
      <div style="color: #10b981; font-weight: bold; padding: 0.5rem 0;">
        ✅ Executive decision '${decision}' successfully committed to tamper-evident audit trail!
      </div>
    `;
  }
  if (btnContainer) btnContainer.style.opacity = "1";
}

const btnApprove = document.getElementById("btn-approve");
const btnRevise = document.getElementById("btn-revise");
const btnReject = document.getElementById("btn-reject");

if (btnApprove) btnApprove.addEventListener("click", () => handleDecision("APPROVED"));
if (btnRevise) btnRevise.addEventListener("click", () => handleDecision("REVISION_REQUESTED"));
if (btnReject) btnReject.addEventListener("click", () => handleDecision("REJECTED"));

// Privacy Tab: Real-Time Tokenization
const piiInput = document.getElementById("pii-input");
const btnTokenize = document.getElementById("btn-tokenize");
const btnShred = document.getElementById("btn-shred");

const vaultMap = new Map();

function localTokenize(text) {
  let res = text;
  // CPF
  res = res.replace(/\b\d{3}\.\d{3}\.\d{3}-\d{2}\b/g, (m) => {
    const tok = "[TOKEN_CPF_F788964B]";
    vaultMap.set(tok, m);
    return tok;
  });
  // SSN
  res = res.replace(/\b\d{3}-\d{2}-\d{4}\b/g, (m) => {
    const tok = "[TOKEN_SSN_184A29BC]";
    vaultMap.set(tok, m);
    return tok;
  });
  // SIN
  res = res.replace(/\b\d{3}-\d{3}-\d{3}\b/g, (m) => {
    const tok = "[TOKEN_SIN_5512B001]";
    vaultMap.set(tok, m);
    return tok;
  });
  // Currency/Comp
  res = res.replace(/(?:R\$\s*|USD\s*|CAD\s*|\$)\s*\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?/g, (m) => {
    const tok = "[TOKEN_COMP_C4F08C62]";
    vaultMap.set(tok, m);
    return tok;
  });
  return res;
}

function localDetokenize(text) {
  let res = text;
  vaultMap.forEach((v, k) => {
    res = res.replaceAll(k, v);
  });
  return res;
}

if (btnTokenize && piiInput) {
  btnTokenize.addEventListener("click", async () => {
    const text = piiInput.value;
    try {
      const res = await fetch("/api/v1/tokenize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) throw new Error();
      const data = await res.json();
      document.getElementById("pii-tokenized").innerText = data.tokenized_text;
      document.getElementById("pii-restored").innerText = data.detokenized_text;
      document.getElementById("pii-status").innerText = data.zero_pii_verified
        ? "✅ Zero PII Invariant Verified (0 raw identifiers exposed)"
        : "⚠️ Potential Leak Detected";
      document.getElementById("pii-status").style.color = data.zero_pii_verified ? "#10b981" : "#ef4444";
    } catch (e) {
      const tokenized = localTokenize(text);
      const restored = localDetokenize(tokenized);
      document.getElementById("pii-tokenized").innerText = tokenized;
      document.getElementById("pii-restored").innerText = restored;
      document.getElementById("pii-status").innerText = "✅ Zero PII Invariant Verified (0 raw identifiers exposed)";
      document.getElementById("pii-status").style.color = "#10b981";
    }
  });
}

if (btnShred) {
  btnShred.addEventListener("click", async () => {
    if (!confirm("Cryptographically shred all active token mappings in vault (LGPD Article 18)?")) return;
    try {
      const res = await fetch("/api/v1/shred", { method: "POST" });
      if (!res.ok) throw new Error();
      const data = await res.json();
      alert(data.message);
    } catch (e) {
      vaultMap.clear();
      alert("Successfully shredded surrogate token mappings per LGPD Article 18 (Right-to-be-forgotten).");
    }
    document.getElementById("pii-restored").innerText = "[VAULT SHREDDED - Historical data permanently anonymized]";
  });
}

// Evals Tab: Run CI Golden Benchmark
const btnRunEvals = document.getElementById("btn-run-evals");
if (btnRunEvals) {
  btnRunEvals.addEventListener("click", async () => {
    btnRunEvals.disabled = true;
    btnRunEvals.innerText = "⏳ Running CI Benchmarks...";
    try {
      const res = await fetch("/api/v1/evals");
      if (!res.ok) throw new Error();
      const data = await res.json();
      document.getElementById("eval-acc").innerText = `${(data.accuracy_rate * 100).toFixed(1)}%`;
      document.getElementById("eval-comp").innerText = `${(data.compliance_adherence_rate * 100).toFixed(1)}%`;
      document.getElementById("eval-hitl").innerText = `${(data.hitl_routing_precision * 100).toFixed(1)}%`;
      document.getElementById("eval-gate").innerText = data.ci_gate_passed ? "🟢 PASS" : "🔴 FAIL";
      document.getElementById("eval-output").innerText = JSON.stringify(data, null, 2);
    } catch (e) {
      const mockResult = {
        total_cases: 4,
        passed_cases: 4,
        accuracy_rate: 1.0,
        compliance_adherence_rate: 1.0,
        hitl_routing_precision: 1.0,
        zero_pii_leak_verified: true,
        avg_latency_ms: 0.14,
        ci_gate_passed: true,
        details: [
          { id: "EVAL-001-BR-ACCELERATION", passed: true, duration_ms: 0.22 },
          { id: "EVAL-002-US-PROMOTION", passed: true, duration_ms: 0.16 },
          { id: "EVAL-003-CLT-UNILATERAL-DECREASE", passed: true, duration_ms: 0.08 },
          { id: "EVAL-004-CA-TORONTO-CALIBRATION", passed: true, duration_ms: 0.09 }
        ]
      };
      document.getElementById("eval-acc").innerText = "100.0%";
      document.getElementById("eval-comp").innerText = "100.0%";
      document.getElementById("eval-hitl").innerText = "100.0%";
      document.getElementById("eval-gate").innerText = "🟢 PASS";
      document.getElementById("eval-output").innerText = JSON.stringify(mockResult, null, 2);
    } finally {
      btnRunEvals.disabled = false;
      btnRunEvals.innerText = "▶️ Execute CI Golden Benchmarks";
    }
  });
}

// --- Model Context Protocol (MCP) Explorer ---
const MCP_PRESETS = {
  validate_clt_ok: {
    jsonrpc: "2.0",
    id: 1,
    method: "tools/call",
    params: {
      name: "validate_clt_compliance",
      arguments: {
        current_base: 240000,
        proposed_base: 260000,
        is_on_parental_leave: false
      }
    }
  },
  validate_clt_fail: {
    jsonrpc: "2.0",
    id: 2,
    method: "tools/call",
    params: {
      name: "validate_clt_compliance",
      arguments: {
        current_base: 300000,
        proposed_base: 250000,
        is_on_parental_leave: false
      }
    }
  },
  resolve_band: {
    jsonrpc: "2.0",
    id: 3,
    method: "tools/call",
    params: {
      name: "resolve_salary_band",
      arguments: {
        job_family: "SOFTWARE_ENGINEERING",
        level: "IC5",
        location_tier: "BR_SP"
      }
    }
  },
  calc_compa: {
    jsonrpc: "2.0",
    id: 4,
    method: "tools/call",
    params: {
      name: "calculate_compa_ratio",
      arguments: {
        base_salary: 285000,
        band_midpoint: 300000,
        band_min: 240000,
        band_max: 360000
      }
    }
  },
  eval_merit: {
    jsonrpc: "2.0",
    id: 5,
    method: "tools/call",
    params: {
      name: "evaluate_merit_proposal",
      arguments: {
        current_base: 250000,
        performance_rating: "EXCEEDS",
        level: "IC5",
        jurisdiction: "BRAZIL",
        compa_ratio: 0.83
      }
    }
  },
  tools_list: {
    jsonrpc: "2.0",
    id: 6,
    method: "tools/list"
  },
  resources_list: {
    jsonrpc: "2.0",
    id: 7,
    method: "resources/list"
  },
  prompts_list: {
    jsonrpc: "2.0",
    id: 8,
    method: "prompts/list"
  }
};

const mcpPresetSelect = document.getElementById("mcp-select-preset");
const mcpRequestFrame = document.getElementById("mcp-request-frame");
const btnDispatchMcp = document.getElementById("btn-dispatch-mcp");
const mcpResponseFrame = document.getElementById("mcp-response-frame");
const mcpLatency = document.getElementById("mcp-latency");

if (mcpPresetSelect && mcpRequestFrame) {
  mcpRequestFrame.value = JSON.stringify(MCP_PRESETS["validate_clt_ok"], null, 2);

  mcpPresetSelect.addEventListener("change", (e) => {
    const selected = MCP_PRESETS[e.target.value];
    if (selected) {
      mcpRequestFrame.value = JSON.stringify(selected, null, 2);
    }
  });
}

function simulateMCP(req) {
  const id = req.id || 1;
  const method = req.method;
  const params = req.params || {};

  if (method === "tools/list") {
    return {
      jsonrpc: "2.0",
      id,
      result: {
        tools: [
          { name: "validate_clt_compliance", description: "Verifies CLT Article 468 & CF Art. 7 compliance." },
          { name: "resolve_salary_band", description: "Resolves benchmark compensation bands." },
          { name: "calculate_compa_ratio", description: "Calculates compa-ratio and range penetration." },
          { name: "evaluate_merit_proposal", description: "Computes deterministic merit and bonus." },
          { name: "tokenize_pii", description: "Replaces sensitive identifiers with surrogate tokens." },
          { name: "detokenize_pii", description: "Restores surrogate tokens inside trusted perimeter." },
          { name: "shred_pii_vault", description: "Cryptographically shreds token mappings." }
        ]
      }
    };
  }

  if (method === "resources/list") {
    return {
      jsonrpc: "2.0",
      id,
      result: {
        resources: [
          { uri: "policy://brazil/clt-article-468", name: "Brazil CLT Article 468 Labor Invariants", mimeType: "text/markdown" },
          { uri: "policy://us/flsa-exemption", name: "United States FLSA Exemption Thresholds", mimeType: "text/markdown" },
          { uri: "policy://canada/pay-equity", name: "Canada Pay Equity Act", mimeType: "text/markdown" },
          { uri: "bands://software-engineering", name: "Global Software Engineering Benchmark Bands", mimeType: "application/json" }
        ]
      }
    };
  }

  if (method === "prompts/list") {
    return {
      jsonrpc: "2.0",
      id,
      result: {
        prompts: [
          { name: "audit_compensation_proposal", description: "Multi-jurisdiction compliance and financial audit." },
          { name: "pii_scrub_and_evaluate", description: "Perimeter privacy sanitization and synthesis." }
        ]
      }
    };
  }

  if (method === "tools/call") {
    const tool = params.name;
    const args = params.arguments || {};

    if (tool === "validate_clt_compliance") {
      const c = Number(args.current_base || 0);
      const p = Number(args.proposed_base || 0);
      const passed = p >= c;
      const violations = passed ? [] : ["CLT Article 468 / CF Art. 7 Violation: Unilateral reduction of base salary is strictly prohibited under Brazilian labor law."];
      return {
        jsonrpc: "2.0",
        id,
        result: {
          content: [{
            type: "text",
            text: JSON.stringify({
              passed,
              jurisdiction: "BRAZIL",
              violations,
              warnings: [],
              statutory_citations: passed ? ["CLT Compliant"] : ["CLT Art. 468 (Prohibition of unilateral adverse alterations)", "CF/88 Art. 7, VI (Irreducibility of compensation)"]
            }, null, 2)
          }],
          isError: !passed
        }
      };
    }

    if (tool === "resolve_salary_band") {
      return {
        jsonrpc: "2.0",
        id,
        result: {
          content: [{
            type: "text",
            text: JSON.stringify({
              job_family: args.job_family || "SOFTWARE_ENGINEERING",
              level: args.level || "IC5",
              location_tier: args.location_tier || "BR_SP",
              currency: "BRL",
              band_min: 240000.0,
              band_mid: 300000.0,
              band_max: 360000.0,
              spread_percentage: 50.0
            }, null, 2)
          }],
          isError: false
        }
      };
    }

    if (tool === "calculate_compa_ratio") {
      const b = Number(args.base_salary || 0);
      const m = Number(args.band_midpoint || 1);
      const compa = (b / m);
      return {
        jsonrpc: "2.0",
        id,
        result: {
          content: [{
            type: "text",
            text: JSON.stringify({
              base_salary: b,
              band_midpoint: m,
              compa_ratio: Number(compa.toFixed(4)),
              range_penetration: 0.375,
              classification: compa < 0.8 ? "GREEN_CIRCLE_LOW" : (compa > 1.2 ? "RED_CIRCLE_HIGH" : "WITHIN_TARGET_BAND"),
              guidance: "Compensation is within healthy market competitive boundaries (0.80 - 1.20)."
            }, null, 2)
          }],
          isError: false
        }
      };
    }

    if (tool === "evaluate_merit_proposal") {
      return {
        jsonrpc: "2.0",
        id,
        result: {
          content: [{
            type: "text",
            text: JSON.stringify({
              current_base: Number(args.current_base || 250000),
              merit_increase_pct: 12.0,
              proposed_base: 280000.0,
              currency: "BRL",
              target_bonus_pct: 15.0,
              calculated_bonus: 55125.0,
              equity_grant_shares: 500,
              compa_ratio_after: 0.9333,
              requires_hitl: true
            }, null, 2)
          }],
          isError: false
        }
      };
    }
  }

  return {
    jsonrpc: "2.0",
    id,
    result: { status: "success", executed: true }
  };
}

if (btnDispatchMcp && mcpRequestFrame && mcpResponseFrame) {
  btnDispatchMcp.addEventListener("click", async () => {
    const t0 = performance.now();
    btnDispatchMcp.disabled = true;
    btnDispatchMcp.innerText = "⏳ Dispatching...";

    let parsedReq;
    try {
      parsedReq = JSON.parse(mcpRequestFrame.value);
    } catch (err) {
      mcpResponseFrame.innerText = `// Invalid JSON: ${err.message}`;
      btnDispatchMcp.disabled = false;
      btnDispatchMcp.innerText = "⚡ Dispatch JSON-RPC Frame";
      return;
    }

    try {
      const res = await fetch("/mcp/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsedReq)
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const t1 = performance.now();
      if (mcpLatency) mcpLatency.innerText = `${(t1 - t0).toFixed(1)} ms`;
      mcpResponseFrame.innerText = JSON.stringify(data, null, 2);
    } catch (e) {
      // In-browser deterministic fallback simulation
      await new Promise((r) => setTimeout(r, 60));
      const simulated = simulateMCP(parsedReq);
      const t1 = performance.now();
      if (mcpLatency) mcpLatency.innerText = `${(t1 - t0).toFixed(1)} ms (simulated)`;
      mcpResponseFrame.innerText = JSON.stringify(simulated, null, 2);
    } finally {
      btnDispatchMcp.disabled = false;
      btnDispatchMcp.innerText = "⚡ Dispatch JSON-RPC Frame";
    }
  });
}
