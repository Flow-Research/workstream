"""Explicit typed composition for project-guide agent runtimes."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from app.adapters.project_agents.manager_authored import (
    MANAGER_AUTHORED_RUNTIME_KEY,
    ManagerAuthoredProjectGuideRuntime,
)
from app.adapters.project_agents.openai_agent_sdk import (
    OpenAIAgentSdkProjectGuideRuntime,
)
from app.adapters.project_agents.openai_profile import (
    build_openai_agents_sdk_adapter_profile,
)
from app.adapters.project_agents.omnicore_agent import (
    OMNICORE_RUNTIME_KEY,
    OmniCoreAgentProjectGuideRuntime,
)
from app.adapters.project_agents.omnicore_profile import (
    build_omnicore_agent_adapter_profile,
)
from app.adapters.project_agents.openai_workspace import (
    OpenAIGuideRuntimeCleanupAdapter,
    RETAINED_OPENAI_GUIDE_RUNTIME_KEY,
)
from workstream_external_services import ExternalServiceAdapterFactory
from app.interfaces.project_agents import (
    ProjectAgentRuntimeConfigurationError,
    ProjectGuideAgentRuntime,
)
from app.interfaces.project_guide_runtime import (
    AdapterProfileValue,
    ProjectGuideRuntimeConfiguration,
)
from app.modules.projects.api.guide_documents import (
    GUIDE_RUNTIME_RESOURCE_CLEANUP_CAPABILITY_KEY,
    GuideRuntimeResourceCleanupAdapter,
)


ProfileBuilder = Callable[[Mapping[str, object]], Mapping[str, AdapterProfileValue]]
RuntimeBuilder = Callable[[ProjectGuideRuntimeConfiguration], ProjectGuideAgentRuntime]


@dataclass(frozen=True, slots=True)
class _RuntimeRegistration:
    profile_builder: ProfileBuilder
    runtime_builder: RuntimeBuilder


def _manager_authored_profile(
    options: Mapping[str, object],
) -> Mapping[str, AdapterProfileValue]:
    if options:
        raise ProjectAgentRuntimeConfigurationError(
            "manager-authored guide runtime accepts no runtime options"
        )
    return {}


_RUNTIMES = {
    "openai_agents_sdk": _RuntimeRegistration(
        profile_builder=build_openai_agents_sdk_adapter_profile,
        runtime_builder=OpenAIAgentSdkProjectGuideRuntime,
    ),
    OMNICORE_RUNTIME_KEY: _RuntimeRegistration(
        profile_builder=build_omnicore_agent_adapter_profile,
        runtime_builder=OmniCoreAgentProjectGuideRuntime,
    ),
    MANAGER_AUTHORED_RUNTIME_KEY: _RuntimeRegistration(
        profile_builder=_manager_authored_profile,
        runtime_builder=ManagerAuthoredProjectGuideRuntime,
    ),
}


def build_project_guide_adapter_profile(
    runtime_key: str,
    options: Mapping[str, object],
) -> Mapping[str, AdapterProfileValue]:
    """Build the selected registered adapter's closed effective profile."""
    try:
        registration = _RUNTIMES[runtime_key]
    except KeyError:
        raise ProjectAgentRuntimeConfigurationError(
            "project guide runtime is unsupported"
        ) from None
    return registration.profile_builder(options)


def create_project_guide_runtime(
    configuration: ProjectGuideRuntimeConfiguration,
) -> ProjectGuideAgentRuntime:
    """Construct only the explicitly registered runtime chosen by this attempt."""
    factory = ExternalServiceAdapterFactory[ProjectGuideAgentRuntime](
        "project_guide_compilation"
    )
    for runtime_key, registration in _RUNTIMES.items():
        factory.register(
            runtime_key,
            lambda registration=registration: registration.runtime_builder(configuration),
        )
    return factory.create(configuration.runtime_key)


def create_guide_runtime_cleanup_factory() -> ExternalServiceAdapterFactory[
    GuideRuntimeResourceCleanupAdapter
]:
    """Register exact retained-resource cleanup independently of inference."""
    factory = ExternalServiceAdapterFactory[GuideRuntimeResourceCleanupAdapter](
        GUIDE_RUNTIME_RESOURCE_CLEANUP_CAPABILITY_KEY
    )
    factory.register(RETAINED_OPENAI_GUIDE_RUNTIME_KEY, OpenAIGuideRuntimeCleanupAdapter)
    return factory


__all__ = (
    "RETAINED_OPENAI_GUIDE_RUNTIME_KEY",
    "build_project_guide_adapter_profile",
    "create_guide_runtime_cleanup_factory",
    "create_project_guide_runtime",
)
