"""Real PostgreSQL proofs for hidden unified-compilation projections."""

from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.modules.artifacts.guide_sufficiency_material import (
    SqlAlchemyGuideSufficiencyMaterialAdapter,
)
from app.modules.authorization.api import (
    ArtifactPolicyProjectionFacts,
    GuideSufficiencyProjectionFacts,
    ProjectGuideProjectionAuthorityReceipt,
    artifact_policy_projection_facts_digest,
    artifact_policy_projection_identity,
    guide_sufficiency_projection_facts_digest,
    guide_sufficiency_projection_identity,
    projection_authority_digest,
)
from app.modules.projects.api import (
    ProjectGuideCompilationExecutionCommand,
    ProjectGuideProjectionCommand,
)
from app.modules.projects.guide_compilation.projections import (
    GuideCompilationProjectionService,
)
from app.modules.projects.repository import ProjectRepository

from .helpers import seed_database
from .test_hidden_orchestrator_postgresql import (
    _Runtime,
    _authorized_attempt,
    _port,
)


class _PreparedProjection:
    def __init__(
        self,
        session: AsyncSession,
        identity,
        component: str,
        *,
        resource_type_override: str | None = None,
    ) -> None:
        self._session = session
        self.identity = identity
        self._component = component
        self._resource_type_override = resource_type_override

    async def consume_new(
        self, facts: GuideSufficiencyProjectionFacts | ArtifactPolicyProjectionFacts
    ) -> ProjectGuideProjectionAuthorityReceipt:
        if self._component == "guide_sufficiency":
            facts_digest = guide_sufficiency_projection_facts_digest(facts)
            action = "project.guide_sufficiency.run"
            permission = "project.guide.manage"
            resource_type = "project_guide_sufficiency_projection"
        else:
            facts_digest = artifact_policy_projection_facts_digest(facts)
            action = "project.submission_artifact_policy.derive"
            permission = "project.effective_policy.manage"
            resource_type = "project_submission_artifact_policy_projection"
        resource_digest = projection_authority_digest(
            component=self._component,
            identity=self.identity,
            project_id=facts.project_id,
            facts_digest=facts_digest,
        )
        event_id = uuid4()
        await self._session.execute(
            text(
                "insert into audit_events(id,entity_type,entity_id,event_type,actor_id,"
                "actor_roles,claim_snapshot,auth_source,is_dev_auth,event_payload,"
                "event_domain,event_version,actor_ref_kind,request_id,correlation_id,"
                "permission_id,action_id,reason,project_id,resource_type,resource_id,"
                "after_facts) values(:id,'authorization_decision',:id,"
                "'SensitiveAuthorizationAllowed',:actor,'[]'::json,'{}'::json,"
                "'local_authority',false,'{}'::json,'authority',1,'actor_profile',"
                ":request_id,:correlation_id,:permission,:action,"
                "'authorization_evaluation',:project_id,:resource_type,:resource_id,"
                "jsonb_build_object('allowed',true,'resource_context_digest',"
                "cast(:resource_digest as text))::json)"
            ),
            {
                "id": str(event_id),
                "actor": str(self.identity.actor_profile_id),
                "request_id": str(self.identity.operation_id),
                "correlation_id": str(self.identity.correlation_id),
                "permission": permission,
                "action": action,
                "project_id": str(facts.project_id),
                "resource_type": self._resource_type_override or resource_type,
                "resource_id": str(self.identity.operation_id),
                "resource_digest": resource_digest,
            },
        )
        return ProjectGuideProjectionAuthorityReceipt(
            decision_event_id=event_id,
            actor_profile_id=self.identity.actor_profile_id,
            identity_link_id=self.identity.identity_link_id,
            service_identity=self.identity.service_identity,
            resource_context_digest=resource_digest,
        )

    async def validate_replay(
        self,
        facts: GuideSufficiencyProjectionFacts | ArtifactPolicyProjectionFacts,
        stored_decision_id: UUID,
    ) -> None:
        count = await self._session.scalar(
            text(
                "select count(*) from audit_events where id=:id and actor_id=:actor "
                "and project_id=:project"
            ),
            {
                "id": str(stored_decision_id),
                "actor": str(self.identity.actor_profile_id),
                "project": str(facts.project_id),
            },
        )
        if count != 1:
            raise AssertionError("stored authorization decision is unavailable")


class _ProjectionAuthorization:
    def __init__(
        self,
        session: AsyncSession,
        values: dict[str, UUID],
        *,
        resource_type_override: str | None = None,
    ) -> None:
        self._session = session
        self._values = values
        self._resource_type_override = resource_type_override

    @asynccontextmanager
    async def prepare_sufficiency_projection(self, locator):
        yield _PreparedProjection(
            self._session,
            guide_sufficiency_projection_identity(
                attempt_id=locator.attempt_id,
                actor_profile_id=self._values["actor"],
                identity_link_id=self._values["link"],
            ),
            "guide_sufficiency",
            resource_type_override=self._resource_type_override,
        )

    @asynccontextmanager
    async def prepare_artifact_policy_projection(self, locator):
        yield _PreparedProjection(
            self._session,
            artifact_policy_projection_identity(
                attempt_id=locator.attempt_id,
                actor_profile_id=self._values["actor"],
                identity_link_id=self._values["link"],
            ),
            "submission_artifact_policy",
            resource_type_override=self._resource_type_override,
        )


