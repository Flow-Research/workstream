"""Project-agent runtime adapter factory."""

from __future__ import annotations

from app.adapters.project_agents.openai_agent_sdk import OpenAIAgentSdkProjectGuideRuntime
from app.core.config import Settings
from app.interfaces.project_agents import ProjectGuideAgentRuntime


def build_project_guide_agent_runtime(settings: Settings) -> ProjectGuideAgentRuntime:
    """Build the configured project guide setup agent runtime."""
    return OpenAIAgentSdkProjectGuideRuntime(settings)
