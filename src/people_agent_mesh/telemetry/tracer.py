"""
OpenTelemetry GenAI Semantic Conventions & Cost Attribution Telemetry.
Tracks multi-agent hops, latency percentiles, and departmental token budgets.
"""

from __future__ import annotations

import time
import uuid
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class GenAISpan(BaseModel):
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    agent_name: str
    workflow_id: str
    department: str
    model: str = "gpt-4o"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    duration_ms: float = 0.0
    status: str = "OK"
    attributes: dict[str, Any] = Field(default_factory=dict)
    start_time: float = Field(default_factory=time.time)


class MeshTelemetryTracer:
    """
    Distributed tracing and FinOps cost allocation aggregator.
    """

    # Model token pricing per 1k tokens (USD)
    PROMPT_COST_PER_1K = Decimal("0.0050")
    COMPLETION_COST_PER_1K = Decimal("0.0150")

    def __init__(self) -> None:
        self.spans: list[GenAISpan] = []

    def start_span(
        self,
        trace_id: str,
        agent_name: str,
        workflow_id: str,
        department: str,
        parent_span_id: str | None = None,
    ) -> GenAISpan:
        span = GenAISpan(
            trace_id=trace_id,
            span_id=f"span_{uuid.uuid4().hex[:8]}",
            parent_span_id=parent_span_id,
            agent_name=agent_name,
            workflow_id=workflow_id,
            department=department,
        )
        return span

    def finish_span(
        self,
        span: GenAISpan,
        prompt_tokens: int,
        completion_tokens: int,
        status: str = "OK",
        attributes: dict[str, Any] | None = None,
    ) -> None:
        span.duration_ms = (time.time() - span.start_time) * 1000
        span.prompt_tokens = prompt_tokens
        span.completion_tokens = completion_tokens
        span.status = status
        if attributes:
            span.attributes.update(attributes)
        self.spans.append(span)

    def calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> Decimal:
        p_cost = (Decimal(prompt_tokens) / Decimal(1000)) * self.PROMPT_COST_PER_1K
        c_cost = (Decimal(completion_tokens) / Decimal(1000)) * self.COMPLETION_COST_PER_1K
        return (p_cost + c_cost).quantize(Decimal("0.000001"))

    def get_departmental_attribution(self) -> dict[str, dict[str, Any]]:
        """
        Aggregates token consumption and cloud expenditure by department.
        """
        summary: dict[str, dict[str, Any]] = {}
        for s in self.spans:
            dept = s.department
            if dept not in summary:
                summary[dept] = {
                    "total_spans": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_cost_usd": Decimal("0.0"),
                    "avg_duration_ms": 0.0,
                    "total_duration_ms": 0.0,
                }

            entry = summary[dept]
            entry["total_spans"] += 1
            entry["prompt_tokens"] += s.prompt_tokens
            entry["completion_tokens"] += s.completion_tokens
            entry["total_cost_usd"] += self.calculate_cost(s.prompt_tokens, s.completion_tokens)
            entry["total_duration_ms"] += s.duration_ms

        for _dept, entry in summary.items():
            if entry["total_spans"] > 0:
                entry["avg_duration_ms"] = round(
                    entry["total_duration_ms"] / entry["total_spans"], 2
                )
            del entry["total_duration_ms"]

        return summary