async def _persist_compilation(
    database_url: str, values: dict[str, UUID], *, outcome=None
):
    requested = await _authorized_attempt(database_url, values)
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    runtime = _Runtime(outcome) if outcome is not None else _Runtime()
    try:
        receipt = await _port(factory, runtime).execute(
            ProjectGuideCompilationExecutionCommand(attempt_id=requested.attempt_id)
        )
        assert runtime.calls == 1
        return requested.attempt_id, receipt.compilation_id
    finally:
        await engine.dispose()


async def _project_both(database_url: str, values: dict[str, UUID]):
    attempt_id, compilation_id = await _persist_compilation(database_url, values)
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    def authorization(session: AsyncSession) -> _ProjectionAuthorization:
        return _ProjectionAuthorization(session, values)

    service = GuideCompilationProjectionService(
        factory,
        material_factory=SqlAlchemyGuideSufficiencyMaterialAdapter,
        sufficiency_authorization_factory=authorization,
        policy_authorization_factory=authorization,
    )
    command = ProjectGuideProjectionCommand(attempt_id=attempt_id)
    try:
        sufficiency = await service.project_guide_sufficiency(command)
        sufficiency_replay = await service.project_guide_sufficiency(command)
        policy = await service.project_submission_artifact_policy(command)
        policy_replay = await service.project_submission_artifact_policy(command)
        return (
            attempt_id,
            compilation_id,
            sufficiency,
            sufficiency_replay,
            policy,
            policy_replay,
        )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_projects_both_components_once_and_replays_without_new_effects(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    (
        _attempt_id,
        compilation_id,
        sufficiency,
        sufficiency_replay,
        policy,
        policy_replay,
    ) = await _project_both(
        clean_postgres_database,
        values,
    )
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        assert sufficiency.disposition == "projected"
        assert sufficiency_replay.disposition == "replayed"
        assert policy.disposition == "projected"
        assert policy_replay.disposition == "replayed"
        assert sufficiency_replay.output_id == sufficiency.output_id
        assert policy_replay.output_id == policy.output_id

        async with factory() as session:
            counts = (
                await session.execute(
                    text(
                        "select "
                        "(select count(*) from guide_sufficiency_reports),"
                        "(select count(*) from guide_sufficiency_report_source_usages),"
                        "(select count(*) from submission_artifact_policies),"
                        "(select count(*) from project_guide_component_projection_operations),"
                        "(select count(*) from audit_events where action_id="
                        "'project.guide_sufficiency.run'),"
                        "(select count(*) from audit_events where action_id="
                        "'project.submission_artifact_policy.derive')"
                    )
                )
            ).one()
            setup = (
                await session.execute(
                    text(
                        "select status,current_step,output_sufficiency_report_id,"
                        "output_submission_artifact_policy_id,"
                        "output_post_submit_checker_policy_id from project_setup_runs "
                        "where id=:id"
                    ),
                    {"id": str(values["setup_1"])},
                )
            ).one()
            rows = (
                await session.execute(
                    text(
                        "select component,compilation_id,output_id,output_digest "
                        "from project_guide_component_projection_operations "
                        "order by component"
                    )
                )
            ).all()
            await session.rollback()

        assert counts == (1, 1, 1, 2, 1, 1)
        assert setup == ("queued", "queued", None, None, None)
        assert {row.compilation_id for row in rows} == {compilation_id}
        assert {row.output_id for row in rows} == {
            sufficiency.output_id,
            policy.output_id,
        }
        assert {row.output_digest for row in rows} == {
            sufficiency.output_digest,
            policy.output_digest,
        }
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_repository_lists_projection_lineage(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    (
        _attempt_id,
        _compilation_id,
        sufficiency,
        _sufficiency_replay,
        policy,
        _policy_replay,
    ) = await _project_both(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory.begin() as session:
            repository = ProjectRepository(session)

            snapshots = await repository.list_guide_source_snapshots(
                str(values["project"]),
                str(values["guide"]),
                "v1",
            )
            items = await repository.lock_guide_source_snapshot_items(
                str(values["snapshot"])
            )
            diagnostic_report = (
                await repository.get_diagnostic_sufficiency_report_for_snapshot(
                    str(values["snapshot"])
                )
            )
            reports = await repository.list_guide_sufficiency_reports(
                str(values["project"]),
                str(values["guide"]),
            )
            policies = await repository.list_submission_artifact_policies(
                str(values["project"]),
                str(values["guide"]),
            )
            locked_policy = await repository.lock_submission_artifact_policy_diagnostic(
                str(policy.output_id),
                str(values["project"]),
                str(values["guide"]),
                "v1",
            )
            approved_policy = await repository.get_approved_submission_artifact_policy(
                str(values["project"]),
                "v1",
                str(values["snapshot"]),
            )

        assert [snapshot.id for snapshot in snapshots] == [str(values["snapshot"])]
        assert len(items) == 1
        assert items[0].source_snapshot_id == str(values["snapshot"])
        assert diagnostic_report is None
        assert [report.id for report in reports] == [str(sufficiency.output_id)]
        assert [stored_policy.id for stored_policy in policies] == [str(policy.output_id)]
        assert locked_policy is not None
        assert locked_policy.id == str(policy.output_id)
        assert approved_policy is None
    finally:
        await engine.dispose()
