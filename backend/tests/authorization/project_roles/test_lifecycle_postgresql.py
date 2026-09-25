"""PostgreSQL issue and revoke decision-binding behavior."""

import pytest
from sqlalchemy import text

from app.core.identifiers import new_record_id
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.catalogue import PermissionId
from app.modules.authorization.project_role_service import (
    ProjectRoleGrantMutationService,
    project_role_issue_lock_key,
)
from app.modules.authorization.runtime import (
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
    PreparedAuthorizationInput,
    ProjectRoleGrantIssueResourceContext,
    ProjectRoleGrantRevokeResourceContext,
)
from app.modules.authorization.schemas import (
    AuthorityOperation,
    ClaimedReservation,
    ProjectRole,
    ProjectRoleGrantIssueRequest,
    ProjectRoleGrantRevokeRequest,
    derive_reason_digest,
)
from tests.authorization.project_roles.fixtures import (
    RoleMutationCase,
    authorization_factory as authorization_factory,
    mutation_runtime,
    project_role_qualification,
    role_mutation_case as role_mutation_case,
)


async def _prepare_submitter_issue(session, repository, prepared, case: RoleMutationCase):
    reason = "Project-role issue proof"
    request = ProjectRoleGrantIssueRequest(
        operation=AuthorityOperation.PROJECT_ROLE_GRANT_ISSUE,
        project_id=case.project_id,
        target_actor_id=case.target_id,
        role=ProjectRole.SUBMITTER,
        qualification=project_role_qualification(),
        reason_digest=derive_reason_digest(reason),
    )
    key = new_record_id()
    reservation = await ProjectRoleGrantMutationService(session).reserve(
        key=key, actor_profile_id=case.caller_id, request=request
    )
    assert isinstance(reservation, ClaimedReservation)
    prepared_input = PreparedAuthorizationInput(
        idempotency_key=key, request_value=request.model_dump(mode="json")
    )
    handle = await prepared.prepare(
        ActionId.PROJECT_ROLE_GRANT_ISSUE,
        prepared_input,
        PreparedAuthorityScope(
            kind=PreparedAuthorityScopeKind.PROJECT,
            project_id=case.project_id,
            target_actor_profile_id=case.target_id,
            role=ProjectRole.SUBMITTER,
        ),
    )
    assert await repository.lock_project(case.project_id) is not None
    await repository.take_project_role_issue_lock(
        project_role_issue_lock_key(case.target_id, case.project_id, "submitter")
    )
    assert await repository.lock_eligible_human(case.target_id) is not None
    resource = ProjectRoleGrantIssueResourceContext(
        resource_type="project_role_grant",
        resource_id=case.project_id,
        scope_project_id=case.project_id,
        target_actor_profile_id=case.target_id,
        role=ProjectRole.SUBMITTER,
        project_status="draft",
        target_eligible=True,
        active_exact_role_exists=False,
    )
    decision = await prepared.consume(
        handle, ActionId.PROJECT_ROLE_GRANT_ISSUE, prepared_input, resource
    )
    return request, reservation, resource, decision, reason


async def _issue_submitter_for_revoke(session, repository, prepared, case):
    request, reservation, resource, decision, reason = await _prepare_submitter_issue(
        session, repository, prepared, case
    )
    issued = await ProjectRoleGrantMutationService(session).complete_issue(
        claim=reservation.claim,
        request=request,
        decision=decision,
        resource=resource,
        actor_profile_id=case.caller_id,
        reason=reason,
    )
    await session.commit()
    return issued, reservation


@pytest.mark.asyncio
async def test_project_role_issue_rejects_substituted_prepared_authority(
    authorization_factory, role_mutation_case: RoleMutationCase
) -> None:
    case = role_mutation_case
    async with mutation_runtime(authorization_factory, case.context) as (
        session,
        repository,
        prepared,
    ):
        request, reservation, resource, decision, reason = await _prepare_submitter_issue(
            session, repository, prepared, case
        )
        assert decision.allowed is True
        assert decision.matched_grant_id == case.manager_grant_id
        service = ProjectRoleGrantMutationService(session)
        substitutions = (
            decision.model_copy(update={"action_id": ActionId.PROJECT_ROLE_GRANT_REVOKE}),
            decision.model_copy(update={"permission_id": PermissionId.PROJECT_READ}),
            decision.model_copy(update={"revalidated": False}),
            decision.model_copy(update={"matched_scope_project_id": new_record_id()}),
            decision.model_copy(update={"resource_context_digest": f"sha256:{'0' * 64}"}),
        )
        for altered_decision in substitutions:
            with pytest.raises(TypeError, match="requires exact matched authority"):
                await service.complete_issue(
                    claim=reservation.claim,
                    request=request,
                    decision=altered_decision,
                    resource=resource,
                    actor_profile_id=case.caller_id,
                    reason=reason,
                )
        issued = await service.complete_issue(
            claim=reservation.claim,
            request=request,
            decision=decision,
            resource=resource,
            actor_profile_id=case.caller_id,
            reason=reason,
        )
        assert issued.status == "active"
        await session.commit()


