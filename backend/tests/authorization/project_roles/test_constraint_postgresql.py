"""Real PostgreSQL active-role uniqueness fallback at the public route."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.api_controls import StructuredHTTPException
from app.core.identifiers import new_record_id
from app.db.errors import integrity_constraint_name
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.actors.service import ResolvedActor
from app.modules.authorization import router as authorization_router
from app.modules.authorization.models import ProjectRoleGrant, ProjectRoleQualificationSnapshot
from app.modules.authorization.project_role_schemas import ProjectRoleGrantIssueBody
from app.modules.authorization.project_role_service import ProjectRoleGrantMutationService
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.schemas import ClaimedReservation, ProjectRole
from tests.authorization.project_roles.fixtures import (
    RoleMutationCase,
    authorization_database_env as authorization_database_env,
    authorization_factory as authorization_factory,
    mutation_runtime,
    project_role_qualification,
    role_mutation_case as role_mutation_case,
)


async def _seed_existing_reviewer(session, case: RoleMutationCase) -> None:
    qualification = project_role_qualification()
    snapshot = ProjectRoleQualificationSnapshot(
        id=new_record_id(),
        project_id=str(case.project_id),
        actor_profile_id=str(case.target_id),
        requested_role="reviewer",
        skills_snapshot=qualification["skills_snapshot"],
        reputation_snapshot=qualification["reputation_snapshot"],
        prior_project_work_refs=[],
        external_expertise_refs=[],
        captured_by_actor_profile_id=str(case.caller_id),
        captured_by_admin_role_grant_id=case.manager_grant_id,
    )
    session.add(snapshot)
    await session.flush()
    session.add(
        ProjectRoleGrant(
            id=new_record_id(),
            project_id=str(case.project_id),
            actor_profile_id=str(case.target_id),
            role="reviewer",
            status="active",
            version=1,
            grant_method="manual",
            qualification_snapshot_id=snapshot.id,
            granted_by_actor_profile_id=str(case.caller_id),
            granted_by_admin_role_grant_id=case.manager_grant_id,
            grant_reason="Existing reviewer role",
        )
    )
    await session.commit()


async def _assert_conflict_left_no_losing_effects(factory, case, context, key, claim_id) -> None:
    async with factory() as clean:
        assert (
            await clean.scalar(
                text(
                    "select count(*) from project_role_grants where project_id=:project "
                    "and actor_profile_id=:actor and role='reviewer' and status='active'"
                ),
                {"project": str(case.project_id), "actor": str(case.target_id)},
            )
            == 1
        )
        assert (
            await clean.scalar(
                text(
                    "select count(*) from project_role_qualification_snapshots where "
                    "project_id=:project and actor_profile_id=:actor and requested_role='reviewer'"
                ),
                {"project": str(case.project_id), "actor": str(case.target_id)},
            )
            == 1
        )
        assert (
            await clean.scalar(
                text(
                    "select count(*) from authority_idempotency_records where idempotency_key=:key"
                ),
                {"key": str(key)},
            )
            == 0
        )
        rows = (
            await clean.execute(
                text(
                    "select event_type, denial_code, idempotency_reference from audit_events "
                    "where request_id=:request and correlation_id=:correlation "
                    "and action_id='project_role_grant.issue'"
                ),
                {"request": str(context.request_id), "correlation": str(context.correlation_id)},
            )
        ).all()
        assert rows == [("SensitiveAuthorizationDenied", "project_role_grant_exists", None)]
        assert (
            await clean.scalar(
                text("select count(*) from audit_events where idempotency_reference=:claim"),
                {"claim": str(claim_id)},
            )
            == 0
        )
        await clean.rollback()


@pytest.mark.asyncio
async def test_project_role_issue_unique_index_conflict_has_no_losing_effects(
    authorization_factory,
    role_mutation_case: RoleMutationCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = role_mutation_case
    context = case.context
    key = new_record_id()
    constraint_errors: list[IntegrityError] = []
    original_find = AdminAuthorizationRepository.find_active_project_role
    original_add = AdminAuthorizationRepository.add_project_role_grant
    original_reserve = ProjectRoleGrantMutationService.reserve
    lookups = 0
    claim_ids = []

    async def miss_winner_until_insert(repository, **kwargs):
        nonlocal lookups
        lookups += 1
        if lookups <= 2:
            return None
        return await original_find(repository, **kwargs)

    async def capture_unique_violation(repository, grant):
        try:
            return await original_add(repository, grant)
        except IntegrityError as error:
            constraint_errors.append(error)
            raise

    async def capture_claim(service, **kwargs):
        reservation = await original_reserve(service, **kwargs)
        assert isinstance(reservation, ClaimedReservation)
        claim_ids.append(reservation.claim.record_id)
        return reservation

    async with mutation_runtime(authorization_factory, context) as (
        session,
        _repository,
        prepared,
    ):
        await _seed_existing_reviewer(session, case)
        caller = await session.get(ActorProfile, str(case.caller_id))
        caller_link = await session.get(ActorIdentityLink, str(case.caller_link_id))
        assert caller is not None and caller_link is not None
        monkeypatch.setattr(
            AdminAuthorizationRepository, "find_active_project_role", miss_winner_until_insert
        )
        monkeypatch.setattr(
            AdminAuthorizationRepository, "add_project_role_grant", capture_unique_violation
        )
        monkeypatch.setattr(ProjectRoleGrantMutationService, "reserve", capture_claim)
        payload = ProjectRoleGrantIssueBody(
            target_actor_profile_id=case.target_id,
            role=ProjectRole.REVIEWER,
            qualification=project_role_qualification(),
            reason="Simulated visibility lag to active-role index",
        )
        with pytest.raises(StructuredHTTPException) as conflict:
            await authorization_router.issue_project_role_grant(
                project_id=case.project_id,
                payload=payload,
                idempotency_key=key,
                resolved=ResolvedActor(caller, caller_link),
                prepared=prepared,
                session=session,
            )
        assert conflict.value.status_code == 409
        assert conflict.value.error_code == "project_role_grant_exists"
        assert lookups == 3
        assert len(constraint_errors) == 1
        assert len(claim_ids) == 1
        assert (
            integrity_constraint_name(constraint_errors[0])
            == "uq_project_role_grants_active_exact_role"
        )

    await _assert_conflict_left_no_losing_effects(
        authorization_factory, case, context, key, claim_ids[0]
    )
