"""PostgreSQL transaction proof for ART admission consumption."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.artifacts.models import (
    ArtifactBinding,
    ArtifactContent,
    PreSubmitEvidenceSet,
    SubmissionBundleAdmission,
)
from app.modules.artifacts.submission_bindings import (
    SubmissionAdmissionConsumptionService,
)
from app.modules.artifacts.api import SubmissionAdmissionConsumptionError
from app.adapters.tasks import TransactionalSubmissionCreationCommand
from app.modules.tasks.api import SubmissionCreationRequest, SubmissionCreationUnavailable
from app.modules.tasks.models import Submission
from app.modules.tasks.models import AuditEvent
from app.modules.tasks.repository import TaskRepository
from app.api.deps.authorization import compose_hidden_submission_creation_command
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization import prepared as prepared_authorization
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    AuthorizationDenialCode,
    HumanAuthorizationContext,
    IdentityLinkStatus,
    ServiceAuthorizationContext,
    PreparedAuthorizationUnsupported,
)
from app.modules.actors.service_identities import ServiceIdentity
from test_artifact_bindings import _Allow, _lineage, _request


_TABLES = (
    ArtifactContent.__table__,
    PreSubmitEvidenceSet.__table__,
    SubmissionBundleAdmission.__table__,
    ArtifactBinding.__table__,
    Submission.__table__,
    AuditEvent.__table__,
)


def _column_sql(column, dialect) -> str:
    name = dialect.identifier_preparer.quote(column.name)
    type_sql = column.type.compile(dialect=dialect)
    primary = " primary key" if column.primary_key else ""
    return f"{name} {type_sql}{primary}"


@asynccontextmanager
async def _isolated_binding_schema(database_url: str):
    engine = create_async_engine(database_url)
    schema = f"binding_{uuid4().hex}"
    dialect = engine.dialect
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f'create schema "{schema}"'))
            for table in _TABLES:
                columns = ", ".join(_column_sql(column, dialect) for column in table.columns)
                await connection.execute(
                    text(f'create table "{schema}"."{table.name}" ({columns})')
                )
            await connection.execute(
                text(
                    f'create unique index uq_binding_scope on "{schema}".artifact_bindings '
                    "(project_id, resource_type, resource_id, logical_role, scope_version)"
                )
            )
            await connection.execute(
                text(
                    f'alter table "{schema}".artifact_bindings add constraint '
                    "scope_version_predecessor check "
                    "((scope_version=1 and supersedes_binding_id is null) or "
                    "(scope_version>1 and supersedes_binding_id is not null))"
                )
            )
            await connection.execute(
                text(
                    f'create unique index uq_admission_consumer on "{schema}".'
                    "submission_bundle_admissions (consumed_by_submission_id) "
                    "where consumed_by_submission_id is not null"
                )
            )
            await connection.execute(
                text(
                    f'alter table "{schema}".submission_bundle_admissions add constraint '
                    "terminal_shape check ("
                    "(status='ready' and consumed_at is null and "
                    "consumed_by_submission_id is null and "
                    "consumed_by_submission_version is null and stale_at is null and "
                    "stale_reason is null) or "
                    "(status='consumed' and consumed_at is not null and "
                    "consumed_by_submission_id is not null and "
                    "consumed_by_submission_version > 0 and stale_at is null and "
                    "stale_reason is null) or "
                    "(status='stale' and consumed_at is null and "
                    "consumed_by_submission_id is null and "
                    "consumed_by_submission_version is null and stale_at is not null and "
                    "octet_length(stale_reason) between 1 and 500))"
                )
            )
        factory = async_sessionmaker(engine, expire_on_commit=False)
        yield schema, factory
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f'drop schema if exists "{schema}" cascade'))
        await engine.dispose()


async def _set_schema(session, schema: str) -> None:
    await session.execute(text(f'set local search_path to "{schema}"'))


async def _seed(session, schema: str, request) -> None:
    admission, evidence, content = _lineage(request)
    await _set_schema(session, schema)
    await session.execute(
        ArtifactContent.__table__.insert().values(
            id=content.id,
            sha256=content.sha256,
            byte_count=content.byte_count,
        )
    )
    await session.execute(
        PreSubmitEvidenceSet.__table__.insert().values(**vars(evidence))
    )
    await session.execute(
        SubmissionBundleAdmission.__table__.insert().values(
            **vars(admission), durable_intent_id=str(uuid4()), put_attempt_id=str(uuid4()),
            verified_replica_id=str(uuid4()), verification_receipt_id=str(uuid4()),
            put_operation_receipt_id=str(uuid4()), put_observation_receipt_id=None,
            ready_at=text("now()"),
        )
    )


class _FinalDeny:
    async def authorize(self, facts) -> None:
        del facts

    async def prepare(self, facts) -> object:
        del facts
        raise SubmissionCreationUnavailable("submission creation is unavailable")

    async def consume(self, prepared_authorization, facts) -> None:
        del prepared_authorization, facts
        raise AssertionError("unreachable")

    def close(self, prepared_authorization) -> None:
        del prepared_authorization


@pytest.mark.asyncio
async def test_composed_final_denial_rolls_back_task_and_art_rows(
    isolated_database_env: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    art_request = _request()
    context = art_request.task_context
    task = type("LockedTask", (), {
        "id": str(context.task_id),
        "locked_guide_version": "1",
        "locked_post_submit_checker_policy_id": str(uuid4()),
        "locked_post_submit_checker_policy_version": "1",
        "locked_post_submit_checker_policy_hash": "sha256:" + "4" * 64,
        "locked_post_submit_checker_policy_body": {},
        "locked_review_policy_id": str(uuid4()), "locked_review_policy_generation": 1,
        "locked_review_policy_hash": "sha256:" + "5" * 64,
        "locked_revision_policy_id": str(uuid4()), "locked_revision_policy_generation": 1,
        "locked_revision_policy_hash": "sha256:" + "6" * 64,
        "locked_payment_policy_version": "1",
        "locked_guide_source_snapshot_id": str(context.locked_project_context.source_snapshot_id),
        "locked_guide_source_snapshot_hash": context.locked_project_context.source_snapshot_hash,
        "locked_effective_project_submission_artifact_policy_id": str(context.locked_project_context.effective_policy_id),
        "locked_effective_project_submission_artifact_policy_hash": context.locked_project_context.effective_policy_hash,
        "locked_pre_submit_checker_policy_id": str(context.locked_project_context.pre_submit_policy_id),
        "locked_pre_submit_checker_bundle_hash": context.locked_project_context.pre_submit_policy_bundle_hash,
    })()

    async def lock_context(self, request):
        del self, request
        return context

    async def get_task(self, task_id, **kwargs):
        del self, task_id, kwargs
        return task

    monkeypatch.setattr(TaskRepository, "lock_submission_context", lock_context)
    monkeypatch.setattr(TaskRepository, "get_task", get_task)
    async with _isolated_binding_schema(isolated_database_env) as (schema, factory):
        async with factory.begin() as seed:
            await _seed(seed, schema, art_request)
        request = SubmissionCreationRequest(
            admission_id=art_request.admission_id, task_id=context.task_id,
            assignment_id=context.assignment_id, contributor_id=context.contributor_id,
            predecessor_submission_id=None, summary="summary",
            contributor_attestation="attestation",
        )
        async with factory() as session:
            await session.execute(text(f'set search_path to "{schema}"'))
            await session.commit()
            command = TransactionalSubmissionCreationCommand(
                session, authorization=_FinalDeny(),
                admissions=SubmissionAdmissionConsumptionService(session, _Allow()),
            )
            with pytest.raises(SubmissionCreationUnavailable):
                await command.create(request)
        async with factory() as session:
            await _set_schema(session, schema)
            assert await session.scalar(text("select count(*) from submissions")) == 0
            assert await session.scalar(text("select count(*) from artifact_bindings")) == 0
            status = await session.scalar(
                text("select status from submission_bundle_admissions where id=:id"),
                {"id": str(request.admission_id)},
            )
            assert status == "ready"
@pytest.mark.asyncio
async def test_postgresql_consumption_is_concurrent_and_rollback_safe(
    isolated_database_env: str,
) -> None:
    request = _request()
    request = type(request)(
        admission_id=request.admission_id,
        submission_id=request.submission_id,
        submission_version=2,
        task_context=request.task_context,
    )
    async with _isolated_binding_schema(isolated_database_env) as (schema, factory):
        async with factory.begin() as seed:
            await _seed(seed, schema, request)

        async def consume_once():
            async with factory() as session:
                async with session.begin():
                    await _set_schema(session, schema)
                    return await SubmissionAdmissionConsumptionService(
                        session, _Allow()
                    ).consume(request)

        first, second = await asyncio.gather(consume_once(), consume_once())
        assert sorted(result.replayed for result in (first, second)) == [False, True]
        async with factory() as session:
            await _set_schema(session, schema)
            status = await session.scalar(
                text("select status from submission_bundle_admissions where id=:id"),
                {"id": str(request.admission_id)},
            )
            binding_count = await session.scalar(
                text("select count(*) from artifact_bindings where resource_id=:id"),
                {"id": str(request.submission_id)},
            )
            assert status == "consumed"
            assert binding_count == 1

        first_competing = _request(submission_id=uuid4())
        competing = replace(first_competing, admission_id=uuid4())
        async with factory.begin() as seed:
            await _seed(seed, schema, first_competing)
            await _seed(seed, schema, competing)

        async def consume_competing(value):
            async with factory() as session:
                async with session.begin():
                    await _set_schema(session, schema)
                    try:
                        await SubmissionAdmissionConsumptionService(
                            session, _Allow()
                        ).consume(value)
                    except SubmissionAdmissionConsumptionError as exc:
                        return exc.code
                    return (await session.get(
                        SubmissionBundleAdmission, str(value.admission_id)
                    )).status

        outcomes = await asyncio.gather(
            consume_competing(first_competing),
            consume_competing(competing),
        )
        assert sorted(outcomes) == [
            "consumed",
            "stale",
        ]
        async with factory() as session:
            await _set_schema(session, schema)
            binding_count = await session.scalar(
                text("select count(*) from artifact_bindings where resource_id=:id"),
                {"id": str(first_competing.submission_id)},
            )
            statuses = list(
                await session.scalars(
                    text(
                        "select status from submission_bundle_admissions "
                        "where id in (:first,:second) order by status"
                    ),
                    {
                        "first": str(first_competing.admission_id),
                        "second": str(competing.admission_id),
                    },
                )
            )
            assert binding_count == 1
            assert statuses == ["consumed", "stale"]

        rollback_request = _request()
        async with factory.begin() as seed:
            await _seed(seed, schema, rollback_request)
        async with factory() as session:
            transaction = await session.begin()
            await _set_schema(session, schema)
            await SubmissionAdmissionConsumptionService(session, _Allow()).consume(
                rollback_request
            )
            await transaction.rollback()
        async with factory() as session:
            await _set_schema(session, schema)
            status = await session.scalar(
                text(
                    "select status from submission_bundle_admissions where id=:id"
                ),
                {"id": str(rollback_request.admission_id)},
            )
            bindings = await session.scalar(
                text(
                    "select count(*) from artifact_bindings where resource_id=:id"
                ),
                {"id": str(rollback_request.submission_id)},
            )
            assert status == "ready"
            assert bindings == 0


def _wire_hidden_authority(monkeypatch: pytest.MonkeyPatch):
    """Install deterministic TASK/AUTH collaborators for the hidden command."""
    art_request = _request()
    context = art_request.task_context
    request_id, correlation_id, human_link_id, service_actor_id, service_link_id = (
        uuid4() for _ in range(5)
    )
    human = HumanAuthorizationContext(
        actor_profile_id=context.contributor_id,
        actor_kind=ActorKind.HUMAN,
        actor_status=ActorStatus.ACTIVE,
        identity_link_id=human_link_id,
        identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=request_id,
        correlation_id=correlation_id,
    )
    service = ServiceAuthorizationContext(
        actor_profile_id=service_actor_id,
        actor_kind=ActorKind.SERVICE,
        actor_status=ActorStatus.ACTIVE,
        identity_link_id=service_link_id,
        identity_link_status=IdentityLinkStatus.ACTIVE,
        service_identity=ServiceIdentity.ARTIFACT_BINDING,
        request_id=request_id,
        correlation_id=correlation_id,
    )
    task = type("LockedTask", (), {
        "id": str(context.task_id), "locked_guide_version": "1",
        "locked_post_submit_checker_policy_id": str(uuid4()),
        "locked_post_submit_checker_policy_version": "1",
        "locked_post_submit_checker_policy_hash": "sha256:" + "4" * 64,
        "locked_post_submit_checker_policy_body": {},
        "locked_review_policy_id": str(uuid4()), "locked_review_policy_generation": 1,
        "locked_review_policy_hash": "sha256:" + "5" * 64,
        "locked_revision_policy_id": str(uuid4()), "locked_revision_policy_generation": 1,
        "locked_revision_policy_hash": "sha256:" + "6" * 64,
        "locked_payment_policy_version": "1",
        "locked_guide_source_snapshot_id": str(context.locked_project_context.source_snapshot_id),
        "locked_guide_source_snapshot_hash": context.locked_project_context.source_snapshot_hash,
        "locked_effective_project_submission_artifact_policy_id": str(context.locked_project_context.effective_policy_id),
        "locked_effective_project_submission_artifact_policy_hash": context.locked_project_context.effective_policy_hash,
        "locked_pre_submit_checker_policy_id": str(context.locked_project_context.pre_submit_policy_id),
        "locked_pre_submit_checker_bundle_hash": context.locked_project_context.pre_submit_policy_bundle_hash,
    })()

    async def lock_context(_self, _request): return context
    async def get_task(_self, _task_id, **_kwargs): return task
    async def lock_actor(_self, link_id, actor_id):
        is_service = actor_id == service_actor_id
        return (
            type("Link", (), {"id": str(link_id), "actor_profile_id": str(actor_id), "status": "active"})(),
            type("Profile", (), {
                "id": str(actor_id),
                "actor_kind": "service" if is_service else "human",
                "service_identity": service.service_identity.value if is_service else None,
                "status": "active",
            })(),
        )
    async def find_role(_self, **_kwargs):
        return type("Grant", (), {"id": uuid4(), "status": "active", "scope_project_id": None})()
    async def fixed_context(*_args, **_kwargs): return service

    monkeypatch.setattr(TaskRepository, "lock_submission_context", lock_context)
    monkeypatch.setattr(TaskRepository, "get_task", get_task)
    monkeypatch.setattr(AdminAuthorizationRepository, "lock_request_actor", lock_actor)
    monkeypatch.setattr(AdminAuthorizationRepository, "find_active_project_role", find_role)
    monkeypatch.setattr(
        prepared_authorization, "fixed_service_authorization_context", fixed_context
    )
    request = SubmissionCreationRequest(
        admission_id=art_request.admission_id, task_id=context.task_id,
        assignment_id=context.assignment_id, contributor_id=context.contributor_id,
        predecessor_submission_id=None, summary="summary",
        contributor_attestation="attestation",
    )
    return art_request, human, request, request_id, correlation_id


async def _create_hidden(factory, schema, human, request, request_id, correlation_id):
    """Run one hidden command and return its stable result or boundary error."""
    async with factory() as session:
        await session.execute(text(f'set search_path to "{schema}"'))
        await session.commit()
        command = compose_hidden_submission_creation_command(
            session, human, request_id=request_id, correlation_id=correlation_id
        )
        try:
            return await command.create(request)
        except (SubmissionAdmissionConsumptionError, SubmissionCreationUnavailable) as exc:
            return exc


@pytest.mark.asyncio
async def test_live_hidden_authority_commits_one_complete_concurrent_effect(
    isolated_database_env: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Concurrent hidden commands commit exactly one complete authorized effect."""
    art_request, human, request, request_id, correlation_id = _wire_hidden_authority(
        monkeypatch
    )

    async with _isolated_binding_schema(isolated_database_env) as (schema, factory):
        async with factory.begin() as seed:
            await _seed(seed, schema, art_request)
        outcomes = await asyncio.gather(*(
            _create_hidden(factory, schema, human, request, request_id, correlation_id)
            for _ in range(2)
        ))
        assert sum(not isinstance(value, Exception) for value in outcomes) == 1
        failures = [value for value in outcomes if isinstance(value, Exception)]
        assert len(failures) == 1
        assert isinstance(failures[0], SubmissionAdmissionConsumptionError)
        assert failures[0].code == "submission_bundle_admission_already_consumed"
        async with factory() as session:
            await _set_schema(session, schema)
            assert await session.scalar(text("select count(*) from submissions")) == 1
            assert await session.scalar(text("select count(*) from artifact_bindings")) == 1
            assert await session.scalar(
                text(
                    "select count(*) from audit_events where event_domain='authority' "
                    "and event_type='SensitiveAuthorizationAllowed'"
                )
            ) == 2


