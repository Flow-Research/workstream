"""Committed-original fixtures and authorized compiled report prerequisites.

Storage/provider calls are scripted. Request, execution, access custody and report
projection use their real owners, so policy tests cannot bypass those gates.
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4
import hashlib

from sqlalchemy import select

from app.db import session as db_session
from app.modules.actors.models import ActorProfile, ActorIdentityLink
from app.modules.artifacts.models import ArtifactContent, ArtifactReplica, ArtifactStorageNamespace, ArtifactPutAttempt, ArtifactOperationReceipt
from app.modules.projects.models import GuideSourceSnapshot, GuideSourceSnapshotItem, GuideSourceArtifactIngest, ProjectSetupRun, GuideSufficiencyReport
from app.adapters.artifacts import guide_document_manifest_port
from app.modules.projects.api.guide_documents import GuideDocumentManifestRequest
from tests.projects.guide_compilation.helpers import SOURCE_BYTES, SOURCE_SHA256, runtime_configuration, result
from tests.projects.guide_compilation.runtime_fixtures import document_access, record_scripted_document_access


def sha256_hash(seed: str) -> str:
    return "sha256:" + hashlib.sha256(seed.encode()).hexdigest()


async def create_committed_document_fixture(source_snapshot_id: str):
    """Persist exact committed upload receipts; never mark a replica verified."""
    async with db_session.get_session_factory()() as session:
        snapshot = await session.get(GuideSourceSnapshot, source_snapshot_id)
        setup = await session.scalar(select(ProjectSetupRun).where(ProjectSetupRun.source_snapshot_id == source_snapshot_id).order_by(ProjectSetupRun.setup_generation.desc()).limit(1))
        assert snapshot is not None and setup is not None
        actor = await session.scalar(select(ActorProfile).where(ActorProfile.actor_kind == "human").order_by(ActorProfile.id).limit(1))
        assert actor is not None
        items = list(await session.scalars(select(GuideSourceSnapshotItem).where(GuideSourceSnapshotItem.source_snapshot_id == source_snapshot_id).order_by(GuideSourceSnapshotItem.item_order)))
        assert items
        namespace = await session.get(ArtifactStorageNamespace, "primary")
        if namespace is None:
            namespace = ArtifactStorageNamespace(id="primary", backend="local", adapter="local", provider_profile="test", namespace_descriptor={"root": "committed-guide-fixture"}, namespace_fingerprint=sha256_hash("committed-guide-fixture"))
            session.add(namespace)
            await session.flush()
        content = await session.scalar(select(ArtifactContent).where(ArtifactContent.sha256 == SOURCE_SHA256))
        if content is None:
            content = ArtifactContent(id=str(uuid4()), sha256=SOURCE_SHA256, byte_count=len(SOURCE_BYTES), media_type="application/pdf", normalized_display_name="guide.pdf")
            session.add(content)
            await session.flush()
        replica = await session.scalar(select(ArtifactReplica).where(ArtifactReplica.content_id == content.id, ArtifactReplica.storage_namespace_id == namespace.id))
        if replica is None:
            replica = ArtifactReplica(id=str(uuid4()), content_id=content.id, storage_namespace_id=namespace.id, namespace_fingerprint=namespace.namespace_fingerprint, adapter=namespace.adapter, provider_profile=namespace.provider_profile, provider_object_ref=f"fixtures/{content.id}", verification_state="pending", availability_state="unknown", integrity_state="unknown")
            session.add(replica)
            await session.flush()
        for item in items:
            assert (item.source_kind, item.ingestion_adapter, item.media_type) == ("document", "upload", "application/pdf")
            existing = await session.scalar(select(GuideSourceArtifactIngest).where(GuideSourceArtifactIngest.source_item_id == item.id))
            if existing is not None:
                continue
            session.add(GuideSourceArtifactIngest(id=str(uuid4()), source_item_id=item.id, actor_profile_id=actor.id, sha256=SOURCE_SHA256, byte_count=len(SOURCE_BYTES), media_type="application/pdf"))
            put = ArtifactPutAttempt(id=str(uuid4()), producer_request_type="guide", producer_type="actor_profile", producer_ref=actor.id, project_id=snapshot.project_id, guide_source_item_id=item.id, sha256=SOURCE_SHA256, byte_count=len(SOURCE_BYTES), media_type="application/pdf", storage_namespace_id=namespace.id, namespace_fingerprint=namespace.namespace_fingerprint, canonical_target=f"sha256/{SOURCE_SHA256[7:9]}/{SOURCE_SHA256[9:]}", operation_identity=sha256_hash(item.id), request_digest=sha256_hash("request:" + item.id), status="object_confirmed", terminal_result_code="document_stored", replica_id=replica.id, terminal_at=datetime.now(timezone.utc))
            session.add(put)
            await session.flush()
            receipt = ArtifactOperationReceipt(id=str(uuid4()), contract_version=2, put_attempt_id=put.id, guide_source_item_id=item.id, replica_id=replica.id, operation="put", idempotency_key=put.operation_identity, request_digest=put.request_digest, provider_object_ref=replica.provider_object_ref, replayed=False, outcome="document_stored", attempt_number=1, correlation_id=str(uuid4()), details=[])
            session.add(receipt)
            await session.flush()
            put.receipt_id = receipt.id
        if setup.documents_ready_at is None:
            setup.documents_ready_at = datetime.now(timezone.utc)
        await session.commit()
        return await guide_document_manifest_port(session).load(GuideDocumentManifestRequest(project_id=UUID(snapshot.project_id), guide_id=UUID(snapshot.guide_id), guide_source_snapshot_id=UUID(snapshot.id), project_setup_run_id=UUID(setup.id), setup_generation=setup.setup_generation))


async def seed_setup_service_for_compiled_fixture(sessions):
    """Arrange the shared service prerequisite without reactivating retained actors."""
    async with sessions() as session, session.begin():
        actor = await session.scalar(select(ActorProfile).where(
            ActorProfile.service_identity == "workstream.project.setup"))
        if actor is not None:
            assert actor.actor_kind == "service" and actor.status == "active"
            return
        actor_id = str(uuid4())
        session.add(ActorProfile(id=actor_id, actor_kind="service", status="active",
            provisioning_method="manual_service_provisioning",
            service_identity="workstream.project.setup", created_by="compiled-guide-fixture"))
        session.add(ActorIdentityLink(id=str(uuid4()), actor_profile_id=actor_id,
            issuer="workstream-internal", subject="workstream.project.setup",
            subject_kind="service", status="active", linked_by="compiled-guide-fixture"))


async def create_compiled_report_fixture(report_id: str, source_snapshot_id: str) -> str:
    """Project a scripted unified result under real service authority and custody."""
    from app.adapters.auth import guide_compilation_request_authority, guide_compilation_execution_authority, guide_sufficiency_projection_authorization, artifact_policy_projection_authorization
    from app.modules.checkers.catalogue import build_pre_submission_checker_catalogue, project_guide_pre_submission_capabilities
    from app.modules.checkers.api.post_submit_catalogue import current_post_submit_catalogue
    from app.modules.projects.api import ProjectGuideCompilationExecutionCommand, ProjectGuideProjectionCommand, ProjectGuideCompilationExecutionClassification
    from app.modules.projects.api.setup_identity import project_guide_compilation_task_id
    from app.modules.projects.guide_compilation.automatic_request import AutomaticCompilationInputs, automatic_operation_id
    from app.modules.projects.guide_compilation.service import GuideCompilationService
    from app.modules.projects.guide_compilation.orchestrator import project_guide_compilation_execution_port
    from app.modules.projects.guide_compilation.projections import GuideCompilationProjectionService
    from app.interfaces.project_agents import CompilationFinding, GuideEvidenceRef

    sessions = db_session.get_session_factory()
    await seed_setup_service_for_compiled_fixture(sessions)
    async with sessions() as session:
        report = await session.scalar(select(GuideSufficiencyReport).where(GuideSufficiencyReport.source_snapshot_id == source_snapshot_id, GuideSufficiencyReport.project_setup_run_id.is_not(None)))
        if report is not None:
            return report.id
        diagnostic = await session.get(GuideSufficiencyReport, report_id)
        assert diagnostic is not None
        status, findings = diagnostic.status, diagnostic.findings
    manifest = await create_committed_document_fixture(source_snapshot_id)
    configuration = runtime_configuration()
    pre = project_guide_pre_submission_capabilities(build_pre_submission_checker_catalogue())
    post = current_post_submit_catalogue()
    async with sessions() as session:
        setup = await session.get(ProjectSetupRun, str(manifest.setup_run_id))
        setup.status = setup.current_step = "queued"
        setup.celery_task_id = project_guide_compilation_task_id(setup.id, setup.setup_generation)
        await session.commit()
    async with sessions() as session:
        async with guide_compilation_request_authority(session, automatic_operation_id(manifest.setup_run_id, manifest.setup_generation)) as (authority, actor):
            request = await GuideCompilationService(session, authority, automatic_inputs=AutomaticCompilationInputs(guide_document_manifest_port(session), pre, post, configuration)).request_automatic(actor=actor, setup_run_id=manifest.setup_run_id)

    class Runtime:
        identity = configuration.adapter_identity

        def admit_execution(self):
            pass

        async def aclose(self):
            pass

        async def compile_project_guide(self, context, capabilities):
            await record_scripted_document_access(context, capabilities)
            refs = tuple(GuideEvidenceRef(source_item_id=item.source_item_id, document_version_id=item.ingest_id, sha256=item.sha256) for item in context.material.documents)
            compiled_findings = tuple(CompilationFinding(severity=item["severity"], code=item["code"], message=item["message"], evidence_refs=refs) for item in findings)
            if not compiled_findings:
                compiled_findings = (CompilationFinding(severity="info", code="guide.ready", message="Guide complete.", evidence_refs=refs),)
            patch = {"status": {"blocked": "guide_blocked", "passed": "draft_ready", "passed_with_warnings": "draft_ready_with_warnings"}[status], "findings": compiled_findings}
            if status == "blocked":
                patch["submission_artifact_policy"] = None
            return result().model_copy(update=patch)

    execution = project_guide_compilation_execution_port(sessions, material_factory=guide_document_manifest_port, document_access_factory=document_access, pre_submission_capabilities=pre, post_submission_capabilities=post, authorization_context=guide_compilation_execution_authority, runtime_factory=lambda config: Runtime())
    receipt = await execution.execute(ProjectGuideCompilationExecutionCommand(attempt_id=request.attempt_id))
    assert receipt.classification is ProjectGuideCompilationExecutionClassification.PERSISTED
    projections = GuideCompilationProjectionService(sessions, material_factory=guide_document_manifest_port, sufficiency_authorization_factory=guide_sufficiency_projection_authorization, policy_authorization_factory=artifact_policy_projection_authorization)
    projected = await projections.project_guide_sufficiency(ProjectGuideProjectionCommand(attempt_id=request.attempt_id))
    return str(projected.output_id)
