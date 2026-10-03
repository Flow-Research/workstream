"""Real PostgreSQL proof that routing preparation remains unavailable and inert."""

from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.identifiers import new_record_id
from app.modules.actors.api import ServiceIdentity
from app.modules.actors.models import ActorIdentityLink
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.post_submit_routing import (
    PostSubmitRoutingResourceContext,
    post_submit_routing_prepare_values,
)
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.post_submit_routing_authorization import (
    PostSubmitRoutingAuthorization,
)
from app.modules.authorization.prepared import (
    PreparedAuthorizationService,
    fixed_service_prepared_authorization,
)
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    AuthorizationDenialCode,
    HumanAuthorizationContext,
    IdentityLinkStatus,
    PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
)
from app.modules.tasks.models import Submission
from app.modules.tasks.post_submit_routing.models import TaskRoutingRequest
from tests.authorization.post_submit_routing.support import (
    changed_request,
    claim_for,
    effect_snapshot,
    provision_router,
    real_source_facts,
    stage_real_request,
)
from tests.tasks.post_submit_routing.support import completed_source


async def _planned_adapter_denial(session, request):
    yielded = False
    with pytest.raises(PreparedAuthorizationUnsupported) as caught:
        async with PostSubmitRoutingAuthorization(session).prepare(request):
            yielded = True
    assert not yielded
    assert caught.value.denial_code is AuthorizationDenialCode.ACTION_UNAVAILABLE


async def test_provisioned_router_remains_planned(tmp_path, isolated_database_env):
    async with completed_source(tmp_path, isolated_database_env) as h:
        await provision_router(h.factory)
        request = await stage_real_request(h)
        source = await real_source_facts(h, request)
        resource = PostSubmitRoutingResourceContext(
            resource_id=request.routing_manifest_id,
            scope_project_id=request.project_id,
            request=request,
            source=source,
            claim=claim_for(request),
            consequence={"kind": "human_admission"},
        )
        assert resource.validate_identity() is resource

        async with h.factory() as session:
            before = await effect_snapshot(session)
        async with h.factory() as session, session.begin():
            await _planned_adapter_denial(session, request)
        async with h.factory() as session:
            assert await effect_snapshot(session) == before


async def test_foreign_service_and_human_cannot_prepare_route(
    tmp_path, isolated_database_env
):
    async with completed_source(tmp_path, isolated_database_env) as h:
        await provision_router(h.factory)
        request = await stage_real_request(h)
        caller_input = PreparedAuthorizationInput(
            idempotency_key=request.route_operation_id,
            request_value=post_submit_routing_prepare_values(request),
        )
        scope = PreparedAuthorityScope(
            kind=PreparedAuthorityScopeKind.PROJECT,
            project_id=request.project_id,
        )
        async with h.factory() as session:
            before = await effect_snapshot(session)

        async with h.factory() as session, session.begin():
            async with fixed_service_prepared_authorization(
                session,
                service_identity=ServiceIdentity.CHECKER_POST_SUBMIT,
                request_id=request.route_operation_id,
                correlation_id=request.route_operation_id,
            ) as foreign:
                with pytest.raises(PreparedAuthorizationUnsupported) as caught:
                    await foreign.service.prepare(
                        ActionId.TASK_POST_SUBMIT_ROUTE, caller_input, scope
                    )
                assert (
                    caught.value.denial_code
                    is AuthorizationDenialCode.PERMISSION_NOT_GRANTED
                )

        async with h.factory() as session, session.begin():
            submission = await session.get(Submission, str(request.submission_id))
            link = await session.scalar(
                select(ActorIdentityLink).where(
                    ActorIdentityLink.actor_profile_id == submission.contributor_id,
                    ActorIdentityLink.status == "active",
                )
            )
            context = HumanAuthorizationContext(
                actor_profile_id=UUID(submission.contributor_id),
                actor_kind=ActorKind.HUMAN,
                actor_status=ActorStatus.ACTIVE,
                identity_link_id=UUID(link.id),
                identity_link_status=IdentityLinkStatus.ACTIVE,
                request_id=request.route_operation_id,
                correlation_id=request.route_operation_id,
            )
            repository = AdminAuthorizationRepository(session)
            kernel = AuthorizationService(
                session, context, admin_repository=repository
            )
            human = PreparedAuthorizationService(
                session, context, kernel, repository
            )
            try:
                with pytest.raises(PreparedAuthorizationUnsupported) as caught:
                    await human.prepare(
                        ActionId.TASK_POST_SUBMIT_ROUTE, caller_input, scope
                    )
                assert (
                    caught.value.denial_code
                    is AuthorizationDenialCode.ACTION_UNAVAILABLE
                )
            finally:
                human.close()

        async with h.factory() as session:
            assert await effect_snapshot(session) == before


@pytest.mark.parametrize("substitution", ("idempotency", "context", "scope", "request"))
async def test_prepared_binding_rejects_operation_and_scope_substitution(
    tmp_path, isolated_database_env, substitution
):
    async with completed_source(tmp_path, isolated_database_env) as h:
        await provision_router(h.factory)
        request = await stage_real_request(h)
        context_operation = (
            new_record_id()
            if substitution == "context"
            else request.route_operation_id
        )
        incoming = (
            changed_request(request, route_operation_id=new_record_id())
            if substitution == "request"
            else request
        )
        caller_input = PreparedAuthorizationInput(
            idempotency_key=(
                new_record_id()
                if substitution == "idempotency"
                else request.route_operation_id
            ),
            request_value=post_submit_routing_prepare_values(incoming),
        )
        scope = PreparedAuthorityScope(
            kind=PreparedAuthorityScopeKind.PROJECT,
            project_id=(
                new_record_id() if substitution == "scope" else request.project_id
            ),
        )
        async with h.factory() as session, session.begin():
            async with fixed_service_prepared_authorization(
                session,
                service_identity=ServiceIdentity.TASK_POST_SUBMIT_ROUTER,
                request_id=context_operation,
                correlation_id=context_operation,
            ) as authority:
                with pytest.raises(PreparedAuthorizationHandleInvalid):
                    await authority.service.prepare(
                        ActionId.TASK_POST_SUBMIT_ROUTE, caller_input, scope
                    )


async def test_planned_denial_rollback_preserves_request(
    tmp_path, isolated_database_env
):
    async with completed_source(tmp_path, isolated_database_env) as h:
        await provision_router(h.factory)
        request = await stage_real_request(h)
        async with h.factory() as session:
            before = await effect_snapshot(session)

        async with h.factory() as session:
            await session.begin()
            await _planned_adapter_denial(session, request)
            await session.rollback()

        async with h.factory() as session:
            stored = await session.get(TaskRoutingRequest, request.route_operation_id)
            assert stored is not None
            assert stored.routing_manifest_id == request.routing_manifest_id
            assert stored.route_request_digest == request.route_request_digest
            assert await effect_snapshot(session) == before

        assert await stage_real_request(h) == request
        async with h.factory() as session:
            assert await effect_snapshot(session) == before
