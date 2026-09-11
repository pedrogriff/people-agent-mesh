"""
Base Agent Interfaces and Execution Context.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from people_agent_mesh.core.state import MeshState


class AgentResult(BaseModel):
    agent_name: str
    success: bool
    state: MeshState
    rationale: str = ""
    errors: list[str] = Field(default_factory=list)
    tokens_consumed: int = 0
    duration_ms: float = 0.0


class BaseAgent(ABC):
    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def execute(self, state: MeshState) -> AgentResult:
        """Executes agent logic against the mesh state."""
        pass
