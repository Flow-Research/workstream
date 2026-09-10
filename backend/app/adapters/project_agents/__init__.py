"""Explicit typed composition for project-guide agent runtimes."""

from app.adapters.project_agents.openai_agent_sdk import OpenAIAgentSdkProjectGuideRuntime
from app.interfaces.external_services import ExternalServiceAdapterFactory
from app.interfaces.project_agents import ProjectGuideAgentRuntime
from app.interfaces.project_guide_runtime import ProjectGuideRuntimeConfiguration


def create_project_guide_runtime(
    configuration: ProjectGuideRuntimeConfiguration,
) -> ProjectGuideAgentRuntime:
    """Construct only the explicitly registered runtime chosen by this attempt."""
    factory = ExternalServiceAdapterFactory[ProjectGuideAgentRuntime]("project_guide_compilation")
    factory.register("openai_agents_sdk", lambda: OpenAIAgentSdkProjectGuideRuntime(configuration))
    return factory.create(configuration.runtime_key)
