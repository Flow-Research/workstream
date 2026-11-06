from __future__ import annotations

import importlib
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.adapters.guide_document_tools import (
    GUIDE_DOCUMENT_PARSER_PROVIDER_KEY,
    GuideDocumentParserRequest,
)
from app.interfaces.guide_document_tools import GuideDocumentToolResult
from app.modules.projects.api.guide_documents import GuideRuntimeCapabilities
from tests.projects.guide_compilation.helpers import context, ids, runtime_configuration

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
MODULES = [importlib.import_module("api_contract_e2e")]


@pytest.mark.asyncio
async def test_api_drill_requests_assistance_after_upload_before_delivering(monkeypatch) -> None:
    """Completed uploads alone cannot supply the drill's compilation delivery."""
    from uuid import UUID, uuid4

    import httpx

    from app.modules.projects.api.setup_identity import project_guide_compilation_task_id

    project_id, guide_id, snapshot_id, setup_id, document_id = (str(uuid4()) for _ in range(5))
    path = f"/api/v1/projects/{project_id}/guides/{guide_id}"
    events = []

    def respond(request):
        assert request.headers["Authorization"] == "Bearer project-pm"
        response_headers = {
            key: request.headers[key]
            for key in ("x-request-id", "x-correlation-id") if key in request.headers
        }
        if request.method == "POST":
            UUID(request.headers["Idempotency-Key"])
            if request.url.path == path + f"/documents/{document_id}/content":
                assert request.content.startswith(b"%PDF")
                events.append("upload")
            else:
                assert request.url.path == path + "/setup"
                assert events == ["upload", "not_requested"]
                events.append("request")
            return httpx.Response(202, json={}, headers=response_headers)
        assert request.url.path == path + "/setup-runs/latest"
        requested = "request" in events
        events.append("queued" if requested else "not_requested")
        return httpx.Response(200, headers=response_headers, json={
            "id": setup_id, "source_snapshot_id": snapshot_id, "setup_generation": 1,
            "status": "queued" if requested else "not_requested",
            "current_step": "queued" if requested else "not_requested",
            "celery_task_id": project_guide_compilation_task_id(setup_id, 1) if requested else None,
            "documents_ready_at": "2026-11-05T00:00:00Z" if requested else None,
            "finalized_compilation_id": None,
        })

    class DeliveryReached(Exception):
        pass

    async def compile_guide(delivery):
        assert events == ["upload", "not_requested", "request", "queued"]
        assert delivery.source_snapshot_id == UUID(snapshot_id)
        raise DeliveryReached

    monkeypatch.setattr(importlib.import_module("guide_compilation_e2e"), "compile_live_guide", compile_guide)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url="http://test") as client:
        with pytest.raises(DeliveryReached):
            await MODULES[0].exercise_guide_setup_contract(
                client, "administrator", "project-pm", "contributor", "service", "role-only",
                "foreign-pm", "manager-subject", project_id, guide_id, "run",
                documents=[{"document_id": document_id, "media_type": "application/pdf"}],
            )


def test_scripted_guide_broker_acknowledgement_binds_exact_delivery() -> None:
    """The API drill cannot acknowledge a different generation or task ID."""
    from uuid import uuid4

    from app.modules.projects.api.setup_identity import project_guide_compilation_task_id

    args = [str(uuid4()) for _ in range(4)] + [1]
    task_id = project_guide_compilation_task_id(args[3], args[4])
    acknowledge = MODULES[0].acknowledge_guide_delivery
    assert acknowledge(args=args, task_id=task_id).id == task_id
    with pytest.raises(ValueError):
        acknowledge(args=[*args[:4], 2], task_id=task_id)
    with pytest.raises(ValueError):
        acknowledge(args=args, task_id=str(uuid4()))
    with pytest.raises(ValueError):
        acknowledge(args=args[:4], task_id=task_id)


