"""Real-PostgreSQL proof for exact compilation-context reconstruction."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.artifacts.guide_sufficiency_material import (
    SqlAlchemyGuideSufficiencyMaterialAdapter,
)
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.checkers.catalogue import (
    build_pre_submission_checker_catalogue,
    project_guide_pre_submission_capabilities,
)
from app.modules.projects.guide_compilation.context import (
    build_project_guide_compilation_context,
)
from app.modules.projects.guide_compilation.contracts import CompilationAttemptIdentity
from app.modules.projects.guide_compilation.repository import (
    GuideCompilationIntegrityError,
)
from app.modules.projects.guide_compilation.service import (
    load_compilation_execution_state,
)
from app.modules.projects.post_submit_policy import (
    project_guide_post_submission_capabilities,
)

from .helpers import context, identity, seed_database
from .test_authorized_request_service import _authorized_service, _request, _seed_human


@pytest.mark.asyncio
async def test_context_rebuilds_the_exact_authorized_art_backed_identity(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    actor_id, link_id, _grant_id = await _seed_human(clean_postgres_database, values)
    actor = ActorIdentityFacts(actor_id, link_id, ActorKind.HUMAN)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            request = await _authorized_service(session, actor).authorize_request(
                actor=actor,
                facts=_request(values),
                identity=identity(context(values)),
            )
        async with factory() as session:
            state = await load_compilation_execution_state(session, request.attempt_id)
        async with factory() as session:
            rebuilt = await build_project_guide_compilation_context(
                session,
                state=state,
                material=SqlAlchemyGuideSufficiencyMaterialAdapter(session),
                pre_submission_capabilities=project_guide_pre_submission_capabilities(
                    build_pre_submission_checker_catalogue()
                ),
                post_submission_capabilities=project_guide_post_submission_capabilities(),
            )

        assert rebuilt == context(values)
        assert CompilationAttemptIdentity.from_context(rebuilt) == state.identity
        assert rebuilt.material.source_lineage[0].extraction_usage_id is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_context_drift_fails_before_dispatch(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    actor_id, link_id, _grant_id = await _seed_human(clean_postgres_database, values)
    actor = ActorIdentityFacts(actor_id, link_id, ActorKind.HUMAN)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            request = await _authorized_service(session, actor).authorize_request(
                actor=actor,
                facts=_request(values),
                identity=identity(context(values)),
            )
        async with factory() as session:
            state = await load_compilation_execution_state(session, request.attempt_id)
        default_catalogue = build_pre_submission_checker_catalogue()
        drifted_catalogue = build_pre_submission_checker_catalogue(
            disabled_entry_ids={default_catalogue.entries[0].stable_id}
        )
        async with factory() as session:
            with pytest.raises(GuideCompilationIntegrityError, match="identity mismatch"):
                await build_project_guide_compilation_context(
                    session,
                    state=state,
                    material=SqlAlchemyGuideSufficiencyMaterialAdapter(session),
                    pre_submission_capabilities=project_guide_pre_submission_capabilities(
                        drifted_catalogue
                    ),
                    post_submission_capabilities=(
                        project_guide_post_submission_capabilities()
                    ),
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_context_requires_fresh_session_and_current_lineage(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    actor_id, link_id, _grant_id = await _seed_human(clean_postgres_database, values)
    actor = ActorIdentityFacts(actor_id, link_id, ActorKind.HUMAN)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            request = await _authorized_service(session, actor).authorize_request(
                actor=actor,
                facts=_request(values),
                identity=identity(context(values)),
            )
        async with factory() as session:
            state = await load_compilation_execution_state(session, request.attempt_id)
        capabilities = project_guide_pre_submission_capabilities(
            build_pre_submission_checker_catalogue()
        )
        post_capabilities = project_guide_post_submission_capabilities()
        async with factory() as session, session.begin():
            with pytest.raises(GuideCompilationIntegrityError, match="fresh root"):
                await build_project_guide_compilation_context(
                    session,
                    state=state,
                    material=SqlAlchemyGuideSufficiencyMaterialAdapter(session),
                    pre_submission_capabilities=capabilities,
                    post_submission_capabilities=post_capabilities,
                )
        missing = replace(
            state,
            identity=state.identity.model_copy(update={"guide_id": uuid4()}),
        )
        async with factory() as session:
            with pytest.raises(GuideCompilationIntegrityError, match="lineage"):
                await build_project_guide_compilation_context(
                    session,
                    state=missing,
                    material=SqlAlchemyGuideSufficiencyMaterialAdapter(session),
                    pre_submission_capabilities=capabilities,
                    post_submission_capabilities=post_capabilities,
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_context_enforces_the_canonical_prompt_limit(
    clean_postgres_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = await seed_database(clean_postgres_database)
    actor_id, link_id, _grant_id = await _seed_human(clean_postgres_database, values)
    actor = ActorIdentityFacts(actor_id, link_id, ActorKind.HUMAN)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            request = await _authorized_service(session, actor).authorize_request(
                actor=actor,
                facts=_request(values),
                identity=identity(context(values)),
            )
        async with factory() as session:
            state = await load_compilation_execution_state(session, request.attempt_id)
        monkeypatch.setattr(
            "app.modules.projects.guide_compilation.context."
            "MAXIMUM_PROJECT_GUIDE_COMPILATION_PROMPT_BYTES",
            1,
        )
        async with factory() as session:
            with pytest.raises(GuideCompilationIntegrityError, match="exceeds"):
                await build_project_guide_compilation_context(
                    session,
                    state=state,
                    material=SqlAlchemyGuideSufficiencyMaterialAdapter(session),
                    pre_submission_capabilities=project_guide_pre_submission_capabilities(
                        build_pre_submission_checker_catalogue()
                    ),
                    post_submission_capabilities=(
                        project_guide_post_submission_capabilities()
                    ),
                )
    finally:
        await engine.dispose()
