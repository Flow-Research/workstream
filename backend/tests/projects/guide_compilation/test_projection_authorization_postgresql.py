"""PostgreSQL atomicity proofs for guide-compilation projection authority."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.auth import (
    artifact_policy_projection_authorization,
    guide_sufficiency_projection_authorization,
)
from app.modules.artifacts.guide_sufficiency_material import (
    SqlAlchemyGuideSufficiencyMaterialAdapter,
)
from app.modules.authorization import prepared as prepared_module
from app.modules.authorization.runtime import AuthorizationEvidenceUnavailable
from app.modules.projects.api import ProjectGuideProjectionCommand
from app.modules.projects.guide_compilation import projections as projection_module
from app.modules.projects.guide_compilation.projections import (
    GuideCompilationProjectionService,
    ProjectGuideProjectionError,
)

from .helpers import seed_database
from .test_projection_postgresql import _persist_compilation


def _service(factory):
    return GuideCompilationProjectionService(
        factory,
        material_factory=SqlAlchemyGuideSufficiencyMaterialAdapter,
        sufficiency_authorization_factory=guide_sufficiency_projection_authorization,
        policy_authorization_factory=artifact_policy_projection_authorization,
    )


async def _effect_counts(factory, *, include_usage: bool = False):
    usage = (
        "(select count(*) from guide_sufficiency_report_source_usages)," if include_usage else ""
    )
    async with factory() as session:
        counts = (
            await session.execute(
                text(
                    "select (select count(*) from guide_sufficiency_reports),"
                    f"{usage}"
                    "(select count(*) from project_guide_component_projection_operations),"
                    "(select count(*) from audit_events where action_id="
                    "'project.guide_sufficiency.run')"
                )
            )
        ).one()
        await session.rollback()
    return counts


async def _policy_ready(factory, attempt_id):
    service = _service(factory)
    command = ProjectGuideProjectionCommand(attempt_id=attempt_id)
    result = await service.project_guide_sufficiency(command)
    assert result.disposition == "projected"
    return service, command


@pytest.mark.asyncio
async def test_projection_same_operation_concurrency_is_single_effect(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    attempt_id, _ = await _persist_compilation(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        command = ProjectGuideProjectionCommand(attempt_id=attempt_id)
        first, second = await asyncio.gather(
            _service(factory).project_guide_sufficiency(command),
            _service(factory).project_guide_sufficiency(command),
        )
        assert {first.disposition, second.disposition} == {"projected", "replayed"}
        assert first.output_id == second.output_id
        assert await _effect_counts(factory) == (1, 1, 1)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_policy_projection_same_operation_concurrency_is_single_effect(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    attempt_id, _ = await _persist_compilation(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        service, command = await _policy_ready(factory, attempt_id)
        first, second = await asyncio.gather(
            service.project_submission_artifact_policy(command),
            _service(factory).project_submission_artifact_policy(command),
        )
        assert {first.disposition, second.disposition} == {"projected", "replayed"}
        assert first.output_id == second.output_id
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
async def test_projection_close_failure_rolls_back_authority_and_product(
    clean_postgres_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = await seed_database(clean_postgres_database)
    attempt_id, _ = await _persist_compilation(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    original_close = prepared_module.PreparedAuthorizationService.close

    def fail_close(prepared) -> None:
        original_close(prepared)
        raise AuthorizationEvidenceUnavailable("close failed")

    monkeypatch.setattr(prepared_module.PreparedAuthorizationService, "close", fail_close)
    try:
        with pytest.raises(ProjectGuideProjectionError, match="service_authority_denied"):
            await _service(factory).project_guide_sufficiency(
                ProjectGuideProjectionCommand(attempt_id=attempt_id)
            )
        assert await _effect_counts(factory) == (0, 0, 0)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_projection_consume_callback_observes_no_product_rows(
    clean_postgres_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = await seed_database(clean_postgres_database)
    attempt_id, _ = await _persist_compilation(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    original_consume = prepared_module.PreparedAuthorizationService.consume
    observed = False

    async def observe_before_consume(prepared, *args, **kwargs):
        nonlocal observed
        counts = (
            await prepared._session.execute(
                text(
                    "select (select count(*) from guide_sufficiency_reports),"
                    "(select count(*) from guide_sufficiency_report_source_usages),"
                    "(select count(*) from project_guide_component_projection_operations),"
                    "(select count(*) from audit_events where action_id="
                    "'project.guide_sufficiency.run')"
                )
            )
        ).one()
        assert counts == (0, 0, 0, 0)
        observed = True
        return await original_consume(prepared, *args, **kwargs)

    monkeypatch.setattr(
        prepared_module.PreparedAuthorizationService, "consume", observe_before_consume
    )
    try:
        receipt = await _service(factory).project_guide_sufficiency(
            ProjectGuideProjectionCommand(attempt_id=attempt_id)
        )
        assert receipt.disposition == "projected"
        assert observed is True
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_policy_projection_consumes_before_product_staging(
    clean_postgres_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = await seed_database(clean_postgres_database)
    attempt_id, _ = await _persist_compilation(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    service, command = await _policy_ready(factory, attempt_id)
    original_consume = prepared_module.PreparedAuthorizationService.consume
    observed = False

    async def observe_before_consume(prepared, action_id, *args, **kwargs):
        nonlocal observed
        if action_id.value == "project.submission_artifact_policy.derive":
            counts = (
                await prepared._session.execute(
                    text(
                        "select (select count(*) from submission_artifact_policies),"
                        "(select count(*) from project_guide_component_projection_operations "
                        "where component='submission_artifact_policy'),"
                        "(select count(*) from audit_events where action_id="
                        "'project.submission_artifact_policy.derive')"
                    )
                )
            ).one()
            assert counts == (0, 0, 0)
            observed = True
        return await original_consume(prepared, action_id, *args, **kwargs)

    monkeypatch.setattr(
        prepared_module.PreparedAuthorizationService, "consume", observe_before_consume
    )
    try:
        result = await service.project_submission_artifact_policy(command)
        assert result.disposition == "projected"
        assert observed is True
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_projection_late_failure_rolls_back_authority_and_product(
    clean_postgres_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = await seed_database(clean_postgres_database)
    attempt_id, _ = await _persist_compilation(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    original_operation = projection_module._new_operation

    def invalid_operation(*args, **kwargs):
        operation = original_operation(*args, **kwargs)
        operation.authorization_decision_event_id = str(uuid4())
        return operation

    monkeypatch.setattr(projection_module, "_new_operation", invalid_operation)
    try:
        with pytest.raises(ProjectGuideProjectionError):
            await _service(factory).project_guide_sufficiency(
                ProjectGuideProjectionCommand(attempt_id=attempt_id)
            )
        assert await _effect_counts(factory, include_usage=True) == (0, 0, 0, 0)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_projection_denial_has_no_product_or_allowed_evidence(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    attempt_id, _ = await _persist_compilation(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "update actor_identity_links set status='revoked',revoked_by=:actor,"
                "revoked_at=now(),revoked_reason='test' where id=:link"
            ),
            {"actor": str(values["actor"]), "link": str(values["link"])},
        )
    try:
        with pytest.raises(ProjectGuideProjectionError, match="service_authority_denied"):
            await _service(factory).project_guide_sufficiency(
                ProjectGuideProjectionCommand(attempt_id=attempt_id)
            )
        assert await _effect_counts(factory) == (0, 0, 0)
    finally:
        await engine.dispose()