@pytest.mark.asyncio
async def test_scripted_guide_runtime_reads_neutral_tools_before_citing_originals() -> None:
    """The API drill runtime proves access through tools, without hosted-resource facts."""
    guide_runtime = importlib.import_module("guide_compilation_e2e")
    compilation_context = context(ids())
    document = compilation_context.material.documents[0]
    handle = compilation_context.material.handle_for(document)
    reads: list[tuple[str, int, int]] = []
    opened: set[str] = set()

    async def read_document(value: str, *, offset: int = 0, limit: int = 16000):
        reads.append((value, offset, limit))
        opened.add(value)
        return GuideDocumentToolResult(
            handle=value,
            source_item_id=document.source_item_id,
            document_version_id=document.ingest_id,
            sha256=document.sha256,
            operation="read",
            text="Guide fixture",
            locators=(),
            next_offset=None,
            total_characters=13,
        )

    async def opened_handles():
        return frozenset(opened)

    tools = SimpleNamespace(
        read_document=read_document,
        opened_handles=opened_handles,
    )
    runtime = guide_runtime.E2EProjectGuideRuntime(runtime_configuration())

    result = await runtime.compile_project_guide(
        compilation_context, GuideRuntimeCapabilities(tools=tools)
    )

    assert reads == [(handle, 0, 16000)]
    assert runtime.calls == 1
    assert result.requirements == ()
    assert len(result.findings[0].evidence_refs) == 1
    reference = result.findings[0].evidence_refs[0]
    assert reference.source_item_id == document.source_item_id
    assert reference.document_version_id == document.ingest_id
    assert reference.sha256 == document.sha256


@pytest.mark.asyncio
async def test_scripted_parser_preserves_source_bindings_without_a_socket() -> None:
    """The API contract drill stubs parsing only after receiving exact ART bytes."""
    from hashlib import sha256
    from uuid import uuid4

    guide_runtime = importlib.import_module("guide_compilation_e2e")
    source = b"%PDF-1.7\ncontract fixture\n%%EOF"
    request = GuideDocumentParserRequest(
        request_id=uuid4(),
        source_sha256="sha256:" + sha256(source).hexdigest(),
        source_byte_count=len(source),
        media_type="application/pdf",
        operation="read",
        offset=0,
        limit=16000,
    )
    parser = guide_runtime.scripted_guide_document_parser_factory(
        socket_path=Path("/unused"), timeout_seconds=30.0
    ).create(GUIDE_DOCUMENT_PARSER_PROVIDER_KEY)

    result = await parser.parse(request, source)

    result.validate_against(request)
    with pytest.raises(AssertionError):
        await parser.parse(request, source + b"changed")


@pytest.mark.parametrize("module", MODULES)
@pytest.mark.parametrize(
    "name", ["workstream_test", "test_workstream", "workstream_test_012345abcdef"]
)
def test_api_drill_database_guard_accepts_only_supported_local_names(module, name: str) -> None:
    """The destructive drill accepts historical and isolated local test DB names."""
    module.assert_local_database_url(
        f"postgresql+asyncpg://workstream:secret@127.0.0.1:5433/{name}"
    )


@pytest.mark.parametrize("module", MODULES)
@pytest.mark.parametrize(
    ("host", "name"),
    [
        ("db.example.com", "workstream_test_012345abcdef"),
        ("localhost", "workstream_test_012345abcdef_extra"),
        ("localhost", "workstream_test_012345ABCDEf"),
        ("localhost", '"workstream_test_012345abcdef"'),
    ],
)
def test_api_drill_database_guard_rejects_lookalikes_without_leaking_url(
    monkeypatch: pytest.MonkeyPatch, module, host: str, name: str
) -> None:
    """Remote and lookalike targets fail closed with a non-secret diagnostic."""
    monkeypatch.delenv("WORKSTREAM_ALLOW_NONLOCAL_E2E_DATABASE", raising=False)
    url = f"postgresql+asyncpg://workstream:secret@{host}:5433/{name}"
    with pytest.raises(RuntimeError) as exc_info:
        module.assert_local_database_url(url)
    assert url not in str(exc_info.value)
    assert "Refusing to run" in str(exc_info.value)


def test_api_contract_drill_requires_isolated_database_without_leaking_url() -> None:
    """The complete API drill refuses a shared persistent test database."""
    isolated_url = (
        "postgresql+asyncpg://workstream:secret@127.0.0.1:5433/workstream_test_012345abcdef"
    )
    api_contract = MODULES[0]
    api_contract.assert_isolated_database_url(isolated_url)

    persistent_url = "postgresql+asyncpg://workstream:secret@127.0.0.1:5433/workstream_test"
    with pytest.raises(RuntimeError) as exc_info:
        api_contract.assert_isolated_database_url(persistent_url)
    assert persistent_url not in str(exc_info.value)
    assert "persistent test database" in str(exc_info.value)


