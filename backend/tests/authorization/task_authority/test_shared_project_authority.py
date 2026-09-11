"""The shared authority-lock helper preserves the distinct guide-ingest guard."""

from uuid import UUID, uuid4

import pytest

from app.modules.authorization.catalogue import ActionId, PermissionId
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.runtime import (
    GuideSourceIngestResourceContext, HumanAuthorizationContext, MatchedAuthorityKind,
    PreparedAuthorizationHandleInvalid, PreparedAuthorizationInput,
    PreparedAuthorityScope, PreparedAuthorityScopeKind,
)
from tests.test_authorization import (
    _PreparedAdminFacts, _PreparedTestSession, _runtime_context, _runtime_service,
)


@pytest.mark.asyncio
async def test_prepared_guide_ingest_binds_exact_project_and_locked_manager_grant():
    context = _runtime_context()
    assert isinstance(context, HumanAuthorizationContext)
    session = _PreparedTestSession()
    authorization, evidence = _runtime_service(context, session=session)
    facts = _PreparedAdminFacts(context)
    authorization._admin = facts  # type: ignore[assignment]
    prepared = PreparedAuthorizationService(
        session,  # type: ignore[arg-type]
        context,
        authorization,
        facts,  # type: ignore[arg-type]
    )
    try:
        project_id = uuid4()
        caller_input = PreparedAuthorizationInput(
            idempotency_key=uuid4(), request_value={"project_id": str(project_id)}
        )
        handle = await prepared.prepare(
            ActionId.ARTIFACT_GUIDE_SOURCE_INGEST,
            caller_input,
            PreparedAuthorityScope(
                kind=PreparedAuthorityScopeKind.PROJECT,
                project_id=project_id,
            ),
        )
        assert (facts.calls, facts.grant_calls) == (1, 1)
        assert facts.grant_requests == [
            (
                (context.actor_profile_id, PermissionId.ARTIFACT_GUIDE_SOURCE_INGEST),
                {"scope_project_id": project_id, "system_scope_only": False, "for_update": True},
            )
        ]

        def resource(scope_project_id: UUID) -> GuideSourceIngestResourceContext:
            return GuideSourceIngestResourceContext(
                resource_type="project",
                resource_id=scope_project_id,
                scope_project_id=scope_project_id,
                guide_id=uuid4(),
                guide_source_snapshot_id=uuid4(),
                guide_source_item_id=uuid4(),
                operation_identity="sha256:" + "b" * 64,
                request_digest="sha256:" + "c" * 64,
                sha256="sha256:" + "d" * 64,
                byte_count=17,
                media_type="application/octet-stream",
            )

        with pytest.raises(PreparedAuthorizationHandleInvalid):
            await prepared.consume(
                handle,
                ActionId.ARTIFACT_GUIDE_SOURCE_INGEST,
                caller_input,
                resource(uuid4()),
            )
        assert evidence.events == []
        decision = await prepared.consume(
            handle,
            ActionId.ARTIFACT_GUIDE_SOURCE_INGEST,
            caller_input,
            resource(project_id),
        )
        assert decision.allowed is True
        assert decision.matched_authority_kind is MatchedAuthorityKind.ADMIN_ROLE_GRANT
        assert decision.matched_grant_id == facts.grant_id
        assert decision.matched_scope_project_id == project_id
        assert (facts.calls, facts.grant_calls) == (1, 1)
        assert len(evidence.events) == 1
        assert evidence.events[0].project_id == str(project_id)
        assert evidence.events[0].after_facts is not None
        assert evidence.events[0].after_facts["resource_context_digest"] == (
            decision.resource_context_digest
        )
    finally:
        prepared.close()
