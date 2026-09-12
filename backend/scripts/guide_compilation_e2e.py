"""Deterministic external runtime and canonical guide owners for the isolated API drill."""

from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import hashlib


from app.core.config import get_settings
from app.core.project_agents import project_guide_runtime_configuration
from app.interfaces.external_services import ExternalServiceAdapterFactory
from app.interfaces.project_agents import (
    ProjectGuideAgentRuntime,
    ProjectGuideCompilationResult, CompilationFinding, GuideEvidenceRef,
    SubmissionArtifactPolicyProposal,
    PROJECT_GUIDE_COMPILATION_AGENT_NAME,
    PROJECT_GUIDE_COMPILATION_AGENT_VERSION,
    PROJECT_GUIDE_COMPILATION_SCHEMA_VERSION,
)
from app.modules.projects.api.guide_compilation import (
    ProjectGuideCompilationDelivery,
)
from app.workers import project_setup as worker


class E2EProjectGuideRuntime:
    """One deterministic external inference, with the production closed result contract."""

    def __init__(self, configuration):
        self.identity = configuration.adapter_identity
        self.calls = 0

    def admit_execution(self):
        """The scripted provider has no network admission."""

    async def aclose(self):
        """No external client survives this scripted execution."""

    async def compile_project_guide(self, context, capabilities):
        """Read real ART grants; record explicitly scripted provider resource custody."""
        self.calls += 1
        custody = capabilities.resources
        expires = datetime.now(timezone.utc) + timedelta(minutes=20)
        container_id = "cntr_scripted_" + uuid4().hex
        allocations = []
        async def allocate(kind, handle=None, parent=None, source_file=None, container=None):
            identifier = await custody.begin_allocation(
                kind=kind, document_handle=handle, parent_provider_id=parent, expires_at=expires,
                source_file_allocation_id=source_file,
                container_allocation_id=container,
            )
            await custody.record_allocated(identifier, container_id if kind == "container" else {"file": "file-", "attachment": "cfile_"}[kind] + "scripted_" + uuid4().hex)
            allocations.append(identifier)
            return identifier
        container_allocation = await allocate("container")
        refs = []
        try:
            for document in context.material.documents:
                handle = context.material.handle_for(document)
                async with capabilities.documents.open(handle) as opened:
                    body = opened.reader.read()
                    assert len(body) == document.byte_count
                    assert "sha256:" + hashlib.sha256(body).hexdigest() == document.sha256
                file_allocation = await allocate("file", handle)
                await allocate("attachment", handle, container_id, file_allocation, container_allocation)
                await custody.record_document_open(handle)
                refs.append(GuideEvidenceRef(source_item_id=document.source_item_id,
                    document_version_id=document.ingest_id, sha256=document.sha256))
        finally:
            for identifier in allocations:
                await custody.record_deleted(identifier)
        return ProjectGuideCompilationResult(
            status="draft_ready",
            findings=(CompilationFinding(severity="info", code="guide.ready", message="Assigned documents are available for this scripted contract test.", evidence_refs=tuple(refs)),),
            submission_artifact_policy=SubmissionArtifactPolicyProposal(
                required_artifacts=("answer.md",),
                required_evidence=("checker_log",),
                attestation_terms=("real_api_originality",),
                maximum_file_size_bytes=1_000_000,
                maximum_package_size_bytes=5_000_000,
            ),
            requirements=(),
            pre_submit_bindings=(),
            post_submit_bindings=(),
            capability_suggestions=(),
            setup_notes=(),
            agent_name=PROJECT_GUIDE_COMPILATION_AGENT_NAME,
            agent_version=PROJECT_GUIDE_COMPILATION_AGENT_VERSION,
            schema_version=PROJECT_GUIDE_COMPILATION_SCHEMA_VERSION,
        )


def runtime_factory(runtime):
    """Register the isolated external test adapter through the shared typed factory."""

    def create(configuration):
        factory = ExternalServiceAdapterFactory[ProjectGuideAgentRuntime](
            "project_guide_compilation"
        )
        factory.register(configuration.runtime_key, lambda: runtime)
        return factory.create(configuration.runtime_key)

    return create


async def compile_live_guide(delivery: ProjectGuideCompilationDelivery) -> dict:
    """Drive the sole worker delivery and prove its finalization replays without inference."""
    runtime = E2EProjectGuideRuntime(project_guide_runtime_configuration(get_settings()))
    with patch.object(worker, "create_project_guide_runtime", runtime_factory(runtime)):
        first = await worker._run_project_guide_compilation(delivery)
        replay = await worker._run_project_guide_compilation(delivery)
    assert first == replay, "live finalization replay changed the receipt"
    assert first["status"] == "policy_draft_ready", first
    assert runtime.calls == 1, "live replay invoked inference again"
    return first


def guide_pdf_bytes() -> bytes:
    """Build a one-page PDF for document upload/custody, not model-quality proof."""
    stream = b"BT /F1 12 Tf 40 750 Td (Submit answer.md with reviewable evidence.) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    body = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(body))
        body.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(body)
    body.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        body.extend(f"{offset:010d} 00000 n \n".encode())
    body.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(body)
