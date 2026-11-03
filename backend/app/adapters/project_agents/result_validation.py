"""Shared final-result parsing and source-access validation for guide runtimes."""

from __future__ import annotations

from app.interfaces.project_agents import (
    ProjectGuideCompilationContext,
    ProjectGuideCompilationResult,
    require_complete_project_guide_compilation_result,
    require_ready_result_cites_every_document,
    validate_project_guide_compilation_result,
)


def validate_project_guide_runtime_result(
    context: ProjectGuideCompilationContext,
    output: object,
    opened_handles: frozenset[str] | set[str],
) -> ProjectGuideCompilationResult:
    """Parse one untrusted result and bind every citation to a trusted tool read."""
    if isinstance(output, ProjectGuideCompilationResult):
        result = output
    elif isinstance(output, str):
        result = ProjectGuideCompilationResult.model_validate_json(output)
    else:
        result = ProjectGuideCompilationResult.model_validate(output)
    require_complete_project_guide_compilation_result(result)
    validate_project_guide_compilation_result(context, result)
    if result.agent_version != context.agent_version:
        raise ValueError("compilation result agent version is invalid")
    require_result_sources_opened(context, result, opened_handles)
    return result


def require_result_sources_opened(
    context: ProjectGuideCompilationContext,
    result: ProjectGuideCompilationResult,
    opened_handles: frozenset[str] | set[str],
) -> None:
    """Require every assigned and cited original within the relevant trusted phase."""
    if not opened_handles:
        raise ValueError("compilation has no opened document evidence")
    document_handles = {
        (item.source_item_id, item.ingest_id): context.material.handle_for(item)
        for item in context.material.documents
    }
    if not set(document_handles.values()) <= set(opened_handles):
        raise ValueError("compilation did not open every assigned original")
    references = (
        *(ref for finding in result.findings for ref in finding.evidence_refs),
        *(ref for requirement in result.requirements for ref in requirement.evidence_refs),
    )
    cited_handles = {
        document_handles.get((ref.source_item_id, ref.document_version_id))
        for ref in references
    }
    if None in cited_handles or not cited_handles <= set(opened_handles):
        raise ValueError("compilation cites unopened source material")
    require_ready_result_cites_every_document(context, result)
