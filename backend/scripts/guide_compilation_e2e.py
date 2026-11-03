"""Scripted inference/parser contracts with real ART reads and access custody."""

from functools import partial
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4


from app.adapters.guide_document_tools import (
    GUIDE_DOCUMENT_PARSER_CAPABILITY_KEY,
    GUIDE_DOCUMENT_PARSER_PROVIDER_KEY,
    GuideDocumentParserAdapter,
    GuideDocumentParserRequest,
    GuideDocumentParserResponse,
)
from app.adapters.project_agents import build_project_guide_adapter_profile
from app.core.config import get_settings
from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.core.project_agents import project_guide_runtime_configuration
from app.interfaces.external_services import (
    ExternalServiceAdapterFactory,
    ExternalServiceAdapterIdentity,
)
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
from app.modules.model_usage.api import (
    ModelGenerationSettings,
    ModelPricing,
    ProjectModelProfileSpec,
)


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
        """Read every assigned original through the production neutral tool boundary."""
        self.calls += 1
        refs = []
        expected_handles = set()
        for document in context.material.documents:
            handle = context.material.handle_for(document)
            expected_handles.add(handle)
            offset = 0
            while True:
                result = await capabilities.tools.read_document(handle, offset=offset)
                assert result.handle == handle
                assert result.source_item_id == document.source_item_id
                assert result.document_version_id == document.ingest_id
                assert result.sha256 == document.sha256
                assert result.operation == "read"
                if result.next_offset is None:
                    break
                assert result.next_offset > offset
                offset = result.next_offset
            refs.append(GuideEvidenceRef(source_item_id=document.source_item_id,
                document_version_id=document.ingest_id, sha256=document.sha256))
        assert expected_handles <= await capabilities.tools.opened_handles()
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
            # This drill proposes no project checks; findings retain source coverage.
            requirements=(),
            agent_name=PROJECT_GUIDE_COMPILATION_AGENT_NAME,
            agent_version=PROJECT_GUIDE_COMPILATION_AGENT_VERSION,
            schema_version=PROJECT_GUIDE_COMPILATION_SCHEMA_VERSION,
        )


class ScriptedGuideDocumentParser:
    """Model the parser contract while real ART reads and receipt custody remain active."""

    identity = ExternalServiceAdapterIdentity(
        GUIDE_DOCUMENT_PARSER_CAPABILITY_KEY,
        GUIDE_DOCUMENT_PARSER_PROVIDER_KEY,
    )

    async def parse(
        self, request: GuideDocumentParserRequest, source: bytes
    ) -> GuideDocumentParserResponse:
        """Return source-bound text without claiming parser implementation evidence."""
        assert type(source) is bytes
        assert len(source) == request.source_byte_count
        assert "sha256:" + sha256(source).hexdigest() == request.source_sha256
        assert request.operation == "read"
        full_text = "Scripted contract parser verified the exact assigned original."
        text = full_text[request.offset : request.offset + request.limit]
        consumed_to = request.offset + len(text)
        next_offset = consumed_to if consumed_to < len(full_text) else None
        return GuideDocumentParserResponse.create(
            request=request,
            text=text,
            locators=(),
            next_offset=next_offset,
            total_characters=len(full_text),
        )


def scripted_guide_document_parser_factory(
    *, socket_path: Path, timeout_seconds: float
):
    """Inject the isolated drill parser at the existing typed factory boundary."""
    assert socket_path.is_absolute()
    assert timeout_seconds > 0
    factory = ExternalServiceAdapterFactory[GuideDocumentParserAdapter](
        GUIDE_DOCUMENT_PARSER_CAPABILITY_KEY
    )
    factory.register(GUIDE_DOCUMENT_PARSER_PROVIDER_KEY, ScriptedGuideDocumentParser)
    return factory


def runtime_factory(runtime):
    """Register the isolated external test adapter through the shared typed factory."""

    def create(configuration):
        factory = ExternalServiceAdapterFactory[ProjectGuideAgentRuntime](
            "project_guide_compilation"
        )
        factory.register(configuration.runtime_key, lambda: runtime)
        return factory.create(configuration.runtime_key)

    return create


async def publish_scripted_model_profile(
    client, operator_token: str, project_id: str,
) -> dict:
    """Publish the exact finite profile required by the scripted setup runtime."""
    settings = get_settings()
    configuration = project_guide_runtime_configuration(
        settings,
        adapter_profile_builder=partial(
            build_project_guide_adapter_profile, settings.project_agent_runtime
        ),
    )
    maximum_calls = configuration.maximum_turns
    spec = ProjectModelProfileSpec(
        project_id=UUID(project_id),
        profile_version=1,
        provider=configuration.model_provider,
        api=configuration.model_api,
        model_snapshot=configuration.model,
        settings=ModelGenerationSettings(
            reasoning_effort="medium", text_verbosity="low",
        ),
        maximum_request_bytes=1_048_576,
        maximum_output_bytes=131_072,
        maximum_response_bytes=1_048_576,
        maximum_input_tokens=1_000_000,
        maximum_output_tokens=16_384,
        maximum_calls=maximum_calls,
        maximum_total_request_bytes=1_048_576 * maximum_calls,
        maximum_total_response_bytes=1_048_576 * maximum_calls,
        maximum_total_input_tokens=1_000_000 * maximum_calls,
        maximum_total_output_tokens=16_384 * maximum_calls,
        allowed_tools=("read_document", "search_document"),
        maximum_tool_calls=configuration.maximum_tool_calls,
        maximum_tool_output_bytes=configuration.maximum_tool_output_characters * 4,
        deadline_ms=configuration.timeout_seconds * 1000,
        pricing=ModelPricing(
            pricing_policy_id=new_record_id(),
            pricing_policy_version=1,
            pricing_policy_digest=canonical_json_hash(
                {"contract": "real_api_scripted_model_pricing", "version": 1}
            ),
            uncached_input_nanodollars_per_token=1,
            cached_input_nanodollars_per_token=1,
            output_nanodollars_per_token=1,
        ),
    )
    response = await client.post(
        f"/api/v1/operations/projects/{project_id}/model-profiles",
        headers={"Authorization": f"Bearer {operator_token}",
                 "Idempotency-Key": str(uuid4())},
        json=spec.model_dump(mode="json"),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def compile_live_guide(delivery: ProjectGuideCompilationDelivery) -> dict:
    """Drive the sole worker delivery and prove its finalization replays without inference."""
    from app.workers import project_setup as worker

    settings = get_settings()
    configuration = project_guide_runtime_configuration(
        settings,
        adapter_profile_builder=partial(
            build_project_guide_adapter_profile, settings.project_agent_runtime
        ),
    )
    runtime = E2EProjectGuideRuntime(configuration)
    with patch.object(
        worker, "create_project_guide_runtime", runtime_factory(runtime)
    ), patch.object(
        worker, "guide_document_parser_factory", scripted_guide_document_parser_factory
    ):
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
