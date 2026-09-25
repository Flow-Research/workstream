"""Real PREP lock cancellation and same-key retry behavior."""

import asyncio

import pytest
from sqlalchemy import text

from app.core.identifiers import new_record_id
from app.modules.authorization import router as authorization_router
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.project_role_service import project_role_issue_lock_key
from app.modules.authorization.runtime import (
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
    PreparedAuthorizationInput,
    ProjectRoleGrantIssueResourceContext,
)
from app.modules.authorization.schemas import (
    AuthorityOperation,
    ClaimedReservation,
    ProjectRole,
    ProjectRoleGrantIssueRequest,
    derive_reason_digest,
)
from tests.auth_concurrency_support import wait_for_named_database_lock
from tests.authorization.project_roles.fixtures import (
    RoleMutationCase,
    authorization_database_env as authorization_database_env,
    authorization_factory as authorization_factory,
    mutation_runtime,
    project_role_mutation_service,
    project_role_qualification,
    role_mutation_case as role_mutation_case,
)


async def _cancel_waiting_prepare(
    locker, waiter, locker_prepared, waiter_prepared, case, request, key, scope, database_url
) -> None:
    waiter_task = None
    try:
        await locker.begin()
        blocker_pid = await locker.scalar(text("select pg_backend_pid()"))
        assert type(blocker_pid) is int and blocker_pid > 0
        await locker_prepared.prepare(
            ActionId.PROJECT_ROLE_GRANT_ISSUE,
            PreparedAuthorizationInput(
                idempotency_key=new_record_id(), request_value=request.model_dump(mode="json")
            ),
            scope,
        )
        await waiter.begin()
        application_name = f"project-role-cancel-{new_record_id().hex}"
        await waiter.execute(
            text("select set_config('application_name', :name, true)"),
            {"name": application_name},
        )
        await project_role_mutation_service(waiter).reserve(
            key=key, actor_profile_id=case.caller_id, request=request
        )
        waiter_pid = await waiter.scalar(text("select pg_backend_pid()"))
        assert type(waiter_pid) is int and waiter_pid > 0 and waiter_pid != blocker_pid
        waiter_task = asyncio.create_task(
            authorization_router._database_call(
                waiter,
                waiter_prepared.prepare(
                    ActionId.PROJECT_ROLE_GRANT_ISSUE,
                    PreparedAuthorizationInput(
                        idempotency_key=key, request_value=request.model_dump(mode="json")
                    ),
                    scope,
                ),
            )
        )
        await asyncio.wait_for(
            wait_for_named_database_lock(
                database_url,
                application_name,
                expected_waiter_pid=waiter_pid,
                expected_blocker_pid=blocker_pid,
            ),
            timeout=5,
        )
        assert not waiter_task.done()
        waiter_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter_task
        await locker.rollback()
    finally:
        if waiter_task is not None:
            if not waiter_task.done():
                waiter_task.cancel()
            await asyncio.gather(waiter_task, return_exceptions=True)


async def _retry_same_key(waiter, prepared, repository, case, request, key, scope) -> None:
    reservation = await project_role_mutation_service(waiter).reserve(
        key=key, actor_profile_id=case.caller_id, request=request
    )
    assert isinstance(reservation, ClaimedReservation)
    prepared_input = PreparedAuthorizationInput(
        idempotency_key=key, request_value=request.model_dump(mode="json")
    )
    handle = await authorization_router._database_call(
        waiter, prepared.prepare(ActionId.PROJECT_ROLE_GRANT_ISSUE, prepared_input, scope)
    )
    project = await repository.lock_project(case.project_id)
    assert project is not None
    await repository.take_project_role_issue_lock(
        project_role_issue_lock_key(case.target_id, case.project_id, "submitter")
    )
    assert await repository.lock_eligible_human(case.target_id) is not None
    assert (
        await repository.find_active_project_role(
            project_id=case.project_id,
            actor_profile_id=case.target_id,
            role="submitter",
        )
        is None
    )
    resource = ProjectRoleGrantIssueResourceContext(
        resource_type="project_role_grant",
        resource_id=case.project_id,
        scope_project_id=case.project_id,
        target_actor_profile_id=case.target_id,
        role=ProjectRole.SUBMITTER,
        project_status=project.status,
        target_eligible=True,
        active_exact_role_exists=False,
    )
    decision = await prepared.consume(
        handle, ActionId.PROJECT_ROLE_GRANT_ISSUE, prepared_input, resource
    )
    created = await project_role_mutation_service(waiter).complete_issue(
        claim=reservation.claim,
        request=request,
        decision=decision,
        resource=resource,
        actor_profile_id=case.caller_id,
        reason="Project-role cancellation retry",
    )
    await waiter.commit()
    assert created.status == "active"


@pytest.mark.asyncio
async def test_cancelled_project_role_prepare_allows_same_key_retry(
    authorization_database_env: str,
    authorization_factory,
    role_mutation_case: RoleMutationCase,
) -> None:
    case = role_mutation_case
    request = ProjectRoleGrantIssueRequest(
        operation=AuthorityOperation.PROJECT_ROLE_GRANT_ISSUE,
        project_id=case.project_id,
        target_actor_id=case.target_id,
        role=ProjectRole.SUBMITTER,
        qualification=project_role_qualification(),
        reason_digest=derive_reason_digest("Project-role cancellation retry"),
    )
    key = new_record_id()
    scope = PreparedAuthorityScope(
        kind=PreparedAuthorityScopeKind.PROJECT,
        project_id=case.project_id,
        target_actor_profile_id=case.target_id,
        role=ProjectRole.SUBMITTER,
    )
    async with (
        mutation_runtime(authorization_factory, case.context) as (
            locker,
            _locker_repository,
            locker_prepared,
        ),
        mutation_runtime(authorization_factory, case.context) as (
            waiter,
            waiter_repository,
            waiter_prepared,
        ),
    ):
        await _cancel_waiting_prepare(
            locker,
            waiter,
            locker_prepared,
            waiter_prepared,
            case,
            request,
            key,
            scope,
            authorization_database_env,
        )
        await _retry_same_key(waiter, waiter_prepared, waiter_repository, case, request, key, scope)
    async with authorization_factory() as clean:
        assert (
            await clean.scalar(
                text(
                    "select count(*) from authority_idempotency_records where idempotency_key=:key"
                ),
                {"key": str(key)},
            )
            == 1
        )
        assert (
            await clean.scalar(
                text(
                    "select count(*) from audit_events where idempotency_reference=(select id "
                    "from authority_idempotency_records where idempotency_key=:key)"
                ),
                {"key": str(key)},
            )
            == 2
        )
        await clean.rollback()
