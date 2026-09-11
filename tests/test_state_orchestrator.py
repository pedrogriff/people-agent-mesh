from decimal import Decimal

from people_agent_mesh.core.state import (
    EmployeeProfile,
    Jurisdiction,
    MeshState,
    WorkflowStatus,
    WorkflowType,
)


def test_mesh_state_snapshot_serialization() -> None:
    emp = EmployeeProfile(
        employee_id="EMP-100",
        name="Rodrigo Santos",
        email="rodrigo@nubank.internal",
        department="Platform Engineering",
        job_title="Software Engineer",
        level="IC4",
        jurisdiction=Jurisdiction.BRAZIL,
        manager_id="MGR-99",
        base_salary=Decimal("180000.00"),
        currency="BRL",
        compa_ratio=Decimal("0.85"),
        performance_rating="EXCEEDS",
        tenure_months=18,
    )

    state = MeshState(
        workflow_id="WF-TEST-001",
        workflow_type=WorkflowType.COMPENSATION_REVIEW,
        jurisdiction=Jurisdiction.BRAZIL,
        employee=emp,
        requester_id="MGR-99",
        requester_role="PEOPLE_MANAGER",
    )

    state = state.record_audit("TestActor", "TEST_ACTION", {"key": "value"})
    assert len(state.audit_trail) == 1
    assert state.audit_trail[0].action == "TEST_ACTION"

    # Test serialization roundtrip
    snapshot = state.to_snapshot()
    hydrated = MeshState.from_snapshot(snapshot)

    assert hydrated.workflow_id == state.workflow_id
    assert hydrated.employee.employee_id == "EMP-100"
    assert hydrated.employee.base_salary == Decimal("180000.00")
    assert hydrated.status == WorkflowStatus.INITIATED
    assert len(hydrated.audit_trail) == 1
