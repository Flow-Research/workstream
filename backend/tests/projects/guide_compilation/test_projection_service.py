"""Failure and ordering proofs for hidden compilation projections."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.interfaces.project_agents import SubmissionArtifactPolicyProposal
from app.modules.artifacts.guide_sufficiency_material import (
    SqlAlchemyGuideSufficiencyMaterialAdapter,
)
from app.modules.authorization.api import AuthorizationDenied
from app.modules.projects.api import (
    ProjectGuideProjectionCommand,
    ProjectGuideProjectionError,
)
from app.modules.projects.guide_compilation.projections import (
    GuideCompilationProjectionService,
    _is_exact_projection_source_state,
)

from .helpers import result, seed_database
from .test_projection_postgresql import (
    _ProjectionAuthorization,
    _persist_compilation,
)
from .test_hidden_orchestrator_postgresql import _authorized_attempt


class _CountingMaterial:
    def __init__(self) -> None:
        self.calls = 0

    async def load(self, request):
        self.calls += 1
        raise AssertionError(f"unexpected material load: {request}")


class _CountingSqlMaterial:
    def __init__(self, session: AsyncSession) -> None:
        self.calls = 0
        self._inner = SqlAlchemyGuideSufficiencyMaterialAdapter(session)

    async def load(self, request):
        self.calls += 1
        return await self._inner.load(request)


class _ReplayDeniedAuthorization(_ProjectionAuthorization):
    @asynccontextmanager
    async def prepare_sufficiency_projection(self, locator):
        async with super().prepare_sufficiency_projection(locator) as capability:
            original = capability.validate_replay

            async def denied(_facts, _decision_id):
                raise AuthorizationDenied("replay denied")

            capability.validate_replay = denied
            try:
                yield capability
            finally:
                capability.validate_replay = original


class _MalformedAuthorization(_ProjectionAuthorization):
    def __init__(self, *args, mode: str, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._mode = mode

    @asynccontextmanager
    async def prepare_sufficiency_projection(self, locator):
        async with super().prepare_sufficiency_projection(locator) as capability:
            if self._mode == "identity":
                capability.identity = replace(
                    capability.identity, output_id=uuid4()
                )
            else:
                original = capability.consume_new

                async def malformed_receipt(facts):
                    receipt = await original(facts)
                    return replace(receipt, actor_profile_id=uuid4())

                capability.consume_new = malformed_receipt
            yield capability


def _service(
    factory,
    values: dict[str, UUID],
    *,
    material_factory=SqlAlchemyGuideSufficiencyMaterialAdapter,
    authorization_factory=None,
):
    if authorization_factory is None:
        def authorization_factory(session):
            return _ProjectionAuthorization(session, values)
    return GuideCompilationProjectionService(
        factory,
        material_factory=material_factory,
        sufficiency_authorization_factory=authorization_factory,
        policy_authorization_factory=authorization_factory,
    )


@pytest.mark.asyncio
async def test_deny_default_precedes_any_material_load(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    attempt_id, _ = await _persist_compilation(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    material = _CountingMaterial()
    service = GuideCompilationProjectionService(
        factory,
        material_factory=lambda _session: material,
    )
    try:
        with pytest.raises(ProjectGuideProjectionError) as failure:
            await service.project_guide_sufficiency(
                ProjectGuideProjectionCommand(attempt_id=attempt_id)
            )
        assert failure.value.code == "service_authority_denied"
        assert material.calls == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_reserved_attempt_stops_before_auth_and_material(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    requested = await _authorized_attempt(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    material = _CountingMaterial()
    authorization_calls = 0

    def forbidden_authorization(_session):
        nonlocal authorization_calls
        authorization_calls += 1
        raise AssertionError("authorization must not be prepared")

    service = _service(
        factory,
        values,
        material_factory=lambda _session: material,
        authorization_factory=forbidden_authorization,
    )
    try:
        with pytest.raises(ProjectGuideProjectionError) as failure:
            await service.project_guide_sufficiency(
                ProjectGuideProjectionCommand(attempt_id=requested.attempt_id)
            )
        assert failure.value.code == "attempt_unavailable"
        assert authorization_calls == 0
        assert material.calls == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_policy_deny_default_precedes_any_material_load(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    attempt_id, _ = await _persist_compilation(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    material = _CountingMaterial()
    service = GuideCompilationProjectionService(
        factory,
        material_factory=lambda _session: material,
    )
    try:
        with pytest.raises(ProjectGuideProjectionError) as failure:
            await service.project_submission_artifact_policy(
                ProjectGuideProjectionCommand(attempt_id=attempt_id)
            )
        assert failure.value.code == "service_authority_denied"
        assert material.calls == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["blocked", "unprojectable"])
async def test_forbidden_or_unprojectable_component_stops_before_auth_and_material(
    clean_postgres_database: str,
    kind: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    compiled = result()
    if kind == "blocked":
        compiled = compiled.model_copy(
            update={"status": "guide_blocked", "submission_artifact_policy": None}
        )
        expected = "component_forbidden"
    else:
        compiled = compiled.model_copy(
            update={
                "submission_artifact_policy": SubmissionArtifactPolicyProposal(
                    maximum_file_size_bytes=1,
                    maximum_package_size_bytes=2,
                    required_artifacts=("C:artifact",),
                )
            }
        )
        expected = "component_unprojectable"
    attempt_id, _ = await _persist_compilation(
        clean_postgres_database, values, outcome=compiled
    )
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    material = _CountingMaterial()
    authorization_calls = 0

    def forbidden_authorization(_session):
        nonlocal authorization_calls
        authorization_calls += 1
        raise AssertionError("authorization must not be prepared")

    service = _service(
        factory,
        values,
        material_factory=lambda _session: material,
        authorization_factory=forbidden_authorization,
    )
    try:
        with pytest.raises(ProjectGuideProjectionError) as failure:
            await service.project_submission_artifact_policy(
                ProjectGuideProjectionCommand(attempt_id=attempt_id)
            )
        assert failure.value.code == expected
        assert authorization_calls == 0
        assert material.calls == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_changed_replay_revalidates_once_without_consuming_new_authority(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    attempt_id, _ = await _persist_compilation(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    service = _service(factory, values)
    command = ProjectGuideProjectionCommand(attempt_id=attempt_id)
    try:
        await service.project_guide_sufficiency(command)
        materials: list[_CountingSqlMaterial] = []

        def material_factory(session: AsyncSession) -> _CountingSqlMaterial:
            material = _CountingSqlMaterial(session)
            materials.append(material)
            return material

        denied = _service(
            factory,
            values,
            material_factory=material_factory,
            authorization_factory=lambda session: _ReplayDeniedAuthorization(
                session, values
            ),
        )
        with pytest.raises(ProjectGuideProjectionError) as failure:
            await denied.project_guide_sufficiency(command)
        assert failure.value.code == "service_authority_denied"
        assert sum(material.calls for material in materials) == 1
        async with factory() as session:
            counts = (
                await session.execute(
                    text(
                        "select (select count(*) from guide_sufficiency_reports),"
                        "(select count(*) from project_guide_component_projection_operations),"
                        "(select count(*) from audit_events where action_id="
                        "'project.guide_sufficiency.run')"
                    )
                )
            ).one()
            await session.rollback()
        assert counts == (1, 1, 1)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_same_component_race_converges_to_one_row_and_event(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    attempt_id, _ = await _persist_compilation(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    service = _service(factory, values)
    command = ProjectGuideProjectionCommand(attempt_id=attempt_id)
    try:
        receipts = await asyncio.gather(
            service.project_guide_sufficiency(command),
            service.project_guide_sufficiency(command),
        )
        assert {receipt.disposition for receipt in receipts} == {
            "projected",
            "replayed",
        }
        assert receipts[0].output_id == receipts[1].output_id
        async with factory() as session:
            counts = (
                await session.execute(
                    text(
                        "select (select count(*) from guide_sufficiency_reports),"
                        "(select count(*) from project_guide_component_projection_operations),"
                        "(select count(*) from audit_events where action_id="
                        "'project.guide_sufficiency.run')"
                    )
                )
            ).one()
            await session.rollback()
        assert counts == (1, 1, 1)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_policy_race_converges_to_one_row_and_event(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    attempt_id, _ = await _persist_compilation(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    service = _service(factory, values)
    command = ProjectGuideProjectionCommand(attempt_id=attempt_id)
    try:
        await service.project_guide_sufficiency(command)
        receipts = await asyncio.gather(
            service.project_submission_artifact_policy(command),
            service.project_submission_artifact_policy(command),
        )
        assert {receipt.disposition for receipt in receipts} == {
            "projected",
            "replayed",
        }
        assert receipts[0].output_id == receipts[1].output_id
        async with factory() as session:
            counts = (
                await session.execute(
                    text(
                        "select (select count(*) from submission_artifact_policies),"
                        "(select count(*) from project_guide_component_projection_operations "
                        "where component='submission_artifact_policy'),"
                        "(select count(*) from audit_events where action_id="
                        "'project.submission_artifact_policy.derive')"
                    )
                )
            ).one()
            await session.rollback()
        assert counts == (1, 1, 1)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["identity", "receipt"])
async def test_malformed_authority_rolls_back_all_projection_effects(
    clean_postgres_database: str,
    mode: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    attempt_id, _ = await _persist_compilation(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    def malformed(session: AsyncSession) -> _MalformedAuthorization:
        return _MalformedAuthorization(session, values, mode=mode)

    service = _service(factory, values, authorization_factory=malformed)
    try:
        with pytest.raises(ProjectGuideProjectionError) as failure:
            await service.project_guide_sufficiency(
                ProjectGuideProjectionCommand(attempt_id=attempt_id)
            )
        assert failure.value.code == "service_authority_denied"
        async with factory() as session:
            counts = (
                await session.execute(
                    text(
                        "select (select count(*) from guide_sufficiency_reports),"
                        "(select count(*) from project_guide_component_projection_operations),"
                        "(select count(*) from audit_events where action_id="
                        "'project.guide_sufficiency.run')"
                    )
                )
            ).one()
            await session.rollback()
        assert counts == (0, 0, 0)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "assignment",
    [
        "status='dispatch_pending'",
        "status='enqueue_failed'",
        "status='enqueue_identity_mismatch'",
        "status='running_sufficiency_agent'",
        "status='sufficiency_blocked'",
        "status='running_policy_derivation_agent'",
        "status='policy_draft_ready'",
        "status='running_post_submit_derivation_agent'",
        "status='post_submit_setup_blocked'",
        "status='post_submit_policy_compiled'",
        "status='setup_blocked'",
        "status='failed'",
        "current_step='guide_sufficiency'",
        "celery_task_id='00000000-0000-0000-0000-000000000001'",
        "continuation_started_at=now()",
        "error_code='projection_error'",
        "error_summary='projection error'",
        "post_submit_derivation_summary='{}'::json",
        "started_at=now()",
        "finished_at=now()",
    ],
)
async def test_every_non_unified_setup_shape_denies_without_projection_effects(
    clean_postgres_database: str,
    assignment: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    attempt_id, _ = await _persist_compilation(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("alter table project_setup_runs disable trigger user")
            )
            try:
                await connection.execute(
                    text(
                        f"update project_setup_runs set {assignment} where id=:setup_id"
                    ),
                    {"setup_id": str(values["setup_1"])},
                )
            finally:
                await connection.execute(
                    text("alter table project_setup_runs enable trigger user")
                )
        service = _service(factory, values)
        with pytest.raises(ProjectGuideProjectionError) as failure:
            await service.project_guide_sufficiency(
                ProjectGuideProjectionCommand(attempt_id=attempt_id)
            )
        assert failure.value.code == "source_state_unavailable"
        async with factory() as session:
            counts = (
                await session.execute(
                    text(
                        "select "
                        "(select count(*) from guide_sufficiency_reports),"
                        "(select count(*) from project_guide_component_projection_operations),"
                        "(select count(*) from audit_events where resource_type in "
                        "('project_guide_sufficiency_projection',"
                        "'project_submission_artifact_policy_projection'))"
                    )
                )
            ).one()
            await session.rollback()
        assert counts == (0, 0, 0)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_non_draft_guide_and_stale_generation_fail_closed(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    attempt_id, _ = await _persist_compilation(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    service = _service(factory, values)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into project_setup_runs(id,project_id,guide_id,guide_version,"
                    "source_snapshot_id,source_snapshot_hash,setup_generation,status,"
                    "current_step,celery_task_id,created_by) values(:id,:project,:guide,"
                    "'v1',:snapshot,:hash,2,'queued','queued',:task,'test')"
                ),
                {
                    "id": str(values["setup_2"]),
                    "project": str(values["project"]),
                    "guide": str(values["guide"]),
                    "snapshot": str(values["snapshot"]),
                    "hash": "sha256:" + "a" * 64,
                    "task": "00000000-0000-0000-0000-000000000007",
                },
            )
        with pytest.raises(ProjectGuideProjectionError) as stale:
            await service.project_guide_sufficiency(
                ProjectGuideProjectionCommand(attempt_id=attempt_id)
            )
        assert stale.value.code == "source_state_unavailable"

        async with engine.begin() as connection:
            await connection.execute(
                text("delete from project_setup_runs where id=:setup_id"),
                {"setup_id": str(values["setup_2"])},
            )
            await connection.execute(text("alter table project_guides disable trigger user"))
            try:
                await connection.execute(
                    text("update project_guides set status='retired' where id=:guide_id"),
                    {"guide_id": str(values["guide"])},
                )
            finally:
                await connection.execute(
                    text("alter table project_guides enable trigger user")
                )
        with pytest.raises(ProjectGuideProjectionError) as non_draft:
            await service.project_guide_sufficiency(
                ProjectGuideProjectionCommand(attempt_id=attempt_id)
            )
        assert non_draft.value.code == "source_state_unavailable"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_policy_requires_exact_sufficiency_custody(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    attempt_id, _ = await _persist_compilation(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    service = _service(factory, values)
    command = ProjectGuideProjectionCommand(attempt_id=attempt_id)
    try:
        with pytest.raises(ProjectGuideProjectionError) as missing:
            await service.project_submission_artifact_policy(command)
        assert missing.value.code == "source_state_unavailable"
        async with factory() as session:
            assert await session.scalar(
                text(
                    "select count(*) from audit_events where action_id="
                    "'project.submission_artifact_policy.derive'"
                )
            ) == 0
            await session.rollback()

        report = await service.project_guide_sufficiency(command)
        policy = await service.project_submission_artifact_policy(command)
        assert report.disposition == "projected"
        assert policy.disposition == "projected"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_projection_and_authority_roll_back_together_on_custody_failure(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    attempt_id, _ = await _persist_compilation(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    def malformed_authorization(session: AsyncSession) -> _ProjectionAuthorization:
        return _ProjectionAuthorization(
            session,
            values,
            resource_type_override="project_guide_compilation_attempt",
        )

    service = _service(factory, values, authorization_factory=malformed_authorization)
    try:
        with pytest.raises(ProjectGuideProjectionError) as failure:
            await service.project_guide_sufficiency(
                ProjectGuideProjectionCommand(attempt_id=attempt_id)
            )
        assert failure.value.code == "source_state_unavailable"
        async with factory() as session:
            counts = (
                await session.execute(
                    text(
                        "select "
                        "(select count(*) from guide_sufficiency_reports),"
                        "(select count(*) from guide_sufficiency_report_source_usages),"
                        "(select count(*) from project_guide_component_projection_operations),"
                        "(select count(*) from audit_events where action_id="
                        "'project.guide_sufficiency.run')"
                    )
                )
            ).one()
            await session.rollback()
        assert counts == (0, 0, 0, 0)
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    ("target", "field", "value"),
    [
        ("guide", "project_id", "wrong"),
        ("guide", "version", "v2"),
        ("guide", "status", "active"),
        ("snapshot", "project_id", "wrong"),
        ("snapshot", "guide_id", "wrong"),
        ("snapshot", "guide_version", "v2"),
        ("snapshot", "bundle_hash", "sha256:" + "b" * 64),
        ("latest_snapshot", "id", "wrong"),
        ("latest_setup", "id", "wrong"),
        ("setup", "source_snapshot_id", "wrong"),
        ("setup", "source_snapshot_hash", "sha256:" + "b" * 64),
        ("setup", "setup_generation", 2),
        ("setup", "status", "failed"),
        ("setup", "current_step", "guide_sufficiency"),
        ("setup", "celery_task_id", "wrong"),
        ("setup", "continuation_verification_job_id", "job"),
        ("setup", "continuation_started_at", datetime.now(UTC)),
        ("setup", "error_code", "error"),
        ("setup", "error_artifact_incident_id", "incident"),
        ("setup", "error_summary", "error"),
        ("setup", "post_submit_derivation_summary", {}),
        ("setup", "started_at", datetime.now(UTC)),
        ("setup", "finished_at", datetime.now(UTC)),
        ("setup", "output_sufficiency_report_id", "report"),
        ("setup", "output_submission_artifact_policy_id", "policy"),
        ("setup", "output_post_submit_checker_policy_id", "checker"),
    ],
)
def test_source_state_predicate_rejects_every_lineage_and_output_drift(
    target: str,
    field: str,
    value,
) -> None:
    """Kill any removed source, generation, error, or output-state guard."""
    project_id, guide_id, snapshot_id, setup_id = (
        uuid
        for uuid in (
            "00000000-0000-0000-0000-000000000011",
            "00000000-0000-0000-0000-000000000012",
            "00000000-0000-0000-0000-000000000013",
            "00000000-0000-0000-0000-000000000014",
        )
    )
    guide = SimpleNamespace(project_id=project_id, version="v1", status="draft")
    snapshot = SimpleNamespace(
        id=snapshot_id,
        project_id=project_id,
        guide_id=guide_id,
        guide_version="v1",
        bundle_hash="sha256:" + "a" * 64,
    )
    setup = SimpleNamespace(
        id=setup_id,
        source_snapshot_id=snapshot_id,
        source_snapshot_hash=snapshot.bundle_hash,
        setup_generation=1,
        status="queued",
        current_step="queued",
        celery_task_id="task",
        continuation_verification_job_id=None,
        continuation_started_at=None,
        error_code=None,
        error_artifact_incident_id=None,
        error_summary=None,
        post_submit_derivation_summary=None,
        started_at=None,
        finished_at=None,
        output_sufficiency_report_id=None,
        output_submission_artifact_policy_id=None,
        output_post_submit_checker_policy_id=None,
    )
    objects = {
        "guide": guide,
        "snapshot": snapshot,
        "setup": setup,
        "latest_snapshot": SimpleNamespace(id=snapshot_id),
        "latest_setup": SimpleNamespace(id=setup_id),
    }
    setattr(objects[target], field, value)
    seed = SimpleNamespace(
        project_id=UUID(project_id),
        guide_id=UUID(guide_id),
        guide_version="v1",
        source_snapshot_hash=snapshot.bundle_hash,
        setup_generation=1,
    )
    assert not _is_exact_projection_source_state(
        guide,
        snapshot,
        setup,
        objects["latest_snapshot"],
        objects["latest_setup"],
        seed,
        "task",
    )
