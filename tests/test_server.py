from fastapi.testclient import TestClient

from people_agent_mesh.server import app

client = TestClient(app)


def test_health_check() -> None:
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"


def test_tokenize_and_shred_endpoints() -> None:
    text = "Employee Gabriel Santos with CPF 123.456.789-00 earns R$ 190.000,00"
    res = client.post("/api/v1/tokenize", json={"text": text})
    assert res.status_code == 200
    data = res.json()
    assert "[TOKEN_CPF_" in data["tokenized_text"]
    assert "[TOKEN_COMP_" in data["tokenized_text"]
    assert data["zero_pii_verified"] is True
    assert "123.456.789-00" in data["detokenized_text"]

    # Test Shred
    shred_res = client.post("/api/v1/shred")
    assert shred_res.status_code == 200
    assert shred_res.json()["shredded_count"] >= 2


def test_orchestrate_and_decision_endpoints() -> None:
    payload = {
        "employee_id": "EMP-BR-8821",
        "name": "Gabriel Santos",
        "email": "gabriel.santos@enterprise.internal",
        "department": "Core Banking",
        "job_title": "Software Engineer",
        "level": "IC4",
        "jurisdiction": "BRAZIL",
        "manager_id": "MGR-EXEC-01",
        "base_salary": 190000.00,
        "currency": "BRL",
        "compa_ratio": 0.86,
        "performance_rating": "EXCEEDS",
        "tenure_months": 26,
        "workflow_type": "FULL_TALENT_DOSSIER",
        "requester_id": "MGR-EXEC-01",
        "requester_role": "PEOPLE_MANAGER",
    }

    res = client.post("/api/v1/orchestrate", json=payload)
    assert res.status_code == 200
    data = res.json()
    wf_id = data["workflow_id"]
    assert data["status"] == "AWAITING_HUMAN_APPROVAL"
    assert data["approval_request"] is not None
    assert data["approval_request"]["required_role"] == "VP_ENGINEERING"
    assert data["comp_proposal"]["percentage_increase"] == "0.10"

    # Test Decision Endpoint
    dec_res = client.post(
        "/api/v1/approvals/decide",
        json={
            "workflow_id": wf_id,
            "decision": "APPROVED",
            "decided_by": "vp.engineering@enterprise.internal",
            "comments": "Approved via Web UI API.",
        },
    )
    assert dec_res.status_code == 200
    dec_data = dec_res.json()
    assert dec_data["status"] == "COMPLETED"
    assert dec_data["approval_request"]["status"] == "APPROVED"


def test_evals_endpoint() -> None:
    res = client.get("/api/v1/evals")
    assert res.status_code == 200
    data = res.json()
    assert data["ci_gate_passed"] is True
    assert data["total_cases"] >= 4


def test_index_html_serving() -> None:
    res = client.get("/")
    assert res.status_code == 200
    assert "PeopleAgentMesh" in res.text
