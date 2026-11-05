"""Small canonical fixtures shared by guide-compilation behavior tests."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from uuid import UUID, uuid4

from sqlalchemy import insert, text, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db import models as _all_models  # noqa: F401
from app.modules.artifacts.models import (
    ArtifactContent,
    ArtifactReplica,
    ArtifactStorageNamespace,
    ArtifactPutAttempt,
    ArtifactOperationReceipt,
)
from app.modules.projects.models import GuideSourceArtifactIngest
from app.modules.projects.api.guide_documents import GuideDocumentManifest, GuideDocumentVersion
from app.interfaces.project_agents import (
    AtomicGuideRequirement,
    CheckFailureFinding,
    CheckInabilityToEvaluate,
    CheckInput,
    CheckNegativeTest,
    CheckSpecification,
    CompilationFinding,
    GuideEvidenceRef,
    ProjectGuideCompilationContext,
    ProjectGuideCompilationResult,
    SubmissionArtifactPolicyProposal,
)
from app.modules.authorization.api import (
    ActorIdentityFacts,
    ActorKind,
    ProjectGuideCompilationExecutePersistFacts,
    project_guide_compilation_execute_resource_digest,
)
from app.modules.projects.guide_compilation.contracts import (
    CompilationAttemptIdentity,
    accepted_compilation_result,
)

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.projects.api.task_examples import task_examples_hash, validate_task_examples

TASK_EXAMPLES = validate_task_examples([{"content": "Review a claim using the project guide."}])
TASK_EXAMPLE_MANIFEST = {
    "task_examples_hash": task_examples_hash(TASK_EXAMPLES),
    "task_examples_count": len(TASK_EXAMPLES),
}
SHA256 = canonical_json_hash(TASK_EXAMPLE_MANIFEST)
SOURCE_ITEM_ID = new_record_id()
DOCUMENT_VERSION_ID = new_record_id()
PUT_ATTEMPT_ID = new_record_id()
CONTENT_ID = new_record_id()
RECEIPT_ID = new_record_id()
REPLICA_ID = new_record_id()
# Metadata-only fixture; live document reader tests use complete PDF originals.
SOURCE_BYTES = b"%PDF-1.7\nGuide fixture\n%%EOF"
SOURCE_SHA256 = "sha256:" + hashlib.sha256(SOURCE_BYTES).hexdigest()


def ids() -> dict[str, UUID]:
    """Return complete unrelated identifiers for one test scenario."""
    record_names = (
        "actor",
        "link",
        "wrong_link",
        "project",
        "guide",
        "snapshot",
        "setup_1",
        "setup_2",
        "setup_3",
        "audit",
    )
    values = {name: new_record_id() for name in record_names}
    values.update(operation=uuid4(), request=uuid4(), key=uuid4())
    return values


def runtime_configuration():
    """Return explicit, non-secret execution settings for isolated test attempts."""
    from app.interfaces.project_guide_runtime import (
        ProjectGuideRuntimeConfiguration,
        canonical_adapter_profile,
    )
    from app.adapters.project_agents import build_project_guide_adapter_profile

    instructions = "Inspect assigned originals and propose bounded draft policies."
    return ProjectGuideRuntimeConfiguration(
        runtime_key="openai_agents_sdk",
        model_provider="openai",
        model="test-model",
        model_api="responses",
        adapter_profile=canonical_adapter_profile(
            build_project_guide_adapter_profile("openai_agents_sdk", {})
        ),
        instruction_version="v1",
        instructions=instructions,
        instructions_sha256="sha256:" + hashlib.sha256(instructions.encode()).hexdigest(),
        timeout_seconds=30,
    )


def manager_runtime_configuration():
    """Return the no-inference configuration recorded by manager-authored attempts."""
    configuration = runtime_configuration()
    return type(configuration).model_validate(
        configuration.model_dump(mode="json")
        | {
            "runtime_key": "manager_authored",
            "model_provider": "none",
            "model_api": "none",
            "model": "none",
            "adapter_profile": "{}",
        }
    )


def context(
    values: dict[str, UUID],
    *,
    generation: int = 1,
    guide_version="v1",
    configuration=None,
    task_examples=TASK_EXAMPLES,
) -> ProjectGuideCompilationContext:
    """Build one exact committed-original metadata context."""
    task_examples = validate_task_examples(task_examples)
    snapshot_hash = canonical_json_hash({
        "task_examples_hash": task_examples_hash(task_examples),
        "task_examples_count": len(task_examples),
    })
    material = GuideDocumentManifest(
        project_id=values["project"],
        guide_id=values["guide"],
        guide_version=guide_version,
        source_snapshot_id=values["snapshot"],
        source_snapshot_hash=snapshot_hash,
        setup_run_id=values[f"setup_{generation}"],
        setup_generation=generation,
        documents=(
            GuideDocumentVersion(
                source_item_id=SOURCE_ITEM_ID,
                ingest_id=DOCUMENT_VERSION_ID,
                item_order=0,
                put_attempt_id=PUT_ATTEMPT_ID,
                content_id=CONTENT_ID,
                replica_id=REPLICA_ID,
                storage_namespace_id="primary",
                namespace_fingerprint=SOURCE_SHA256,
                sha256=SOURCE_SHA256,
                byte_count=len(SOURCE_BYTES),
                media_type="application/pdf",
            ),
        ),
    )
    return ProjectGuideCompilationContext(
        task_examples=task_examples,
        runtime_configuration=configuration or runtime_configuration(),
        material=material,
        setup_run_id=values[f"setup_{generation}"],
        setup_generation=generation,
        instruction_version="v1",
        agent_identity="project-guide-compilation-agent-v1",
        agent_version="v1",
    )


def result() -> ProjectGuideCompilationResult:
    """Return the smallest semantically valid unified result."""
    return ProjectGuideCompilationResult(
        status="draft_ready",
        findings=(
            CompilationFinding(
                severity="info",
                code="guide.ready",
                message="Guide is complete.",
                evidence_refs=(
                    GuideEvidenceRef(
                        source_item_id=SOURCE_ITEM_ID,
                        document_version_id=DOCUMENT_VERSION_ID,
                        sha256=SOURCE_SHA256,
                    ),
                ),
            ),
        ),
        submission_artifact_policy=SubmissionArtifactPolicyProposal(
            maximum_file_size_bytes=1_000,
            maximum_package_size_bytes=10_000,
            required_artifacts=("submission",),
        ),
        requirements=(),
        setup_notes=(),
        agent_name="ProjectGuideCompilationAgent",
        agent_version="v1",
        schema_version="project_guide_check_specification.v1",
    )


def valid_specification() -> CheckSpecification:
    """Return one actionable source-derived PRE check specification."""
    return CheckSpecification(
        evaluation_method="Inspect the submitted package manifest.",
        inputs=(
            CheckInput(
                input_id="submitted_package",
                kind="package",
                purpose="Submitted work to inspect.",
            ),
        ),
        check_steps=("Inspect the package manifest for the required item.",),
        pass_conditions=("The required item is present.",),
        failure_findings=(
            CheckFailureFinding(
                code="required_item_missing",
                level="error",
                condition="The required item is absent.",
                message="The submitted work is missing a required item.",
            ),
        ),
        positive_tests=("A package containing the required item passes.",),
        negative_tests=(
            CheckNegativeTest(
                name="missing_required_item",
                scenario="A package omits the required item.",
                expected_verdict="failed",
                expected_finding_codes=("required_item_missing",),
            ),
        ),
        implementation_needs=("Read the submitted package manifest and identify its entries.",),
        inability_to_evaluate=(
            CheckInabilityToEvaluate(
                code="invalid_output",
                condition="The submitted package manifest cannot be read.",
            ),
        ),
    )


def generated_result() -> ProjectGuideCompilationResult:
    """Return a valid new-generation result without changing retained fixtures."""
    requirement = AtomicGuideRequirement(
        suggestion_id="required_item",
        statement="The submitted work must include the required item.",
        stage="pre_submit",
        classification_rationale="The guide asks for this item before submission.",
        check_specification=valid_specification(),
        evidence_refs=(
            GuideEvidenceRef(
                source_item_id=SOURCE_ITEM_ID,
                document_version_id=DOCUMENT_VERSION_ID,
                sha256=SOURCE_SHA256,
            ),
        ),
    )
    body = result().model_dump(mode="json", exclude={"setup_notes"})
    body["requirements"] = [requirement.model_dump(mode="json")]
    return ProjectGuideCompilationResult.model_validate(body)


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
        result_schema_version=attempt_identity.result_schema_version,
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
        resource_context_digest=SHA256,
    )
    return replace(
        facts,
        resource_context_digest=project_guide_compilation_execute_resource_digest(
            service_actor(values), facts
        ),
    )


async def _seed_project_rows(
    engine: AsyncEngine, values: dict[str, UUID], generations: int, guide_version: str,
    task_examples=TASK_EXAMPLES,
) -> None:
    sql_values = {name: str(value) for name, value in values.items()}
    examples = validate_task_examples(task_examples)
    example_hash = task_examples_hash(examples)
    example_manifest = {
        "task_examples_hash": example_hash,
        "task_examples_count": len(examples),
    }
    snapshot_hash = canonical_json_hash(example_manifest)
    sql_values.update(
        guide_version=guide_version,
        examples=json.dumps([item.model_dump(mode="json") for item in examples]),
        examples_hash=example_hash,
        example_manifest=json.dumps(example_manifest),
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
            {**sql_values, "hash": snapshot_hash},
        )
        for generation in range(1, generations + 1):
            await connection.execute(
                text(
                    "insert into project_setup_runs(id,project_id,guide_id,guide_version,"
                    "source_snapshot_id,source_snapshot_hash,setup_generation,status,"
                    "current_step,celery_task_id,documents_ready_at,created_by) values("
                    ":setup,:project,:guide,:guide_version,:snapshot,:hash,:generation,"
                    "'awaiting_documents','awaiting_documents',NULL,NULL,'test')"
                ),
                {
                    **sql_values,
                    "setup": str(values[f"setup_{generation}"]),
                    "hash": snapshot_hash,
                    "generation": generation,
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


async def _seed_artifact_custody(
    session: AsyncSession,
    values: dict[str, UUID],
    namespace=None,
    provider_object_ref: str | None = None,
) -> None:
    namespace_values = {
        "id": "primary",
        "backend": namespace.backend if namespace else "local",
        "adapter": namespace.adapter if namespace else "local",
        "provider_profile": namespace.provider_profile if namespace else "test",
        "namespace_descriptor": namespace.namespace_descriptor
        if namespace
        else {"root": "guide-compilation-fixture"},
        "namespace_fingerprint": namespace.namespace_fingerprint
        if namespace
        else SOURCE_SHA256,
    }
    provider_ref = provider_object_ref or f"fixtures/{CONTENT_ID}"
    # Explicit Core statements let historical-migration tests arrange the ART
    # columns that existed at that revision without making current ORM metadata
    # project newer nullable columns into the older schema.
    await session.execute(insert(ArtifactStorageNamespace).values(**namespace_values))
    await session.execute(
        insert(ArtifactContent).values(
            id=str(CONTENT_ID),
            sha256=SOURCE_SHA256,
            byte_count=len(SOURCE_BYTES),
            media_type="application/pdf",
            normalized_display_name="guide.pdf",
        )
    )
    await session.execute(
        insert(GuideSourceArtifactIngest).values(
            id=str(DOCUMENT_VERSION_ID),
            source_item_id=str(SOURCE_ITEM_ID),
            actor_profile_id=str(values["actor"]),
            sha256=SOURCE_SHA256,
            byte_count=len(SOURCE_BYTES),
            media_type="application/pdf",
        )
    )
    await session.execute(
        insert(ArtifactReplica).values(
            id=str(REPLICA_ID),
            content_id=str(CONTENT_ID),
            storage_namespace_id="primary",
            namespace_fingerprint=namespace_values["namespace_fingerprint"],
            adapter=namespace_values["adapter"],
            provider_profile=namespace_values["provider_profile"],
            provider_object_ref=provider_ref,
            verification_state="pending",
            availability_state="unknown",
            integrity_state="unknown",
        )
    )
    await _seed_verified_guide_put(session, values, namespace_values, provider_ref)


async def _seed_verified_guide_put(session, values, namespace_values, provider_ref) -> None:
    """Arrange the retained put, its terminal receipt and their exact linkage."""
    from datetime import datetime, timezone

    await session.execute(
        insert(ArtifactPutAttempt).values(
            id=str(PUT_ATTEMPT_ID),
            producer_request_type="guide",
            producer_type="actor_profile",
            producer_ref=str(values["actor"]),
            project_id=str(values["project"]),
            guide_source_item_id=str(SOURCE_ITEM_ID),
            sha256=SOURCE_SHA256,
            byte_count=len(SOURCE_BYTES),
            media_type="application/pdf",
            storage_namespace_id="primary",
            namespace_fingerprint=namespace_values["namespace_fingerprint"],
            canonical_target=f"sha256/{SOURCE_SHA256[7:9]}/{SOURCE_SHA256[9:]}",
            operation_identity=SOURCE_SHA256,
            request_digest=SOURCE_SHA256,
            status="object_confirmed",
            terminal_result_code="document_stored",
            replica_id=str(REPLICA_ID),
            terminal_at=datetime.now(timezone.utc),
        )
    )
    await session.execute(
        insert(ArtifactOperationReceipt).values(
            id=str(RECEIPT_ID),
            contract_version=2,
            put_attempt_id=str(PUT_ATTEMPT_ID),
            guide_source_item_id=str(SOURCE_ITEM_ID),
            replica_id=str(REPLICA_ID),
            operation="put",
            idempotency_key=SOURCE_SHA256,
            request_digest=SOURCE_SHA256,
            provider_object_ref=provider_ref,
            replayed=False,
            outcome="document_stored",
            attempt_number=1,
            correlation_id=str(uuid4()),
            details=[],
        )
    )
    await session.execute(
        update(ArtifactPutAttempt)
        .where(ArtifactPutAttempt.id == str(PUT_ATTEMPT_ID))
        .values(receipt_id=str(RECEIPT_ID))
    )


async def seed_database(
    database_url: str,
    *,
    generations: int = 1,
    guide_version="v1",
    namespace=None,
    provider_object_ref: str | None = None,
    task_examples=TASK_EXAMPLES,
) -> dict[str, UUID]:
    """Seed only canonical parent rows needed by hidden persistence tests."""
    values = ids()
    engine = create_async_engine(database_url)
    try:
        await _seed_project_rows(engine, values, generations, guide_version, task_examples)
        await _seed_snapshot_item(engine, values)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session, session.begin():
            await _seed_artifact_custody(
                session,
                values,
                namespace,
                provider_object_ref,
            )
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
    event_id = new_record_id()
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


async def acknowledge_requested_setup(factory, receipt) -> None:
    """Arrange a broker acknowledgement only for the exact committed PM request."""
    from app.modules.projects.guide_compilation.models import ProjectGuideCompilationRequestOperation
    from app.modules.projects.models import ProjectSetupRun
    from sqlalchemy import select

    async with factory() as session, session.begin():
        operation = await session.scalar(select(ProjectGuideCompilationRequestOperation).where(
            ProjectGuideCompilationRequestOperation.operation_id == receipt.operation_id,
            ProjectGuideCompilationRequestOperation.attempt_id == receipt.attempt_id,
            ProjectGuideCompilationRequestOperation.request_trigger == "project_manager",
        ))
        assert operation is not None
        setup = await session.get(ProjectSetupRun, str(operation.setup_run_id), with_for_update=True)
        assert setup.status == "dispatch_pending" and setup.current_step == "dispatch"
        assert setup.documents_ready_at is not None
        setup.status, setup.current_step = "queued", "queued"