@pytest.mark.asyncio
async def test_revoked_binding_service_rolls_back_the_hidden_command(
    isolated_database_env: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A revoked fixed-service link leaves every protected effect absent."""
    art_request, human, request, request_id, correlation_id = _wire_hidden_authority(
        monkeypatch
    )
    async def revoked_context(*_args, **_kwargs):
        raise PreparedAuthorizationUnsupported(
            AuthorizationDenialCode.IDENTITY_LINK_REVOKED
        )
    monkeypatch.setattr(
        prepared_authorization, "fixed_service_authorization_context", revoked_context
    )
    async with _isolated_binding_schema(isolated_database_env) as (schema, factory):
        denied_art_request = replace(
            art_request, admission_id=uuid4(), submission_id=uuid4()
        )
        async with factory.begin() as seed:
            await _seed(seed, schema, denied_art_request)
        denied = await _create_hidden(
            factory, schema, human,
            replace(request, admission_id=denied_art_request.admission_id),
            request_id, correlation_id,
        )
        assert isinstance(denied, SubmissionAdmissionConsumptionError)
        assert denied.code == "submission_bundle_admission_unavailable"
        async with factory() as session:
            await _set_schema(session, schema)
            assert await session.scalar(text("select count(*) from submissions")) == 0
            assert await session.scalar(text("select count(*) from artifact_bindings")) == 0
            assert await session.scalar(
                text(
                    "select count(*) from submission_bundle_admissions "
                    "where id=:id and status='ready'"
                ),
                {"id": str(denied_art_request.admission_id)},
            ) == 1
            assert await session.scalar(
                text("select count(*) from audit_events")
            ) == 0
