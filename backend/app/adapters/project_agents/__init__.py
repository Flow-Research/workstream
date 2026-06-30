"""Project-agent runtime adapter factory."""

from __future__ import annotations

from app.adapters.project_agents.deterministic import DeterministicProjectGuideAgentRuntime
from app.adapters.project_agents.openai_agents import OpenAIAgentsProjectGuideRuntime
from app.core.config import Settings
from app.interfaces.project_agents import ProjectGuideAgentRuntime


def build_project_guide_agent_runtime(settings: Settings) -> ProjectGuideAgentRuntime:
    """Build the configured project guide setup agent runtime."""
    if settings.project_agent_runtime == "openai":
        return OpenAIAgentsProjectGuideRuntime(settings)
    return DeterministicProjectGuideAgentRuntime()
