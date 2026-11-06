"""Trusted configuration snapshots for guide-agent execution."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping

from app.core.config import Settings
from app.core.project_guide_instructions import PROJECT_GUIDE_INSTRUCTIONS
from app.interfaces.project_guide_runtime import (
    ProjectGuideRuntimeConfiguration,
    canonical_adapter_profile,
)


def project_guide_runtime_configuration(
    settings: Settings,
    *,
    adapter_profile_builder: Callable[[Mapping[str, object]], Mapping[str, object]],
) -> ProjectGuideRuntimeConfiguration:
    """Snapshot trusted settings with an adapter-validated effective profile."""
    instructions = (
        PROJECT_GUIDE_INSTRUCTIONS
        if settings.project_agent_instructions is None
        else settings.project_agent_instructions
    )
    adapter_profile = canonical_adapter_profile(
        adapter_profile_builder(settings.project_agent_runtime_options)
    )
    return ProjectGuideRuntimeConfiguration(
        runtime_key=settings.project_agent_runtime,
        model_provider=settings.project_agent_model_provider,
        model=settings.project_agent_model,
        model_api=settings.project_agent_model_api,
        adapter_profile=adapter_profile,
        instruction_version=settings.project_agent_instruction_version,
        instructions=instructions,
        instructions_sha256="sha256:" + hashlib.sha256(instructions.encode("utf-8")).hexdigest(),
        timeout_seconds=settings.project_agent_run_timeout_seconds,
        maximum_manifest_bytes=settings.project_agent_max_manifest_bytes,
        maximum_documents=settings.project_agent_max_documents,
        maximum_document_bytes=settings.project_agent_max_document_bytes,
        maximum_total_document_bytes=settings.project_agent_max_total_document_bytes,
        maximum_turns=settings.project_agent_max_turns,
        maximum_tool_calls=settings.project_agent_max_tool_calls,
        maximum_tool_output_characters=settings.project_agent_max_tool_output_characters,
    )


def manager_authored_guide_configuration(settings: Settings) -> ProjectGuideRuntimeConfiguration:
    """Select the registered provider-free compiler without changing process settings."""
    instructions = PROJECT_GUIDE_INSTRUCTIONS
    return ProjectGuideRuntimeConfiguration(
        runtime_key="manager_authored", model_provider="none", model_api="none", model="none",
        adapter_profile="{}", instruction_version=settings.project_agent_instruction_version,
        instructions=instructions,
        instructions_sha256="sha256:" + hashlib.sha256(instructions.encode("utf-8")).hexdigest(),
        timeout_seconds=settings.project_agent_run_timeout_seconds,
        maximum_manifest_bytes=settings.project_agent_max_manifest_bytes,
        maximum_documents=settings.project_agent_max_documents,
        maximum_document_bytes=settings.project_agent_max_document_bytes,
        maximum_total_document_bytes=settings.project_agent_max_total_document_bytes,
        maximum_turns=settings.project_agent_max_turns,
        maximum_tool_calls=settings.project_agent_max_tool_calls,
        maximum_tool_output_characters=settings.project_agent_max_tool_output_characters,
    )
