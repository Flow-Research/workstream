"""Small canonical fixtures shared by guide-compilation behavior tests."""

from __future__ import annotations

from app.modules.checkers.catalogue import project_guide_pre_submission_capabilities

from dataclasses import replace
import hashlib
import json
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db import models as _all_models  # noqa: F401
from app.modules.artifacts.models import (
    ArtifactContent, ArtifactReplica, ArtifactStorageNamespace, ArtifactPutAttempt,
    ArtifactOperationReceipt,
)
from app.modules.projects.models import GuideSourceArtifactIngest
from app.modules.projects.api.guide_documents import GuideDocumentManifest, GuideDocumentVersion
from app.interfaces.project_agents import (
    CompilationFinding, GuideEvidenceRef, ProjectGuideCompilationContext,
    ProjectGuideCompilationResult, SubmissionArtifactPolicyProposal,
)
from app.modules.authorization.api import (
    ActorIdentityFacts,
    ActorKind,
    ProjectGuideCompilationExecutePersistFacts,
    project_guide_compilation_execute_resource_digest,
)
from app.modules.checkers.catalogue import (
    build_pre_submission_checker_catalogue,
)
from app.modules.projects.guide_compilation.contracts import (
    CompilationAttemptIdentity,
    accepted_compilation_result,
)
from app.modules.checkers.api.post_submit_catalogue import current_post_submit_catalogue
from app.modules.projects.api.setup_identity import project_guide_compilation_task_id

from app.core.hashing import canonical_json_hash
from app.modules.projects.api.task_examples import task_examples_hash, validate_task_examples

TASK_EXAMPLES = validate_task_examples([{"content": "Review a claim using the project guide."}])
TASK_EXAMPLE_MANIFEST = {"task_examples_hash": task_examples_hash(TASK_EXAMPLES), "task_examples_count": len(TASK_EXAMPLES)}
SHA256 = canonical_json_hash(TASK_EXAMPLE_MANIFEST)
SOURCE_ITEM_ID = UUID("11111111-1111-1111-1111-111111111111")
DOCUMENT_VERSION_ID = UUID("22222222-2222-2222-2222-222222222222")
PUT_ATTEMPT_ID = UUID("33333333-3333-3333-3333-333333333333")
CONTENT_ID = UUID("44444444-4444-4444-4444-444444444444")
RECEIPT_ID = UUID("55555555-5555-5555-5555-555555555555")
REPLICA_ID = UUID("88888888-8888-8888-8888-888888888888")
# Metadata-only fixture; live document reader tests use complete PDF originals.
SOURCE_BYTES = b"%PDF-1.7\nGuide fixture\n%%EOF"
SOURCE_SHA256 = "sha256:" + hashlib.sha256(SOURCE_BYTES).hexdigest()


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


def runtime_configuration():
    """Return explicit, non-secret execution settings for isolated test attempts."""
    from app.interfaces.project_guide_runtime import ProjectGuideRuntimeConfiguration

    instructions = "Inspect assigned originals and propose bounded draft policies."
    return ProjectGuideRuntimeConfiguration(
        runtime_key="openai_agents_sdk",
        model_provider="openai",
        model="test-model",
        model_api="responses",
        instruction_version="v1",
        instructions=instructions,
        instructions_sha256="sha256:" + hashlib.sha256(instructions.encode()).hexdigest(),
        timeout_seconds=30,
    )


def context(values: dict[str, UUID], *, generation: int = 1, guide_version="v1") -> ProjectGuideCompilationContext:
    """Build one exact committed-original metadata context."""
    material = GuideDocumentManifest(
        project_id=values["project"], guide_id=values["guide"], guide_version=guide_version,
        source_snapshot_id=values["snapshot"], source_snapshot_hash=SHA256,
        setup_run_id=values[f"setup_{generation}"], setup_generation=generation,
        documents=(GuideDocumentVersion(
            source_item_id=SOURCE_ITEM_ID, ingest_id=DOCUMENT_VERSION_ID, item_order=0,
            put_attempt_id=PUT_ATTEMPT_ID, content_id=CONTENT_ID, replica_id=REPLICA_ID,
            storage_namespace_id="primary", namespace_fingerprint=SOURCE_SHA256,
            sha256=SOURCE_SHA256, byte_count=len(SOURCE_BYTES), media_type="application/pdf",
        ),),
    )
    return ProjectGuideCompilationContext(
        task_examples=({"content": "Review a claim using the project guide."},),
        runtime_configuration=runtime_configuration(),
        material=material,
        setup_run_id=values[f"setup_{generation}"],
        setup_generation=generation,
        instruction_version="v1",
        agent_identity="project-guide-compilation-agent-v1",
        agent_version="v1",
        pre_submission_capabilities=project_guide_pre_submission_capabilities(
            build_pre_submission_checker_catalogue()
        ),
        post_submission_capabilities=current_post_submit_catalogue(),
    )


