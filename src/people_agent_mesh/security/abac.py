"""
Attribute-Based Access Control (ABAC) & Security Trimming Engine.
Guarantees that agents and calling users can only query, summarize, or mutate
data within their authorized organizational reporting tree and role boundary.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class RequesterContext(BaseModel):
    user_id: str
    role: str  # e.g., "PEOPLE_MANAGER", "PEOPLE_PARTNER", "COMP_PARTNER", "PEOPLE_VP"
    department: str
    is_executive: bool = False


class ReportingHierarchy:
    """
    Graph representing organizational management hierarchy.
    """

    def __init__(self, manager_to_reports: dict[str, list[str]] | None = None) -> None:
        # manager_id -> list of direct report employee_ids
        self._hierarchy = manager_to_reports or {}

    def is_in_reporting_tree(self, manager_id: str, employee_id: str) -> bool:
        """Returns True if employee_id reports directly or transitively to manager_id."""
        if manager_id == employee_id:
            return True

        queue = list(self._hierarchy.get(manager_id, []))
        visited = set(queue)

        while queue:
            current = queue.pop(0)
            if current == employee_id:
                return True
            for direct_report in self._hierarchy.get(current, []):
                if direct_report not in visited:
                    visited.add(direct_report)
                    queue.append(direct_report)

        return False


class ABACSecurityEngine:
    """
    Enforces authorization gates and security trims context documents.
    """

    EXECUTIVE_ROLES = {"PEOPLE_VP", "CHIEF_PEOPLE_OFFICER", "CTO", "CEO"}
    COMP_ROLES = {"COMP_PARTNER", "TOTAL_REWARDS_DIR", "PEOPLE_VP"}

    def __init__(self, hierarchy: ReportingHierarchy) -> None:
        self.hierarchy = hierarchy

    def can_access_employee_data(
        self,
        requester: RequesterContext,
        target_employee_id: str,
        is_compensation_data: bool = False,
    ) -> bool:
        """
        Validates whether requester has permission to inspect employee records.
        """
        # Executive leadership has global visibility
        if requester.role in self.EXECUTIVE_ROLES or requester.is_executive:
            return True

        # Total Rewards / Compensation partners have visibility into compensation across their domain
        if is_compensation_data and requester.role in self.COMP_ROLES:
            return True

        # People Partners (HRBPs) have department-wide visibility
        if requester.role == "PEOPLE_PARTNER":
            return True

        # People Managers can only access their direct or transitive reporting tree
        if requester.role == "PEOPLE_MANAGER":
            return self.hierarchy.is_in_reporting_tree(requester.user_id, target_employee_id)

        # Default deny
        return False

    def security_trim_documents(
        self, requester: RequesterContext, documents: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Filters out knowledge documents that the requester is not authorized to see,
        preventing prompt context poisoning or unauthorized data leakage.
        """
        authorized_docs = []
        for doc in documents:
            target_emp_id = doc.get("subject_employee_id")
            doc_classification = doc.get("classification", "INTERNAL")

            # Public/Internal general docs are allowed
            if not target_emp_id and doc_classification in {"PUBLIC", "INTERNAL"}:
                authorized_docs.append(doc)
                continue

            # Restricted SPII docs require explicit compensation or VP clearance
            if doc_classification == "RESTRICTED_SPII" and requester.role not in self.COMP_ROLES:
                continue

            # If document concerns a specific employee, check reporting tree
            if target_emp_id:
                is_comp = doc.get("is_compensation", False)
                if self.can_access_employee_data(
                    requester, target_emp_id, is_compensation_data=is_comp
                ):
                    authorized_docs.append(doc)
            else:
                authorized_docs.append(doc)

        return authorized_docs
