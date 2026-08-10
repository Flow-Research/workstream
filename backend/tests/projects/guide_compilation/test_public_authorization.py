"""Public fact integrity and inactive authorization behavior."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest

from app.modules.authorization.api import (
    AuthorizationUnavailable,
    ProjectGuideCompilationRequestFacts,
)
from app.modules.projects.guide_compilation.authorization import (
    DenyProjectGuideCompilationAuthorization,
)

from .helpers import SHA256, context, identity, ids, persistence_facts, service_actor


def _request_facts() -> ProjectGuideCompilationRequestFacts:
    values = ids()
    attempt_identity = identity(context(values))
    persist = persistence_facts(values, uuid4(), attempt_identity)
    return ProjectGuideCompilationRequestFacts(
        operation_id=persist.operation_id,
        request_id=persist.request_id,
        idempotency_key=persist.idempotency_key,
        project_id=persist.project_id,
        guide_id=persist.guide_id,
        guide_version=persist.guide_version,
        source_snapshot_id=persist.source_snapshot_id,
        source_snapshot_hash=persist.source_snapshot_hash,
        setup_run_id=persist.setup_run_id,
        setup_generation=persist.setup_generation,
        canonical_input_hash=persist.canonical_input_hash,
        guide_material_hash=persist.guide_material_hash,
        pre_catalogue_id=persist.pre_catalogue_id,
        pre_catalogue_version=persist.pre_catalogue_version,
        pre_catalogue_schema_version=persist.pre_catalogue_schema_version,
        pre_catalogue_manifest_hash=persist.pre_catalogue_manifest_hash,
        post_catalogue_id=persist.post_catalogue_id,
        post_catalogue_version=persist.post_catalogue_version,
        post_catalogue_schema_version=persist.post_catalogue_schema_version,
        post_catalogue_manifest_hash=persist.post_catalogue_manifest_hash,
        agent_identity=persist.agent_identity,
        agent_version=persist.agent_version,
        instruction_version=persist.instruction_version,
    )


def test_public_facts_reject_wrong_uuid_and_unbounded_token() -> None:
    """Public AUTH facts reject open scalar shapes before evaluation."""
    facts = _request_facts()
    with pytest.raises(ValueError, match="project_id must be a UUID"):
        replace(facts, project_id="not-a-uuid")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="agent_version"):
        replace(facts, agent_version="x" * 161)
    with pytest.raises(ValueError, match="source_snapshot_hash"):
        replace(facts, source_snapshot_hash=SHA256.upper())


@pytest.mark.asyncio
async def test_hidden_authorization_denies_before_touching_product_state() -> None:
    """Every request and execute operation remains unavailable in 03A."""
    values = ids()
    compilation_context = context(values)
    attempt_identity = identity(compilation_context)
    facts = persistence_facts(values, uuid4(), attempt_identity)
    actor = service_actor(values)
    denial = DenyProjectGuideCompilationAuthorization()

    with pytest.raises(AuthorizationUnavailable):
        await denial.prepare_request(actor=actor, facts=facts)
    with pytest.raises(AuthorizationUnavailable):
        await denial.consume_request(handle=object(), actor=actor, facts=facts)
    with pytest.raises(AuthorizationUnavailable):
        await denial.authorize_execute_preflight(actor=actor, facts=facts)
    with pytest.raises(AuthorizationUnavailable):
        await denial.prepare_execute_persist(actor=actor, facts=facts)
    with pytest.raises(AuthorizationUnavailable):
        await denial.consume_execute_persist(handle=object(), actor=actor, facts=facts)
