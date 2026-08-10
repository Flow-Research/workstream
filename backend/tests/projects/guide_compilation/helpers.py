"""Small canonical fixtures shared by guide-compilation behavior tests."""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.db import models as _all_models  # noqa: F401
from app.interfaces.project_agents import (
    CompilationFinding,
    GuideSourceMaterial,
    ProjectGuideCompilationContext,
    ProjectGuideCompilationResult,
    SubmissionArtifactPolicyProposal,
    VerifiedGuideMaterialSnapshot,
)
from app.modules.authorization.api import (
    ActorIdentityFacts,
    ActorKind,
    ProjectGuideCompilationExecutePersistFacts,
    project_guide_compilation_execute_resource_digest,
)
from app.modules.checkers.catalogue import (
    build_pre_submission_checker_catalogue,
    project_guide_pre_submission_capabilities,
)
from app.modules.projects.guide_compilation.contracts import (
    CompilationAttemptIdentity,
    accepted_compilation_result,
)
from app.modules.projects.post_submit_policy import (
    project_guide_post_submission_capabilities,
)

SHA256 = "sha256:" + "a" * 64


def ids() -> dict[str, UUID]:
    """Return complete unrelated identifiers for one test scenario."""
    return {
        name: uuid4()
        for name in (
            "actor",
            "link",
            "wrong_link",
            "project",
            "guide",
            "snapshot",
            "setup_1",
            "setup_2",
            "setup_3",
            "operation",
            "request",
            "key",
            "audit",
        )
    }


def context(values: dict[str, UUID], *, generation: int = 1) -> ProjectGuideCompilationContext:
    """Build one exact ART-verified compilation context."""
    material = GuideSourceMaterial(
        project_id=str(values["project"]),
        guide_id=str(values["guide"]),
        guide_version="v1",
        source_snapshot_id=str(values["snapshot"]),
        source_snapshot_hash=SHA256,
        guide_material={"content_markdown": "Canonical project guide."},
        verified_artifact_material=True,
        source_items=[
            {
                "source_kind": "uploaded_file",
                "ingestion_adapter": "artifact_store",
                "source_item_id": str(UUID("11111111-1111-1111-1111-111111111111")),
                "extraction_usage_id": str(UUID("22222222-2222-2222-2222-222222222222")),
                "canonical_output_sha256": SHA256,
            }
        ],
    )
    return ProjectGuideCompilationContext(
        material=VerifiedGuideMaterialSnapshot.from_material(material),
        setup_run_id=values[f"setup_{generation}"],
        setup_generation=generation,
        instruction_version="v1",
        agent_identity="project-guide-compilation-agent-v1",
        pre_submission_capabilities=project_guide_pre_submission_capabilities(
            build_pre_submission_checker_catalogue()
        ),
        post_submission_capabilities=project_guide_post_submission_capabilities(),
    )


def result() -> ProjectGuideCompilationResult:
    """Return the smallest semantically valid unified result."""
    return ProjectGuideCompilationResult(
        status="draft_ready",
        findings=(
            CompilationFinding(
                severity="info", code="guide.ready", message="Guide is complete."
            ),
        ),
        submission_artifact_policy=SubmissionArtifactPolicyProposal(
            maximum_file_size_bytes=1_000,
            maximum_package_size_bytes=10_000,
            required_artifacts=("submission",),
        ),
        agent_version="v1",
    )


def identity(
    compilation_context: ProjectGuideCompilationContext,
) -> CompilationAttemptIdentity:
    """Derive the trusted attempt identity."""
    return CompilationAttemptIdentity.from_context(compilation_context, agent_version="v1")


def service_actor(values: dict[str, UUID]) -> ActorIdentityFacts:
    """Return the only fixed service actor admitted by future execution."""
    return ActorIdentityFacts(
        actor_profile_id=values["actor"],
        identity_link_id=values["link"],
        actor_kind=ActorKind.SERVICE,
        service_identity="workstream.project.setup",
    )


def persistence_facts(
    values: dict[str, UUID],
    attempt_id: UUID,
    attempt_identity: CompilationAttemptIdentity,
    *,
    predecessor_id: UUID | None = None,
) -> ProjectGuideCompilationExecutePersistFacts:
    """Bind all public execution facts to one accepted result."""
    accepted = accepted_compilation_result(result())
    hashes = accepted.component_hashes
    facts = ProjectGuideCompilationExecutePersistFacts(
        project_id=attempt_identity.project_id,
        guide_id=attempt_identity.guide_id,
        guide_version=attempt_identity.guide_version,
        source_snapshot_id=attempt_identity.source_snapshot_id,
        source_snapshot_hash=attempt_identity.source_snapshot_hash,
        canonical_input_hash=attempt_identity.canonical_input_hash,
        guide_material_hash=attempt_identity.guide_material_hash,
        setup_run_id=attempt_identity.setup_run_id,
        setup_generation=attempt_identity.setup_generation,
        operation_id=values["operation"],
        request_id=values["request"],
        idempotency_key=values["key"],
        pre_catalogue_id=attempt_identity.pre_catalogue_id,
        pre_catalogue_version=attempt_identity.pre_catalogue_version,
        pre_catalogue_schema_version=attempt_identity.pre_catalogue_schema_version,
        pre_catalogue_manifest_hash=attempt_identity.pre_catalogue_manifest_hash,
        post_catalogue_id=attempt_identity.post_catalogue_id,
        post_catalogue_version=attempt_identity.post_catalogue_version,
        post_catalogue_schema_version=attempt_identity.post_catalogue_schema_version,
        post_catalogue_manifest_hash=attempt_identity.post_catalogue_manifest_hash,
        agent_identity=attempt_identity.agent_identity,
        agent_version=attempt_identity.agent_version,
        instruction_version=attempt_identity.instruction_version,
        expected_predecessor_compilation_id=predecessor_id,
        attempt_id=attempt_id,
        provider_idempotency_key=attempt_identity.provider_idempotency_key(),
        result_hash=accepted.result_hash,
        sufficiency_component_hash=hashes.sufficiency_hash,
        artifact_policy_component_hash=hashes.artifact_policy_hash,
        requirement_inventory_component_hash=hashes.requirement_inventory_hash,
        pre_submit_policy_component_hash=hashes.pre_submit_hash,
        post_submit_policy_component_hash=hashes.post_submit_hash,
        capability_suggestions_component_hash=hashes.capability_suggestions_hash,
        setup_notes_component_hash=hashes.setup_notes_hash,
        resource_context_digest=SHA256,
    )
    return replace(
        facts,
        resource_context_digest=project_guide_compilation_execute_resource_digest(
            service_actor(values), facts
        ),
    )


