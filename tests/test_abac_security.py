from typing import Any

from people_agent_mesh.security.abac import (
    ABACSecurityEngine,
    ReportingHierarchy,
    RequesterContext,
)


def test_reporting_hierarchy_resolution() -> None:
    # Hierarchy: MGR-1 -> [LEAD-1], LEAD-1 -> [DEV-1, DEV-2]
    hierarchy = ReportingHierarchy(
        {
            "MGR-1": ["LEAD-1"],
            "LEAD-1": ["DEV-1", "DEV-2"],
            "MGR-2": ["DEV-3"],
        }
    )

    # Direct report
    assert hierarchy.is_in_reporting_tree("LEAD-1", "DEV-1") is True
    # Transitive report
    assert hierarchy.is_in_reporting_tree("MGR-1", "DEV-1") is True
    assert hierarchy.is_in_reporting_tree("MGR-1", "DEV-2") is True
    # Non-report
    assert hierarchy.is_in_reporting_tree("MGR-1", "DEV-3") is False
    assert hierarchy.is_in_reporting_tree("LEAD-1", "DEV-3") is False


def test_abac_access_control() -> None:
    hierarchy = ReportingHierarchy(
        {
            "MGR-1": ["EMP-A"],
            "MGR-2": ["EMP-B"],
        }
    )
    engine = ABACSecurityEngine(hierarchy)

    mgr1_ctx = RequesterContext(user_id="MGR-1", role="PEOPLE_MANAGER", department="Engineering")
    vp_ctx = RequesterContext(
        user_id="EXEC-1", role="PEOPLE_VP", department="People", is_executive=True
    )
    comp_ctx = RequesterContext(user_id="COMP-1", role="COMP_PARTNER", department="Total Rewards")

    # MGR-1 can access EMP-A
    assert engine.can_access_employee_data(mgr1_ctx, "EMP-A") is True
    # MGR-1 cannot access EMP-B
    assert engine.can_access_employee_data(mgr1_ctx, "EMP-B") is False

    # VP can access any employee
    assert engine.can_access_employee_data(vp_ctx, "EMP-A") is True
    assert engine.can_access_employee_data(vp_ctx, "EMP-B") is True

    # Compensation Partner can access compensation data
    assert engine.can_access_employee_data(comp_ctx, "EMP-B", is_compensation_data=True) is True


def test_document_security_trimming() -> None:
    hierarchy = ReportingHierarchy({"MGR-1": ["EMP-A"]})
    engine = ABACSecurityEngine(hierarchy)

    mgr1_ctx = RequesterContext(user_id="MGR-1", role="PEOPLE_MANAGER", department="Engineering")

    docs: list[dict[str, Any]] = [
        {"id": "doc-1", "title": "Company Promotion Guidelines", "classification": "PUBLIC"},
        {
            "id": "doc-2",
            "subject_employee_id": "EMP-A",
            "title": "1-on-1 Notes",
            "classification": "INTERNAL",
        },
        {
            "id": "doc-3",
            "subject_employee_id": "EMP-B",
            "title": "1-on-1 Notes Peer",
            "classification": "INTERNAL",
        },
        {
            "id": "doc-4",
            "subject_employee_id": "EMP-A",
            "is_compensation": True,
            "classification": "RESTRICTED_SPII",
        },
    ]

    filtered = engine.security_trim_documents(mgr1_ctx, docs)
    doc_ids = [d["id"] for d in filtered]

    # Doc 1 (public) and Doc 2 (direct report internal) should be included
    assert "doc-1" in doc_ids
    assert "doc-2" in doc_ids
    # Doc 3 (peer report) and Doc 4 (restricted SPII) must be trimmed out!
    assert "doc-3" not in doc_ids
    assert "doc-4" not in doc_ids
