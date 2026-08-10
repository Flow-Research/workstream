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
    names = ProjectGuideCompilationRequestFacts.__dataclass_fields__
    return ProjectGuideCompilationRequestFacts(
        **{name: getattr(persist, name) for name in names}
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

    operations = (
        denial.prepare_request(actor=actor, facts=facts),
        denial.consume_request(handle=object(), actor=actor, facts=facts),
        denial.authorize_execute_preflight(actor=actor, facts=facts),
        denial.prepare_execute_persist(actor=actor, facts=facts),
        denial.consume_execute_persist(handle=object(), actor=actor, facts=facts),
    )
    for operation in operations:
        with pytest.raises(AuthorizationUnavailable):
            await operation
