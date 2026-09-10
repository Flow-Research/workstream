"""Authorized request custody through the real AUTH adapter and PostgreSQL."""

from __future__ import annotations

from tests.projects.guide_compilation.helpers import runtime_configuration

from app.modules.authorization.api import ProjectGuideCompilationRequestOrigin
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.modules.authorization.api import (
    ActorIdentityFacts,
    ActorKind as PublicActorKind,
    ProjectGuideCompilationRequestFacts,
)
from app.modules.authorization.guide_compilation import (
    ProjectGuideCompilationAuthorizationAdapter,
)
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    HumanAuthorizationContext,
    IdentityLinkStatus,
)
from app.modules.projects.guide_compilation.contracts import (
    CompilationRecoveryClassification,
)
from app.modules.projects.guide_compilation.repository import (
    GuideCompilationIntegrityError,
)
from app.modules.projects.guide_compilation.service import GuideCompilationService

from .helpers import context, identity, persistence_facts, seed_database


def _request(values: dict[str, UUID]) -> ProjectGuideCompilationRequestFacts:
    attempt_identity = identity(context(values))
    persist = persistence_facts(values, uuid4(), attempt_identity)
    names = ProjectGuideCompilationRequestFacts.__dataclass_fields__
    return ProjectGuideCompilationRequestFacts(**{name: asdict(persist)[name] for name in names})


async def _seed_human(database_url: str, values: dict[str, UUID]) -> tuple[UUID, UUID, UUID]:
    human, link, grant = uuid4(), uuid4(), uuid4()
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into actor_profiles(id,actor_kind,status,provisioning_method,"
                    "created_by) values(:human,'human','active','automatic_first_access','test')"
                ),
                {"human": str(human)},
            )
            await connection.execute(
                text(
                    "insert into actor_identity_links(id,actor_profile_id,issuer,subject,"
                    "subject_kind,status,linked_by,last_verified_at) values"
                    "(:link,:human,'https://identity.flowresearch.tech',:subject,'human',"
                    "'active','test',:now)"
                ),
                {
                    "link": str(link),
                    "human": str(human),
                    "subject": f"compilation-{human}",
                    "now": datetime.now(UTC),
                },
            )
            await connection.execute(text("alter table admin_role_grants disable trigger user"))
            await connection.execute(
                text(
                    "insert into admin_role_grants(id,target_actor_profile_id,role,scope_type,"
                    "scope_project_id,status,version,granted_by_system_principal,grant_reason) "
                    "values(:grant,:human,'project_manager','project',:project,'active',1,"
                    "'workstream:system:bootstrap','authorized compilation test')"
                ),
                {
                    "grant": grant,
                    "human": str(human),
                    "project": str(values["project"]),
                },
            )
            await connection.execute(text("alter table admin_role_grants enable trigger user"))
    finally:
        await engine.dispose()
    return human, link, grant