def result() -> ProjectGuideCompilationResult:
    """Return the smallest semantically valid unified result."""
    return ProjectGuideCompilationResult(
        status="draft_ready",
        findings=(
            CompilationFinding(severity="info", code="guide.ready", message="Guide is complete.",
                evidence_refs=(GuideEvidenceRef(source_item_id=SOURCE_ITEM_ID,
                    document_version_id=DOCUMENT_VERSION_ID, sha256=SOURCE_SHA256),)),
        ),
        submission_artifact_policy=SubmissionArtifactPolicyProposal(
            maximum_file_size_bytes=1_000,
            maximum_package_size_bytes=10_000,
            required_artifacts=("submission",),
        ),
        requirements=(),
        pre_submit_bindings=(),
        post_submit_bindings=(),
        capability_suggestions=(),
        setup_notes=(),
        agent_name="ProjectGuideCompilationAgent",
        agent_version="v1",
        schema_version="project_guide_compilation_result.v1",
    )


def identity(
    compilation_context: ProjectGuideCompilationContext,
) -> CompilationAttemptIdentity:
    """Derive the trusted attempt identity."""
    return CompilationAttemptIdentity.from_context(compilation_context)


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


async def _seed_project_rows(
    engine: AsyncEngine, values: dict[str, UUID], generations: int, guide_version: str
) -> None:
    sql_values = {name: str(value) for name, value in values.items()}
    examples = TASK_EXAMPLES
    example_hash = task_examples_hash(examples)
    sql_values.update(
        guide_version=guide_version,
        examples=json.dumps([item.model_dump(mode="json") for item in examples]),
        examples_hash=example_hash,
        example_manifest=json.dumps(TASK_EXAMPLE_MANIFEST),
    )
    async with engine.begin() as connection:
        await connection.execute(text("alter table projects disable trigger user"))
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
        await connection.execute(
            text(
                "insert into projects(id,name,slug,status) values"
                "(:project,'Compilation project',:slug,'draft')"
            ),
            {**sql_values, "slug": f"compilation-{values['project']}"},
        )
        await connection.execute(text("alter table projects enable trigger user"))
        for table in ("project_guides", "guide_source_snapshots", "project_setup_runs"):
            await connection.execute(text(f"alter table {table} disable trigger user"))
        await connection.execute(
            text(
                "insert into project_guides(id,project_id,version,status,"
                "created_by,task_examples,task_examples_hash) values(:guide,:project,:guide_version,'draft','test',cast(:examples as json),:examples_hash)"
            ),
            sql_values,
        )
        await connection.execute(
            text(
                "insert into guide_source_snapshots(id,project_id,guide_id,guide_version,"
                "manifest_schema_version,manifest_json,bundle_hash,captured_by) values"
                "(:snapshot,:project,:guide,:guide_version,'guide_source_snapshot.task_examples',cast(:example_manifest as json),"
                ":hash,'test')"
            ),
            {**sql_values, "hash": SHA256},
        )
        for generation in range(1, generations + 1):
            await connection.execute(
                text(
                    "insert into project_setup_runs(id,project_id,guide_id,guide_version,"
                    "source_snapshot_id,source_snapshot_hash,setup_generation,status,"
                    "current_step,celery_task_id,documents_ready_at,created_by) values("
                    ":setup,:project,:guide,:guide_version,:snapshot,:hash,:generation,"
                    "'queued','queued',:task_id,now(),'test')"
                ),
                {
                    **sql_values,
                    "setup": str(values[f"setup_{generation}"]),
                    "hash": SHA256,
                    "generation": generation,
                    "task_id": project_guide_compilation_task_id(
                        str(values[f"setup_{generation}"]), generation
                    ),
                },
            )
        for table in reversed(("project_guides", "guide_source_snapshots", "project_setup_runs")):
            await connection.execute(text(f"alter table {table} enable trigger user"))