def test_api_contract_uses_runner_owned_minio_namespace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The hosted fan-in maps its isolated MinIO namespace into real ART settings."""
    api_contract = MODULES[0]
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setenv("WORKSTREAM_TEST_MINIO_ENDPOINT", "http://127.0.0.1:9000")
    monkeypatch.setenv("WORKSTREAM_TEST_MINIO_BUCKET", "workstream-ci-isolated-012345abcdef")
    monkeypatch.setenv("WORKSTREAM_TEST_MINIO_PREFIX", "ci/isolated/012345abcdef")

    env = api_contract.api_environment()

    assert env["WORKSTREAM_ARTIFACT_STORE_BACKEND"] == "s3_compatible"
    assert env["WORKSTREAM_ARTIFACT_S3_PROVIDER_PROFILE"] == "minio"
    assert env["WORKSTREAM_ARTIFACT_S3_ENDPOINT_URL"] == "http://127.0.0.1:9000"
    assert env["WORKSTREAM_ARTIFACT_S3_BUCKET"] == "workstream-ci-isolated-012345abcdef"
    assert env["WORKSTREAM_ARTIFACT_S3_PRIVATE_PREFIX"] == "ci/isolated/012345abcdef"
    assert env["WORKSTREAM_ARTIFACT_SCRATCH_ROOT"] == str(
        tmp_path / "workstream-api-contract-scratch"
    )
    for key, value in env.items():
        if key.startswith("WORKSTREAM_ARTIFACT_"):
            monkeypatch.setenv(key, value)
    settings = Settings(_env_file=None, environment=env["WORKSTREAM_ENVIRONMENT"])
    assert settings.artifact_store_backend == "s3_compatible"
    assert settings.artifact_s3_bucket == "workstream-ci-isolated-012345abcdef"


def test_full_api_contract_enables_local_artifacts_for_typed_model_sessions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Provider-free API consumers still admit the typed setup-model capability."""
    api_contract = MODULES[0]
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    for key in (
        "WORKSTREAM_TEST_MINIO_ENDPOINT",
        "WORKSTREAM_TEST_MINIO_BUCKET",
        "WORKSTREAM_TEST_MINIO_PREFIX",
        "WORKSTREAM_ARTIFACT_STORE_BACKEND",
    ):
        monkeypatch.delenv(key, raising=False)

    env = api_contract.api_environment()
    assert env.get("WORKSTREAM_ARTIFACT_STORE_BACKEND", "disabled") == "disabled"
    assert "WORKSTREAM_CHECKER_MODEL_PROXY_SOCKET" not in env
    api_contract.configure_scripted_model_session_environment(env)

    assert env["WORKSTREAM_ARTIFACT_STORE_BACKEND"] == "local"
    assert env["WORKSTREAM_ARTIFACT_LOCAL_ROOT"] != env["WORKSTREAM_ARTIFACT_SCRATCH_ROOT"]
    assert Path(env["WORKSTREAM_ARTIFACT_LOCAL_ROOT"]).stat().st_mode & 0o777 == 0o700
    assert Path(env["WORKSTREAM_ARTIFACT_SCRATCH_ROOT"]).stat().st_mode & 0o777 == 0o700
    assert env["WORKSTREAM_CHECKER_MODEL_PROXY_SOCKET"].startswith(str(tmp_path) + "/")
    for key, value in env.items():
        if key.startswith("WORKSTREAM_ARTIFACT_") or key == (
            "WORKSTREAM_CHECKER_MODEL_PROXY_SOCKET"
        ):
            monkeypatch.setenv(key, value)
    settings = Settings(_env_file=None, environment=env["WORKSTREAM_ENVIRONMENT"])
    assert settings.artifact_store_backend == "local"
    assert settings.checker_model_proxy_socket is not None


def test_real_api_drill_provisions_exact_guide_artifact_pipeline_services() -> None:
    """The fan-in owns every fixed principal required before guide setup can run."""
    api_contract = MODULES[0]

    assert api_contract.GUIDE_ARTIFACT_PIPELINE_SERVICE_IDENTITIES == (
        "workstream.artifact.put_resolver",
        "workstream.artifact.verifier",
        "workstream.artifact.scheduler",
        "workstream.artifact.binding",
        "workstream.artifact.guide_reader",
        "workstream.project.setup",
    )


def test_api_drill_action_expectations_use_current_catalogue():
    """Retired actions cannot remain in the drill's independent exact inventories."""
    import ast
    from app.modules.authorization.catalogue import ActionId

    source = ast.parse(Path(MODULES[0].__file__).read_text())
    inventories = [
        node.comparators[0]
        for node in ast.walk(source)
        if isinstance(node, ast.Compare)
        and isinstance(node.left, ast.Subscript)
        and isinstance(node.left.slice, ast.Constant)
        and node.left.slice.value == "effective_action_ids"
        and isinstance(node.comparators[0], ast.List)
    ]
    assert inventories
    current_actions = {action.value for action in ActionId}
    for inventory in inventories:
        assert set(ast.literal_eval(inventory)) <= current_actions
