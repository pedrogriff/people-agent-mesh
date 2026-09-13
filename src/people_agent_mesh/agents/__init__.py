"""
Agents package for PeopleAgentMesh.
Provides BaseAgent, CompensationAgent, PromotionAgent, MeshSupervisorAgent,
and the Multi-Agent Calibration Committee (ADR-006).
"""

from people_agent_mesh.agents.base import AgentResult, BaseAgent
from people_agent_mesh.agents.committee import (
    AdvocateAgent,
    CalibrationCommitteeOrchestrator,
    ConsensusModeratorAgent,
    EquityAuditorAgent,
    ReflexionCritiqueEngine,
    SkepticAgent,
)
from people_agent_mesh.agents.compensation import CompensationAgent
from people_agent_mesh.agents.promotion import PromotionAgent
from people_agent_mesh.agents.supervisor import MeshSupervisorAgent

__all__ = [
    "AgentResult",
    "BaseAgent",
    "CompensationAgent",
    "PromotionAgent",
    "MeshSupervisorAgent",
    "AdvocateAgent",
    "SkepticAgent",
    "EquityAuditorAgent",
    "ConsensusModeratorAgent",
    "ReflexionCritiqueEngine",
    "CalibrationCommitteeOrchestrator",
]