async def _seed_snapshot_item(engine: AsyncEngine, values: dict[str, UUID]) -> None:
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("alter table guide_source_snapshot_items disable trigger user")
            )
            await connection.execute(
                text(
                    "insert into guide_source_snapshot_items("
                    "id,source_snapshot_id,item_order,source_kind,source_label,"
                    "ingestion_adapter,media_type) values("
                    ":id,:snapshot,0,'document','guide.pdf',"
                    "'upload','application/pdf')"
                ),
                {"id": str(SOURCE_ITEM_ID), "snapshot": str(values["snapshot"])},
            )
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("alter table guide_source_snapshot_items enable trigger user")
            )


async def _seed_artifact_custody(session: AsyncSession, values: dict[str, UUID], namespace=None) -> None:
    from datetime import datetime, timezone
    namespace_row = ArtifactStorageNamespace(
        id="primary", backend=namespace.backend if namespace else "local",
        adapter=namespace.adapter if namespace else "local",
        provider_profile=namespace.provider_profile if namespace else "test",
        namespace_descriptor=namespace.namespace_descriptor if namespace else {"root": "guide-compilation-fixture"},
        namespace_fingerprint=namespace.namespace_fingerprint if namespace else SOURCE_SHA256,
    )
    session.add_all([
        namespace_row,
        ArtifactContent(id=str(CONTENT_ID), sha256=SOURCE_SHA256,
            byte_count=len(SOURCE_BYTES), media_type="application/pdf",
            normalized_display_name="guide.pdf"),
        GuideSourceArtifactIngest(id=str(DOCUMENT_VERSION_ID), source_item_id=str(SOURCE_ITEM_ID),
            actor_profile_id=str(values["actor"]), sha256=SOURCE_SHA256,
            byte_count=len(SOURCE_BYTES), media_type="application/pdf"),
    ])
    await session.flush()
    replica = ArtifactReplica(id=str(REPLICA_ID), content_id=str(CONTENT_ID),
        storage_namespace_id="primary", namespace_fingerprint=namespace_row.namespace_fingerprint,
        adapter=namespace_row.adapter, provider_profile=namespace_row.provider_profile, provider_object_ref=f"fixtures/{CONTENT_ID}",
        verification_state="pending", availability_state="unknown", integrity_state="unknown")
    session.add(replica)
    await session.flush()
    put = ArtifactPutAttempt(id=str(PUT_ATTEMPT_ID), producer_request_type="guide",
        producer_type="actor_profile", producer_ref=str(values["actor"]),
        project_id=str(values["project"]), guide_source_item_id=str(SOURCE_ITEM_ID),
        sha256=SOURCE_SHA256, byte_count=len(SOURCE_BYTES), media_type="application/pdf",
        storage_namespace_id="primary", namespace_fingerprint=namespace_row.namespace_fingerprint,
        canonical_target=f"sha256/{SOURCE_SHA256[7:9]}/{SOURCE_SHA256[9:]}",
        operation_identity=SOURCE_SHA256, request_digest=SOURCE_SHA256,
        status="object_confirmed", terminal_result_code="document_stored",
        replica_id=str(REPLICA_ID), terminal_at=datetime.now(timezone.utc))
    session.add(put)
    await session.flush()
    session.add(ArtifactOperationReceipt(id=str(RECEIPT_ID), contract_version=2,
        put_attempt_id=put.id, guide_source_item_id=str(SOURCE_ITEM_ID),
        replica_id=replica.id, operation="put", idempotency_key=put.operation_identity,
        request_digest=put.request_digest, provider_object_ref=replica.provider_object_ref,
        replayed=False, outcome="document_stored", attempt_number=1,
        correlation_id=str(uuid4()), details=[]))
    await session.flush()
    put.receipt_id = str(RECEIPT_ID)


async def seed_database(database_url: str, *, generations: int = 1, guide_version="v1", namespace=None) -> dict[str, UUID]:
    """Seed only canonical parent rows needed by hidden persistence tests."""
    values = ids()
    engine = create_async_engine(database_url)
    try:
        await _seed_project_rows(engine, values, generations, guide_version)
        await _seed_snapshot_item(engine, values)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session, session.begin():
            await _seed_artifact_custody(session, values, namespace)
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
