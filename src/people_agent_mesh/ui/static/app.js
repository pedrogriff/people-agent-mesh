/**
 * PeopleAgentMesh: Interactive Showcase UI Controller.
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
    if (n) {
      n.classList.remove("active", "completed", "interrupted");
    }
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

// Orchestrator Execution
let currentWorkflowId = null;

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

    try {
      const res = await fetch("/api/v1/orchestrate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      currentWorkflowId = data.workflow_id;

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
    } catch (err) {
      document.getElementById("mesh-output").innerText = `Error: ${err.message}`;
    } finally {
      runMeshBtn.disabled = false;
      runMeshBtn.innerText = "🚀 Run Multi-Agent Mesh";
    }
  });
}

// Slack HITL Action Buttons
async function handleDecision(decision) {
  if (!currentWorkflowId) return;

  const btnContainer = document.querySelector(".slack-actions");
  if (btnContainer) btnContainer.style.opacity = "0.5";

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
    const data = await res.json();
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
  } catch (err) {
    alert(`Failed to commit decision: ${err.message}`);
  } finally {
    if (btnContainer) btnContainer.style.opacity = "1";
  }
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

if (btnTokenize && piiInput) {
  btnTokenize.addEventListener("click", async () => {
    const text = piiInput.value;
    try {
      const res = await fetch("/api/v1/tokenize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const data = await res.json();
      document.getElementById("pii-tokenized").innerText = data.tokenized_text;
      document.getElementById("pii-restored").innerText = data.detokenized_text;
      document.getElementById("pii-status").innerText = data.zero_pii_verified
        ? "✅ Zero PII Invariant Verified (0 raw identifiers exposed)"
        : "⚠️ Potential Leak Detected";
      document.getElementById("pii-status").style.color = data.zero_pii_verified ? "#10b981" : "#ef4444";
    } catch (err) {
      alert(`Tokenization error: ${err.message}`);
    }
  });
}

if (btnShred) {
  btnShred.addEventListener("click", async () => {
    if (!confirm("Cryptographically shred all active token mappings in vault (LGPD Article 18)?")) return;
    try {
      const res = await fetch("/api/v1/shred", { method: "POST" });
      const data = await res.json();
      alert(data.message);
      document.getElementById("pii-restored").innerText = "[VAULT SHREDDED - Historical data permanently anonymized]";
    } catch (err) {
      alert(`Shredding failed: ${err.message}`);
    }
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
      const data = await res.json();
      document.getElementById("eval-acc").innerText = `${(data.accuracy_rate * 100).toFixed(1)}%`;
      document.getElementById("eval-comp").innerText = `${(data.compliance_adherence_rate * 100).toFixed(1)}%`;
      document.getElementById("eval-hitl").innerText = `${(data.hitl_routing_precision * 100).toFixed(1)}%`;
      document.getElementById("eval-gate").innerText = data.ci_gate_passed ? "🟢 PASS" : "🔴 FAIL";
      document.getElementById("eval-output").innerText = JSON.stringify(data, null, 2);
    } catch (err) {
      alert(`Evals error: ${err.message}`);
    } finally {
      btnRunEvals.disabled = false;
      btnRunEvals.innerText = "▶️ Execute CI Golden Benchmarks";
    }
  });
}
