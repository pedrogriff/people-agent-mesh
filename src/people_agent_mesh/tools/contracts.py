"""
Strict Tool Contracts & Specifications.
Defines typed JSON Schema interfaces using Pydantic v2 to enforce boundary invariants
between LLM agent reasoning and enterprise microservice calls.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Any, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T", bound=BaseModel)


class ToolRiskLevel(StrEnum):
    READ_ONLY = "READ_ONLY"  # Safe to retry without side-effects
    WRITE_IDEMPOTENT = "WRITE_IDEMPOTENT"  # Requires idempotency key, safe on re-delivery
    WRITE_MUTATING = "WRITE_MUTATING"  # Mutating state, requires HITL approval gate


class ToolSpec(BaseModel):
    name: str
    description: str
    risk_level: ToolRiskLevel
    required_role: str
    timeout_seconds: float = 5.0
    max_retries: int = 2


# 1. HRIS Query Contract
class HRISQueryInput(BaseModel):
    employee_id: str = Field(description="Unique alphanumeric employee ID (e.g., 'EMP-10492')")
    include_compensation: bool = Field(
        default=False, description="Flag to include salary and equity grant data"
    )


class HRISQueryOutput(BaseModel):
    employee_id: str
    name: str
    department: str
    level: str
    tenure_months: int
    performance_rating: str
    current_base_salary: Decimal | None = None
    currency: str | None = None
    compa_ratio: Decimal | None = None


# 2. Market Band Benchmark Contract
class MarketBandInput(BaseModel):
    job_family: str = Field(description="e.g., 'SOFTWARE_ENGINEERING', 'PRODUCT_MANAGEMENT'")
    level: str = Field(description="e.g., 'IC4', 'IC5', 'IC6', 'M1'")
    location_tier: str = Field(description="e.g., 'BR_SP', 'US_NYC', 'US_REMOTE', 'CA_TORONTO'")


class MarketBandOutput(BaseModel):
    band_min: Decimal
    band_mid: Decimal
    band_max: Decimal
    currency: str
    spread: Decimal  # (max - min) / min


# 3. Document Query Contract
class DocumentQueryInput(BaseModel):
    subject_employee_id: str
    categories: list[str] = Field(
        default_factory=lambda: ["PERFORMANCE", "SLACK_KUDOS", "FEEDBACK"]
    )
    limit: int = 5


class DocumentQueryOutput(BaseModel):
    documents: list[dict[str, Any]]
    total_found: int


# 4. Slack Approval Dispatch Contract
class SlackApprovalDispatchInput(BaseModel):
    workflow_id: str
    approver_role: str
    employee_name: str
    proposed_action: str
    risk_score: float
    executive_summary: str
    callback_token: str


class SlackApprovalDispatchOutput(BaseModel):
    dispatched: bool
    channel: str
    message_ts: str
    callback_url: str
