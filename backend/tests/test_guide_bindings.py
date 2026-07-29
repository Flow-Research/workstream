"""PostgreSQL proof for exact hidden guide-source binding."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.hashing import canonical_json_hash
from app.interfaces.artifact_operations import GuideSourceBindingRequest
from app.modules.actors.models import ActorProfile
from app.modules.artifacts.guide_bindings import (
    GuideSourceBindingError,
    GuideSourceBindingService,
)
from app.modules.artifacts.models import (
    ArtifactContent,
    ArtifactPutAttempt,
    ArtifactReplica,
    ArtifactStorageNamespace,
    ArtifactVerificationJob,
    GuideSourceArtifactBinding,
)
from app.modules.artifacts.schemas import (
    ArtifactAuthorityDeniedError,
    GuideSourceBindingAuthorityFacts,
)
from app.modules.authorization.prepared import PreparedAuthorizationHandle
from app.modules.projects.models import (
    GuideSourceArtifactIngest,
    GuideSourceSnapshot,
    GuideSourceSnapshotItem,
    Project,
    ProjectGuide,
    ProjectSetupRun,
)


class _AllowBindingAuthority:
    """Test-only fixed authority; production composition cannot import it."""

    def __init__(self, *, deny: bool = False) -> None:
        self.handle = object.__new__(PreparedAuthorizationHandle)
        self.deny = deny
        self.facts: list[GuideSourceBindingAuthorityFacts] = []

    async def consume(self, **values: Any) -> None:
        assert values["prepared_authorization"] is self.handle
        self.facts.append(values["facts"])
        if self.deny:
            raise ArtifactAuthorityDeniedError("binding denied")


async def _seed_binding_lineage(session, *, verified: bool = True) -> dict[str, UUID]:
    ids = {
        name: uuid4()
        for name in (
            "actor",
            "project",
            "guide",
            "snapshot",
            "item",
            "run",
            "content",
            "replica",
            "attempt",
            "job",
        )
    }
    digest = "sha256:" + "a" * 64
    namespace_fingerprint = "sha256:" + "b" * 64
    session.add(
        ActorProfile(
            id=str(ids["actor"]),
            actor_kind="human",
            status="active",
            provisioning_method="automatic_first_access",
            created_by="test",
        )
    )
    session.add(
        Project(
            id=str(ids["project"]),
            name="Guide binding",
            slug=f"guide-binding-{ids['project']}",
            status="draft",
        )
    )
    await session.flush()
    session.add(
        ProjectGuide(
            id=str(ids["guide"]),
            project_id=str(ids["project"]),
            version="v1",
            status="draft",
            content_markdown="# Guide",
            created_by="test",
        )
    )
    await session.flush()
    snapshot_hash = canonical_json_hash({"item": str(ids["item"])})
    session.add(
        GuideSourceSnapshot(
            id=str(ids["snapshot"]),
            project_id=str(ids["project"]),
            guide_id=str(ids["guide"]),
            guide_version="v1",
            manifest_schema_version="v1",
            manifest_json={"item": str(ids["item"])},
            bundle_hash=snapshot_hash,
            captured_by=str(ids["actor"]),
        )
    )
    await session.flush()
    session.add(
        GuideSourceSnapshotItem(
            id=str(ids["item"]),
            source_snapshot_id=str(ids["snapshot"]),
            item_order=0,
            source_kind="file",
            durable_ref="guide.pdf",
            ingestion_adapter="pdf",
            content_hash="caller-metadata-is-not-authority",
            media_type="application/pdf",
        )
    )
    session.add(
        ProjectSetupRun(
            id=str(ids["run"]),
            project_id=str(ids["project"]),
            guide_id=str(ids["guide"]),
            guide_version="v1",
            source_snapshot_id=str(ids["snapshot"]),
            source_snapshot_hash=snapshot_hash,
            setup_generation=1,
            status="queued",
            current_step="queued",
            created_by="test",
        )
    )
    session.add(
        GuideSourceArtifactIngest(
            id=str(uuid4()),
            source_item_id=str(ids["item"]),
            actor_profile_id=str(ids["actor"]),
            sha256=digest,
            byte_count=42,
            media_type="application/pdf",
        )
    )
    session.add(
        ArtifactStorageNamespace(
            id="primary",
            backend="local",
            adapter="local",
            provider_profile="test",
            namespace_descriptor={"root": "test"},
            namespace_fingerprint=namespace_fingerprint,
        )
    )
    session.add(
        ArtifactContent(
            id=str(ids["content"]),
            sha256=digest,
            byte_count=42,
            media_type="application/pdf",
        )
    )
    await session.flush()
    session.add(
        ArtifactReplica(
            id=str(ids["replica"]),
            content_id=str(ids["content"]),
            storage_namespace_id="primary",
            namespace_fingerprint=namespace_fingerprint,
            adapter="local",
            provider_profile="test",
            provider_object_ref=f"objects/{ids['content']}",
            verification_state="verified" if verified else "pending",
            availability_state="available" if verified else "unknown",
            integrity_state="valid" if verified else "unknown",
        )
    )
    await session.flush()
    session.add(
        ArtifactPutAttempt(
            id=str(ids["attempt"]),
            producer_request_type="guide",
            producer_type="actor_profile",
            producer_ref=str(ids["actor"]),
            project_id=str(ids["project"]),
            guide_source_item_id=str(ids["item"]),
            sha256=digest,
            byte_count=42,
            media_type="application/pdf",
            storage_namespace_id="primary",
            namespace_fingerprint=namespace_fingerprint,
            canonical_target="sha256/" + "a" * 64,
            operation_identity="sha256:" + "c" * 64,
            request_digest="sha256:" + "d" * 64,
            status="object_confirmed",
            replica_id=str(ids["replica"]),
            terminal_result_code="object_confirmed",
            terminal_at=datetime.now(UTC),
        )
    )
    await session.flush()
    session.add(
        ArtifactVerificationJob(
            id=str(ids["job"]),
            originating_put_attempt_id=str(ids["attempt"]),
            replica_id=str(ids["replica"]),
            status="verified" if verified else "pending",
            attempt_count=1 if verified else 0,
            maximum_attempts=3,
            terminal_result_code="verified" if verified else None,
            terminal_at=datetime.now(UTC) if verified else None,
        )
    )
    await session.commit()
    return ids


def _request(ids: dict[str, UUID], authority: _AllowBindingAuthority, **changes: Any):
    values = {
        "prepared_authorization": authority.handle,
        "project_id": ids["project"],
        "guide_id": ids["guide"],
        "guide_source_snapshot_id": ids["snapshot"],
        "source_item_id": ids["item"],
        "project_setup_run_id": ids["run"],
        "setup_generation": 1,
        "logical_role": "guide_source_original",
        "verified_content_id": ids["content"],
    }
    values.update(changes)
    return GuideSourceBindingRequest(**values)


@pytest.mark.asyncio
async def test_binding_is_exact_immutable_and_idempotent(isolated_database_env: str) -> None:
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            ids = await _seed_binding_lineage(session)
        first_authority = _AllowBindingAuthority()
        async with factory() as session, session.begin():
            first = await GuideSourceBindingService(session, first_authority).bind_guide_source(
                _request(ids, first_authority)
            )
        replay_authority = _AllowBindingAuthority()
        async with factory() as session, session.begin():
            replay = await GuideSourceBindingService(session, replay_authority).bind_guide_source(
                _request(ids, replay_authority)
            )
        assert not first.replayed
        assert replay.replayed
        assert replay.binding_id == first.binding_id
        assert first_authority.facts[0].verified_replica_id == ids["replica"]
        async with factory() as session:
            assert await session.scalar(select(func.count(GuideSourceArtifactBinding.id))) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["unverified", "cross_project", "stale_generation"])
async def test_binding_fails_closed_before_authority_or_effect(
    isolated_database_env: str,
    failure: str,
) -> None:
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            ids = await _seed_binding_lineage(session, verified=failure != "unverified")
            if failure == "stale_generation":
                session.add(
                    ProjectSetupRun(
                        id=str(uuid4()),
                        project_id=str(ids["project"]),
                        guide_id=str(ids["guide"]),
                        guide_version="v1",
                        source_snapshot_id=str(ids["snapshot"]),
                        source_snapshot_hash=(
                            await session.get(GuideSourceSnapshot, str(ids["snapshot"]))
                        ).bundle_hash,
                        setup_generation=2,
                        status="queued",
                        current_step="queued",
                        created_by="test",
                    )
                )
                await session.commit()
        authority = _AllowBindingAuthority()
        request = _request(
            ids,
            authority,
            project_id=uuid4() if failure == "cross_project" else ids["project"],
        )
        with pytest.raises(GuideSourceBindingError):
            async with factory() as session, session.begin():
                await GuideSourceBindingService(session, authority).bind_guide_source(request)
        assert authority.facts == []
        async with factory() as session:
            assert await session.scalar(select(func.count(GuideSourceArtifactBinding.id))) == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_binding_denial_rolls_back_without_effect(isolated_database_env: str) -> None:
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            ids = await _seed_binding_lineage(session)
        authority = _AllowBindingAuthority(deny=True)
        with pytest.raises(ArtifactAuthorityDeniedError):
            async with factory() as session, session.begin():
                await GuideSourceBindingService(session, authority).bind_guide_source(
                    _request(ids, authority)
                )
        async with factory() as session:
            assert await session.scalar(select(func.count(GuideSourceArtifactBinding.id))) == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_default_live_binding_authority_denies(isolated_database_env: str) -> None:
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            ids = await _seed_binding_lineage(session)
        authority = _AllowBindingAuthority()
        with pytest.raises(ArtifactAuthorityDeniedError):
            async with factory() as session, session.begin():
                await GuideSourceBindingService(session).bind_guide_source(
                    _request(ids, authority)
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_binding_creates_one_business_effect(isolated_database_env: str) -> None:
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            ids = await _seed_binding_lineage(session)

        async def bind_once() -> bool:
            authority = _AllowBindingAuthority()
            async with factory() as session, session.begin():
                result = await GuideSourceBindingService(session, authority).bind_guide_source(
                    _request(ids, authority)
                )
                return result.replayed

        assert sorted(await asyncio.gather(bind_once(), bind_once())) == [False, True]
        async with factory() as session:
            assert await session.scalar(select(func.count(GuideSourceArtifactBinding.id))) == 1
    finally:
        await engine.dispose()
