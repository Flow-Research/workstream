"""Committed-original fixtures and authorized compiled report prerequisites.

Storage/provider calls are scripted. Request, execution, access custody and report
projection use their real owners, so policy tests cannot bypass those gates.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import UUID, uuid4
import hashlib

from sqlalchemy import select

from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.actors.models import ActorProfile, ActorIdentityLink
from app.modules.artifacts.models import (
    ArtifactContent,
    ArtifactReplica,
    ArtifactStorageNamespace,
    ArtifactPutAttempt,
    ArtifactOperationReceipt,
)
from app.modules.projects.models import (
    GuideSourceSnapshot,
    GuideSourceSnapshotItem,
    GuideSourceArtifactIngest,
    ProjectSetupRun,
    GuideSufficiencyReport,
)
from app.adapters.artifacts import guide_document_manifest_port
from app.modules.projects.api.guide_documents import (
    DOCUMENT_EXTENSIONS,
    GuideDocumentManifestRequest,
)
from tests.projects.guide_compilation.helpers import (
    SOURCE_BYTES,
    runtime_configuration,
    generated_result,
)
from tests.projects.guide_compilation.runtime_fixtures import (
    document_tools,
    record_scripted_document_access,
)


def sha256_hash(seed: str) -> str:
    return "sha256:" + hashlib.sha256(seed.encode()).hexdigest()


async def create_committed_document_fixture(
    source_snapshot_id: str, *, sessions=None, contents=None
):
    """Persist exact committed upload receipts; never mark a replica verified.

    ``contents`` optionally maps a source label to its exact original bytes; any
    other item stores the shared PDF fixture under its declared media type.
    """
    sessions = sessions or db_session.get_session_factory()
    contents = contents or {}
    async with sessions() as session:
        snapshot = await session.get(GuideSourceSnapshot, source_snapshot_id)
        setup = await session.scalar(
            select(ProjectSetupRun)
            .where(ProjectSetupRun.source_snapshot_id == source_snapshot_id)
            .order_by(ProjectSetupRun.setup_generation.desc())
            .limit(1)
        )
        assert snapshot is not None and setup is not None
        actor = await session.scalar(
            select(ActorProfile)
            .where(ActorProfile.actor_kind == "human")
            .order_by(ActorProfile.id)
            .limit(1)
        )
        assert actor is not None
        items = list(
            await session.scalars(
                select(GuideSourceSnapshotItem)
                .where(GuideSourceSnapshotItem.source_snapshot_id == source_snapshot_id)
                .order_by(GuideSourceSnapshotItem.item_order)
            )
        )
        assert items
        namespace = await session.get(ArtifactStorageNamespace, "primary")
        if namespace is None:
            namespace = ArtifactStorageNamespace(
                id="primary",
                backend="local",
                adapter="local",
                provider_profile="test",
                namespace_descriptor={"root": "committed-guide-fixture"},
                namespace_fingerprint=sha256_hash("committed-guide-fixture"),
            )
            session.add(namespace)
            await session.flush()
        for item in items:
            assert (item.source_kind, item.ingestion_adapter) == ("document", "upload")
            existing = await session.scalar(
                select(GuideSourceArtifactIngest).where(
                    GuideSourceArtifactIngest.source_item_id == item.id
                )
            )
            if existing is not None:
                assert existing.media_type == item.media_type
                continue
            body = contents.get(item.source_label, SOURCE_BYTES)
            assert item.source_label in contents or item.media_type == "application/pdf"
            await _store_committed_original(session, snapshot, actor, item, namespace, body)
        if setup.documents_ready_at is None:
            setup.documents_ready_at = datetime.now(timezone.utc)
        await session.commit()
        return await guide_document_manifest_port(session).load(
            GuideDocumentManifestRequest(
                project_id=UUID(snapshot.project_id),
                guide_id=UUID(snapshot.guide_id),
                guide_source_snapshot_id=UUID(snapshot.id),
                project_setup_run_id=UUID(setup.id),
                setup_generation=setup.setup_generation,
            )
        )


async def _store_committed_original(session, snapshot, actor, item, namespace, body):
    """Keep each scripted original bound to its put and terminal receipt."""
    digest = "sha256:" + hashlib.sha256(body).hexdigest()
    content = await session.scalar(
        select(ArtifactContent).where(ArtifactContent.sha256 == digest)
    )
    if content is None:
        content = ArtifactContent(
            id=str(new_record_id()),
            sha256=digest,
            byte_count=len(body),
            media_type=item.media_type,
            normalized_display_name="guide." + DOCUMENT_EXTENSIONS[item.media_type],
        )
        session.add(content)
        await session.flush()
    replica = await session.scalar(
        select(ArtifactReplica).where(
            ArtifactReplica.content_id == content.id,
            ArtifactReplica.storage_namespace_id == namespace.id,
        )
    )
    if replica is None:
        replica = ArtifactReplica(
            id=str(new_record_id()),
            content_id=content.id,
            storage_namespace_id=namespace.id,
            namespace_fingerprint=namespace.namespace_fingerprint,
            adapter=namespace.adapter,
            provider_profile=namespace.provider_profile,
            provider_object_ref=f"fixtures/{content.id}",
            verification_state="pending",
            availability_state="unknown",
            integrity_state="unknown",
        )
        session.add(replica)
        await session.flush()
    session.add(
        GuideSourceArtifactIngest(
            id=str(new_record_id()),
            source_item_id=item.id,
            actor_profile_id=actor.id,
            sha256=digest,
            byte_count=len(body),
            media_type=item.media_type,
        )
    )
    put = ArtifactPutAttempt(
        id=str(new_record_id()),
        producer_request_type="guide",
        producer_type="actor_profile",
        producer_ref=actor.id,
        project_id=snapshot.project_id,
        guide_source_item_id=item.id,
        sha256=digest,
        byte_count=len(body),
        media_type=item.media_type,
        storage_namespace_id=namespace.id,
        namespace_fingerprint=namespace.namespace_fingerprint,
        canonical_target=f"sha256/{digest[7:9]}/{digest[9:]}",
        operation_identity=sha256_hash(item.id),
        request_digest=sha256_hash("request:" + item.id),
        status="object_confirmed",
        terminal_result_code="document_stored",
        replica_id=replica.id,
        terminal_at=datetime.now(timezone.utc),
    )
    session.add(put)
    await session.flush()
    receipt = ArtifactOperationReceipt(
        id=str(new_record_id()),
        contract_version=2,
        put_attempt_id=put.id,
        guide_source_item_id=item.id,
        replica_id=replica.id,
        operation="put",
        idempotency_key=put.operation_identity,
        request_digest=put.request_digest,
        provider_object_ref=replica.provider_object_ref,
        replayed=False,
        outcome="document_stored",
        attempt_number=1,
        correlation_id=str(uuid4()),
        details=[],
    )
    session.add(receipt)
    await session.flush()
    put.receipt_id = receipt.id


async def seed_setup_service_for_compiled_fixture(sessions):
    """Arrange the shared service prerequisite without reactivating retained actors."""
    async with sessions() as session, session.begin():
        actor = await session.scalar(
            select(ActorProfile).where(ActorProfile.service_identity == "workstream.project.setup")
        )
        if actor is not None:
            assert actor.actor_kind == "service" and actor.status == "active"
            return
        actor_id = str(new_record_id())
        session.add(
            ActorProfile(
                id=actor_id,
                actor_kind="service",
                status="active",
                provisioning_method="manual_service_provisioning",
                service_identity="workstream.project.setup",
                created_by="compiled-guide-fixture",
            )
        )
        session.add(
            ActorIdentityLink(
                id=str(new_record_id()),
                actor_profile_id=actor_id,
                issuer="workstream-internal",
                subject="workstream.project.setup",
                subject_kind="service",
                status="active",
                linked_by="compiled-guide-fixture",
            )
        )


def _compiled_report_runtime(configuration, status, findings, artifact_proposal, execution_errors):
    """Script only evaluation output; document access keeps its real custody."""
    from app.interfaces.project_agents import CompilationFinding, GuideEvidenceRef

    class Runtime:
        identity = configuration.adapter_identity

        def admit_execution(self):
            pass

        async def aclose(self):
            pass

        async def compile_project_guide(self, context, capabilities):
            try:
                await record_scripted_document_access(context, capabilities)
            except Exception as exc:
                execution_errors.append(("runtime_compile", exc))
                raise
            refs = tuple(
                GuideEvidenceRef(
                    source_item_id=item.source_item_id,
                    document_version_id=item.ingest_id,
                    sha256=item.sha256,
                )
                for item in context.material.documents
            )
            compiled_findings = tuple(
                CompilationFinding(
                    severity=item["severity"],
                    code=item["code"],
                    message=item["message"],
                    evidence_refs=refs,
                )
                for item in findings
            )
            if not compiled_findings:
                compiled_findings = (
                    CompilationFinding(
                        severity="info",
                        code="guide.ready",
                        message="Guide complete.",
                        evidence_refs=refs,
                    ),
                )
            patch = {
                "status": {
                    "blocked": "guide_blocked",
                    "passed": "draft_ready",
                    "passed_with_warnings": "draft_ready_with_warnings",
                }[status],
                "findings": compiled_findings,
                "requirements": tuple(
                    item.model_copy(update={"evidence_refs": refs})
                    for item in generated_result().requirements
                ) if status != "blocked" else (),
            }
            if artifact_proposal is not None:
                patch["submission_artifact_policy"] = artifact_proposal
            if status == "blocked":
                patch["submission_artifact_policy"] = None
            return generated_result().model_copy(update=patch)

    return Runtime()


async def _request_compiled_fixture(sessions, manifest, configuration):
    """Reserve and acknowledge an explicit PM request against committed originals."""
    from app.db.session import get_database_url
    from app.modules.authorization.models import AdminRoleGrant
    from tests.projects.guide_compilation.test_authorized_request_service import _seed_human
    from tests.projects.guide_compilation.pending_source import request_pending_source

    async with sessions() as session:
        grant = await session.scalar(select(AdminRoleGrant.id).where(
            AdminRoleGrant.scope_project_id == str(manifest.project_id),
            AdminRoleGrant.role == "project_manager", AdminRoleGrant.status == "active",
        ))
    if grant is None:
        await _seed_human(get_database_url(), {"project": manifest.project_id})
    request = await request_pending_source(sessions, manifest.setup_run_id, configuration)
    from tests.projects.guide_compilation.helpers import acknowledge_requested_setup

    await acknowledge_requested_setup(sessions, request)

    return request


async def create_compiled_report_fixture(
    report_id: str,
    source_snapshot_id: str,
    *,
    artifact_proposal=None,
    post_submit_registry_spec=None,
    document_access_factory=None,
) -> str:
    """Request as the PM, then project a scripted result under service custody."""
    from app.adapters.auth import (
        guide_compilation_execution_authority,
        guide_sufficiency_projection_authorization,
        artifact_policy_projection_authorization,
    )
    from app.modules.projects.api import (
        ProjectGuideCompilationExecutionCommand,
        ProjectGuideProjectionCommand,
        ProjectGuideCompilationExecutionClassification,
    )
    from app.modules.projects.guide_compilation.orchestrator import (
        project_guide_compilation_execution_port,
    )
    from app.modules.projects.guide_compilation.projections import GuideCompilationProjectionService
    sessions = db_session.get_session_factory()
    from tests.projects.guide_activation.source_fixtures import _register_external_checker_fixture

    if post_submit_registry_spec is not None:
        await _register_external_checker_fixture(sessions, post_submit_registry_spec)
    await seed_setup_service_for_compiled_fixture(sessions)
    async with sessions() as session:
        report = await session.scalar(
            select(GuideSufficiencyReport).where(
                GuideSufficiencyReport.source_snapshot_id == source_snapshot_id,
                GuideSufficiencyReport.project_setup_run_id.is_not(None),
            )
        )
        if report is not None:
            return report.id
        diagnostic = await session.get(GuideSufficiencyReport, report_id)
        assert diagnostic is not None
        status, findings = diagnostic.status, diagnostic.findings
    manifest = await create_committed_document_fixture(source_snapshot_id)
    configuration = runtime_configuration()
    execution_errors = []
    selected_document_access_factory = document_access_factory
    if document_access_factory is not None:

        @asynccontextmanager
        async def observed_document_access(*args):
            try:
                async with document_access_factory(*args) as grant:
                    yield grant
            except Exception as exc:
                execution_errors.append(("document_access", exc))
                raise

        selected_document_access_factory = observed_document_access
    request = await _request_compiled_fixture(sessions, manifest, configuration)

    execution = project_guide_compilation_execution_port(
        sessions,
        material_factory=guide_document_manifest_port,
        document_tools_factory=document_tools(
            sessions, document_access_factory=selected_document_access_factory
        ),
        authorization_context=guide_compilation_execution_authority,
        runtime_factory=lambda config: _compiled_report_runtime(
            config, status, findings, artifact_proposal, execution_errors
        ),
    )
    receipt = await execution.execute(
        ProjectGuideCompilationExecutionCommand(attempt_id=request.attempt_id)
    )
    safe_errors = []
    for phase, exc in execution_errors:
        parts = [phase, type(exc).__name__]
        code = getattr(exc, "code", None)
        if (
            isinstance(code, str)
            and len(code) <= 80
            and code.replace("_", "").isalnum()
        ):
            parts.append(code)
        safe_errors.append(":".join(parts))
    assert (
        receipt.classification is ProjectGuideCompilationExecutionClassification.PERSISTED
    ), (receipt.classification.value, tuple(safe_errors))
    projections = GuideCompilationProjectionService(
        sessions,
        material_factory=guide_document_manifest_port,
        sufficiency_authorization_factory=guide_sufficiency_projection_authorization,
        policy_authorization_factory=artifact_policy_projection_authorization,
    )
    projected = await projections.project_guide_sufficiency(
        ProjectGuideProjectionCommand(attempt_id=request.attempt_id)
    )
    return str(projected.output_id)