@pytest.mark.asyncio
async def test_request_rejects_caller_identity_drift_before_authority(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    human, link, grant = await _seed_human(clean_postgres_database, values)
    actor = ActorIdentityFacts(human, link, PublicActorKind.HUMAN)
    facts = _request(values)
    drifted = identity(context(values)).model_copy(update={"guide_version": "guide.v2"})
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            with pytest.raises(GuideCompilationIntegrityError, match="do not match"):
                await _authorized_service(session, actor).authorize_request(
                    origin=ProjectGuideCompilationRequestOrigin(trigger="project_manager"),
                    actor=actor,
                    facts=facts,
                    identity=drifted,
                    runtime_configuration=runtime_configuration(),
                )
            counts = (
                await session.execute(
                    text(
                        "select (select count(*) from project_guide_compilation_attempts),"
                        "(select count(*) from audit_events where action_id="
                        "'project.guide_compilation.request')"
                    )
                )
            ).one()
            await session.rollback()
        assert counts == (0, 0)
    finally:
        await engine.dispose()


def _authorized_service(
    session: AsyncSession, actor: ActorIdentityFacts
) -> GuideCompilationService:
    context_value = HumanAuthorizationContext(
        actor_profile_id=actor.actor_profile_id,
        actor_kind=ActorKind.HUMAN,
        actor_status=ActorStatus.ACTIVE,
        identity_link_id=actor.identity_link_id,
        identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    repository = AdminAuthorizationRepository(session)
    authorization = AuthorizationService(session, context_value, admin_repository=repository)
    prepared = PreparedAuthorizationService(session, context_value, authorization, repository)
    adapter = ProjectGuideCompilationAuthorizationAdapter(authorization, prepared)
    return GuideCompilationService(session, adapter)


@pytest.mark.asyncio
async def test_authorized_request_commits_one_bound_receipt_and_exact_replay(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    human, link, grant = await _seed_human(clean_postgres_database, values)
    actor = ActorIdentityFacts(human, link, PublicActorKind.HUMAN)
    facts = _request(values)
    attempt_identity = identity(context(values))
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            receipt = await _authorized_service(session, actor).authorize_request(
                origin=ProjectGuideCompilationRequestOrigin(trigger="project_manager"),
                actor=actor,
                facts=facts,
                identity=attempt_identity,
                runtime_configuration=runtime_configuration(),
            )
        assert receipt.classification is CompilationRecoveryClassification.RESERVED
        async with factory() as session:
            replay = await _authorized_service(session, actor).authorize_request(
                origin=ProjectGuideCompilationRequestOrigin(trigger="project_manager"),
                actor=actor,
                facts=facts,
                identity=attempt_identity,
                runtime_configuration=runtime_configuration(),
            )
            counts = (
                await session.execute(
                    text(
                        "select (select count(*) from project_guide_compilation_attempts),"
                        "(select count(*) from project_guide_compilation_request_operations),"
                        "(select count(*) from audit_events where action_id="
                        "'project.guide_compilation.request')"
                    )
                )
            ).one()
            await session.rollback()
        assert replay == receipt
        assert counts == (1, 1, 1)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("revoked_authority", ["identity_link", "project_manager_grant"])
async def test_revoked_pm_cannot_recover_request(clean_postgres_database, revoked_authority):
    from app.modules.authorization.api import AuthorizationDenied

    values = await seed_database(clean_postgres_database)
    human, link, grant = await _seed_human(clean_postgres_database, values)
    actor = ActorIdentityFacts(human, link, PublicActorKind.HUMAN)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    facts = _request(values)
    origin = ProjectGuideCompilationRequestOrigin(trigger="project_manager")
    try:
        async with factory() as session:
            await _authorized_service(session, actor).authorize_request(
                actor=actor,
                facts=facts,
                identity=identity(context(values)),
                origin=origin,
                runtime_configuration=runtime_configuration(),
            )
        async with factory() as session, session.begin():
            if revoked_authority == "identity_link":
                await session.execute(
                    text(
                        "update actor_identity_links set status='revoked',revoked_by='test',revoked_at=now(),revoked_reason='test revocation' where id=:id"
                    ),
                    {"id": str(link)},
                )
            else:
                # Seed the committed revoked state; this test exercises replay admission,
                # while AUTH's grant-revocation service has its own operation tests.
                await session.execute(text("alter table admin_role_grants disable trigger user"))
                await session.execute(
                    text(
                        "update admin_role_grants set status='revoked',version=2,revoked_by_actor_profile_id=:actor,revoked_by_admin_role_grant_id=:grant,revoked_at=now(),revoked_reason='test revocation' where id=:grant"
                    ),
                    {"actor": str(human), "grant": grant},
                )
                await session.execute(text("alter table admin_role_grants enable trigger user"))
        async with factory() as session:
            with pytest.raises(AuthorizationDenied):
                await _authorized_service(session, actor).authorize_request(
                    actor=actor,
                    facts=facts,
                    identity=identity(context(values)),
                    origin=origin,
                    runtime_configuration=runtime_configuration(),
                )
            assert (
                await session.scalar(
                    text(
                        "select count(*) from audit_events where action_id='project.guide_compilation.request'"
                    )
                )
                == 1
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("authority", ["identity_link", "grant"])
async def test_pm_replay_holds_current_authority_until_receipt_classification(
    clean_postgres_database, monkeypatch, authority
):
    import asyncio
    from app.modules.projects.guide_compilation import service as service_module

    values = await seed_database(clean_postgres_database)
    human, link, grant = await _seed_human(clean_postgres_database, values)
    actor = ActorIdentityFacts(human, link, PublicActorKind.HUMAN)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    facts, origin = (
        _request(values),
        ProjectGuideCompilationRequestOrigin(trigger="project_manager"),
    )
    entered, release, revoke_started = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original = service_module._request_receipt

    async def classify(repository, operation):
        assert repository._session.in_transaction()
        entered.set()
        await release.wait()
        return await original(repository, operation)

    async def replay():
        async with factory() as session:
            return await _authorized_service(session, actor).authorize_request(
                actor=actor,
                facts=facts,
                identity=identity(context(values)),
                origin=origin,
                runtime_configuration=runtime_configuration(),
            )

    async def revoke():
        async with factory() as session, session.begin():
            revoke_started.set()
            if authority == "identity_link":
                await session.execute(
                    text(
                        "update actor_identity_links set status='revoked',revoked_by='test',revoked_at=now(),revoked_reason='test revocation' where id=:id"
                    ),
                    {"id": str(link)},
                )
            else:
                await session.execute(
                    text(
                        "update admin_role_grants set status='revoked',version=2,revoked_by_actor_profile_id=:actor,revoked_by_admin_role_grant_id=:grant,revoked_at=now(),revoked_reason='replay race' where id=:grant"
                    ),
                    {"actor": str(human), "grant": grant},
                )

    pending = []
    try:
        if authority == "grant":
            # Fixture setup precedes the race so no ALTER TABLE lock can mask
            # whether AUTH retains its actual grant row lock during classification.
            async with factory() as session, session.begin():
                await session.execute(text("alter table admin_role_grants disable trigger user"))
        first = await replay()
        monkeypatch.setattr(service_module, "_request_receipt", classify)
        replay_task = asyncio.create_task(replay())
        pending.append(replay_task)
        await asyncio.wait_for(entered.wait(), 5)
        revoke_task = asyncio.create_task(revoke())
        pending.append(revoke_task)
        await asyncio.wait_for(revoke_started.wait(), 5)
        done, _ = await asyncio.wait({revoke_task}, timeout=0.2)
        assert not done, "revocation escaped the replay transaction's authority lock"
        release.set()
        assert await asyncio.wait_for(replay_task, 5) == first
        await asyncio.wait_for(revoke_task, 5)
    finally:
        release.set()
        for task in pending:
            if not task.done():
                task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        if authority == "grant":
            async with factory() as session, session.begin():
                await session.execute(text("alter table admin_role_grants enable trigger user"))
        await engine.dispose()
