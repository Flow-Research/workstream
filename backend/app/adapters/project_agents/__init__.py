"""Project-agent runtime adapter factory."""

from __future__ import annotations

from app.adapters.project_agents.local_fixture import LocalFixtureProjectGuideAgentRuntime
from app.adapters.project_agents.openai_agent_sdk import OpenAIAgentSdkProjectGuideRuntime
from app.core.config import Settings
from app.interfaces.project_agents import ProjectGuideAgentRuntime
from app.interfaces.project_agents import ProjectAgentRuntimeConfigurationError

LOCAL_FIXTURE_ENVIRONMENTS = {"local", "dev", "development", "test"}


def build_project_guide_agent_runtime(settings: Settings) -> ProjectGuideAgentRuntime:
    """Build the configured project guide setup agent runtime."""
    if settings.project_agent_runtime_adapter == "openai_agent_sdk":
        return OpenAIAgentSdkProjectGuideRuntime(settings)
    if settings.environment.strip().lower() not in LOCAL_FIXTURE_ENVIRONMENTS:
        raise ProjectAgentRuntimeConfigurationError(
            "local fixture project agent adapter cannot run outside local/dev/test"
        )
    return LocalFixtureProjectGuideAgentRuntime()