async def seed_database(database_url: str, *, generations: int = 1) -> dict[str, UUID]:
    """Seed only canonical parent rows needed by hidden persistence tests."""
    values = ids()
    sql_values = {name: str(value) for name, value in values.items()}
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into actor_profiles(id,actor_kind,status,provisioning_method,"
                    "service_identity,created_by) values(:actor,'service','active',"
                    "'manual_service_provisioning','workstream.project.setup','test')"
                ),
                sql_values,
            )
            await connection.execute(
                text(
                    "insert into actor_identity_links(id,actor_profile_id,issuer,subject,"
                    "subject_kind,status,linked_by) values(:link,:actor,'workstream-internal',"
                    "'workstream.project.setup','service','active','test')"
                ),
                sql_values,
            )
            await connection.execute(text("alter table projects disable trigger user"))
            await connection.execute(
                text(
                    "insert into projects(id,name,slug,status) values"
                    "(:project,'Compilation project',:slug,'draft')"
                ),
                {**sql_values, "slug": f"compilation-{values['project']}"},
            )
            await connection.execute(text("alter table projects enable trigger user"))
            for table in (
                "project_guides",
                "guide_source_snapshots",
                "project_setup_runs",
            ):
                await connection.execute(text(f"alter table {table} disable trigger user"))
            await connection.execute(
                text(
                    "insert into project_guides(id,project_id,version,status,content_markdown,"
                    "created_by) values(:guide,:project,'v1','draft','# Guide','test')"
                ),
                sql_values,
            )
            await connection.execute(
                text(
                    "insert into guide_source_snapshots(id,project_id,guide_id,guide_version,"
                    "manifest_schema_version,manifest_json,bundle_hash,captured_by) values"
                    "(:snapshot,:project,:guide,'v1','guide_source_snapshot.v1','{}'::json,"
                    ":hash,'test')"
                ),
                {**sql_values, "hash": SHA256},
            )
            for generation in range(1, generations + 1):
                await connection.execute(
                    text(
                        "insert into project_setup_runs(id,project_id,guide_id,guide_version,"
                        "source_snapshot_id,source_snapshot_hash,setup_generation,status,"
                        "current_step,created_by) values(:setup,:project,:guide,'v1',:snapshot,"
                        ":hash,:generation,'queued','guide_material_verified','test')"
                    ),
                    {
                        **sql_values,
                        "setup": str(values[f"setup_{generation}"]),
                        "hash": SHA256,
                        "generation": generation,
                    },
                )
            for table in reversed(
                ("project_guides", "guide_source_snapshots", "project_setup_runs")
            ):
                await connection.execute(text(f"alter table {table} enable trigger user"))
    finally:
        await engine.dispose()
    return values


async def insert_authorization_evidence(
    database_url: str,
    values: dict[str, UUID],
    attempt_id: UUID,
    *,
    resource_context_digest: str,
    action_id: str = "project.guide_compilation.execute",
    permission_id: str = "project.guide_compilation.execute",
) -> UUID:
    """Insert exact future execute evidence for one hidden persistence test."""
    event_id = uuid4()
    sql_values = {name: str(value) for name, value in values.items()} | {
        "audit": str(event_id),
        "action": action_id,
        "permission": permission_id,
        "resource_digest": resource_context_digest,
    }
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into audit_events(id,entity_type,entity_id,event_type,actor_id,"
                    "actor_roles,claim_snapshot,auth_source,is_dev_auth,event_payload,"
                    "event_domain,event_version,actor_ref_kind,request_id,correlation_id,"
                    "permission_id,action_id,reason,project_id,resource_type,resource_id,"
                    "after_facts) values"
                    "(:audit,'authorization_decision',:audit,'SensitiveAuthorizationAllowed',"
                    ":actor,'[]'::json,'{}'::json,'local_authority',false,'{}'::json,"
                    "'authority',1,'actor_profile',:request,:operation,:permission,:action,"
                    "'authorization_evaluation',:project,'project_guide_compilation_attempt',"
                    ":attempt,jsonb_build_object('allowed',true,"
                    "'resource_context_digest',cast(:resource_digest as text))::json)"
                ),
                {**sql_values, "attempt": str(attempt_id)},
            )
    finally:
        await engine.dispose()
    return event_id