async def _prepare_revoke(session, repository, prepared, case: RoleMutationCase):
    issued, issue_reservation = await _issue_submitter_for_revoke(
        session, repository, prepared, case
    )
    await session.execute(
        text(
            "update actor_profiles set status='suspended', suspended_by=:by, "
            "suspended_at=clock_timestamp(), suspension_reason='proof' where id=:id"
        ),
        {"id": str(case.target_id), "by": str(case.caller_id)},
    )
    await session.execute(
        text(
            "update actor_identity_links set status='revoked', revoked_by=:by, "
            "revoked_at=clock_timestamp(), revoked_reason='proof' where id=:id"
        ),
        {"id": str(case.target_link_id), "by": str(case.caller_id)},
    )
    await session.commit()
    reason = "Lifecycle-independent revoke proof"
    request = ProjectRoleGrantRevokeRequest(
        operation=AuthorityOperation.PROJECT_ROLE_GRANT_REVOKE,
        project_id=case.project_id,
        grant_id=issued.id,
        reason_digest=derive_reason_digest(reason),
    )
    key = new_record_id()
    reservation = await ProjectRoleGrantMutationService(session).reserve(
        key=key, actor_profile_id=case.caller_id, request=request
    )
    assert isinstance(reservation, ClaimedReservation)
    prepared_input = PreparedAuthorizationInput(
        idempotency_key=key, request_value=request.model_dump(mode="json")
    )
    handle = await prepared.prepare(
        ActionId.PROJECT_ROLE_GRANT_REVOKE,
        prepared_input,
        PreparedAuthorityScope(
            kind=PreparedAuthorityScopeKind.PROJECT,
            project_id=case.project_id,
            grant_id=issued.id,
        ),
    )
    project = await repository.lock_project(case.project_id)
    row = await repository.lock_project_role_grant(project_id=case.project_id, grant_id=issued.id)
    assert project is not None and row is not None
    grant, _snapshot = row
    resource = ProjectRoleGrantRevokeResourceContext(
        resource_type="project_role_grant",
        resource_id=issued.id,
        scope_project_id=case.project_id,
        actor_profile_id=case.target_id,
        role=ProjectRole.SUBMITTER,
        project_status="draft",
        status="active",
        version=1,
    )
    decision = await prepared.consume(
        handle, ActionId.PROJECT_ROLE_GRANT_REVOKE, prepared_input, resource
    )
    return issued, issue_reservation, reservation, request, reason, grant, resource, decision


async def _assert_revoke_invalidation(session, case, issued, reservation, issue_reservation):
    assert (
        await session.scalar(
            text(
                "select count(*) from audit_events where idempotency_reference in (:issue, :revoke)"
            ),
            {
                "issue": str(issue_reservation.claim.record_id),
                "revoke": str(reservation.claim.record_id),
            },
        )
        == 4
    )
    event = (
        await session.execute(
            text(
                "select target_actor_ref_kind,target_actor_ref,resource_type,resource_id,"
                "target_ref_kind,target_ref_id,invalidation_target_kind,"
                "invalidation_target_ref,before_facts,after_facts from audit_events "
                "where idempotency_reference=:revoke and "
                "event_type='AuthorityInvalidationRequested'"
            ),
            {"revoke": str(reservation.claim.record_id)},
        )
    ).one()
    assert tuple(event[:8]) == (
        "actor_profile",
        str(case.target_id),
        "project_role_grant",
        str(issued.id),
        "project_role_grant",
        str(issued.id),
        "project_role_grant",
        str(issued.id),
    )
    assert event.before_facts == {
        "effective": True,
        "role": "submitter",
        "scope_type": "project",
        "scope_id": str(case.project_id),
        "future_obligation": "auth13_assignment",
    }
    assert event.after_facts == {**event.before_facts, "effective": False}


@pytest.mark.asyncio
async def test_project_role_revoke_rejects_substituted_prepared_authority(
    authorization_factory, role_mutation_case: RoleMutationCase
) -> None:
    case = role_mutation_case
    async with mutation_runtime(authorization_factory, case.context) as (
        session,
        repository,
        prepared,
    ):
        _, _, reservation, request, reason, grant, resource, decision = await _prepare_revoke(
            session, repository, prepared, case
        )
        service = ProjectRoleGrantMutationService(session)
        substitutions = (
            (
                decision.model_copy(update={"action_id": ActionId.PROJECT_ROLE_GRANT_ISSUE}),
                resource,
            ),
            (decision.model_copy(update={"permission_id": PermissionId.PROJECT_READ}), resource),
            (decision.model_copy(update={"revalidated": False}), resource),
            (decision.model_copy(update={"matched_scope_project_id": new_record_id()}), resource),
            (
                decision.model_copy(update={"resource_context_digest": f"sha256:{'0' * 64}"}),
                resource,
            ),
            (decision, resource.model_copy(update={"actor_profile_id": new_record_id()})),
            (decision, resource.model_copy(update={"role": ProjectRole.REVIEWER})),
            (decision, resource.model_copy(update={"version": 2, "status": "revoked"})),
        )
        for altered_decision, altered_resource in substitutions:
            with pytest.raises(TypeError, match="requires exact matched authority"):
                await service.complete_revoke(
                    claim=reservation.claim,
                    request=request,
                    decision=altered_decision,
                    resource=altered_resource,
                    actor_profile_id=case.caller_id,
                    reason=reason,
                    grant=grant,
                )
        assert grant.status == "active" and grant.version == 1


@pytest.mark.asyncio
async def test_project_role_revoke_survives_target_lifecycle_loss(
    authorization_factory, role_mutation_case: RoleMutationCase
) -> None:
    case = role_mutation_case
    async with mutation_runtime(authorization_factory, case.context) as (
        session,
        repository,
        prepared,
    ):
        (
            issued,
            issue_reservation,
            reservation,
            request,
            reason,
            grant,
            resource,
            decision,
        ) = await _prepare_revoke(session, repository, prepared, case)
        revoked = await ProjectRoleGrantMutationService(session).complete_revoke(
            claim=reservation.claim,
            request=request,
            decision=decision,
            resource=resource,
            actor_profile_id=case.caller_id,
            reason=reason,
            grant=grant,
        )
        assert revoked.status == "revoked"
        await session.commit()
        await _assert_revoke_invalidation(session, case, issued, reservation, issue_reservation)
