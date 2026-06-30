"""Project-agent runtime factory functions."""

from __future__ import annotations

from app.adapters.project_agents import build_project_guide_agent_runtime
from app.core.config import get_settings
from app.interfaces.project_agents import ProjectGuideAgentRuntime


def get_project_guide_agent_runtime() -> ProjectGuideAgentRuntime:
    """Return the configured project guide setup agent runtime."""
    return build_project_guide_agent_runtime(get_settings())
