"""Trusted configuration snapshots for guide-agent execution."""

from __future__ import annotations

import hashlib

from app.core.config import Settings
from app.core.project_guide_instructions import PROJECT_GUIDE_INSTRUCTIONS
from app.interfaces.project_guide_runtime import ProjectGuideRuntimeConfiguration


def project_guide_runtime_configuration(settings: Settings) -> ProjectGuideRuntimeConfiguration:
    """Snapshot trusted settings without constructing a provider or copying secrets."""
    instructions = (
        PROJECT_GUIDE_INSTRUCTIONS
        if settings.project_agent_instructions is None
        else settings.project_agent_instructions
    )
    return ProjectGuideRuntimeConfiguration(
        runtime_key=settings.project_agent_runtime,
        model_provider=settings.project_agent_model_provider,
        model=settings.project_agent_model,
        model_api=settings.project_agent_model_api,
        instruction_version=settings.project_agent_instruction_version,
        instructions=instructions,
        instructions_sha256="sha256:" + hashlib.sha256(instructions.encode("utf-8")).hexdigest(),
        timeout_seconds=settings.project_agent_run_timeout_seconds,
        request_timeout_seconds=settings.project_agent_request_timeout_seconds,
        maximum_retries=settings.project_agent_max_retries,
        retry_backoff_multiplier=settings.project_agent_retry_backoff_multiplier,
        retry_jitter=settings.project_agent_retry_jitter,
        retry_initial_delay_seconds=settings.project_agent_retry_initial_delay_seconds,
        retry_max_delay_seconds=settings.project_agent_retry_max_delay_seconds,
        circuit_failure_threshold=settings.project_agent_circuit_failure_threshold,
        circuit_cooldown_seconds=settings.project_agent_circuit_cooldown_seconds,
        maximum_manifest_bytes=settings.project_agent_max_manifest_bytes,
        maximum_documents=settings.project_agent_max_documents,
        maximum_document_bytes=settings.project_agent_max_document_bytes,
        maximum_total_document_bytes=settings.project_agent_max_total_document_bytes,
        maximum_turns=settings.project_agent_max_turns,
        maximum_hosted_tool_calls=settings.project_agent_max_hosted_tool_calls,
        compaction_threshold_tokens=settings.project_agent_compaction_threshold_tokens,
        container_expiry_minutes=settings.project_agent_container_expiry_minutes,
        file_expiry_seconds=settings.project_agent_file_expiry_seconds,
        cleanup_timeout_seconds=settings.project_agent_cleanup_timeout_seconds,
    )
