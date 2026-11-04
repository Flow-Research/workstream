"""Scripted document tools for PostgreSQL orchestration proofs.

These tests exercise real parser-bound access custody. ART byte authorization
and parser transport are proved separately, not simulated as live.
"""

from collections.abc import Callable, Mapping
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.modules.model_usage.api import ProjectModelProfileSpec
from app.modules.projects.models import ProjectSetupRun
from tests.actors.support import set_dev_actor
from tests.checkers_model_calls.test_model_call_contract import profile_spec
from tests.projects.client_fixtures import auth_headers
from app.adapters.guide_document_tools import (
    GUIDE_DOCUMENT_PARSER_CAPABILITY_KEY,
    GUIDE_DOCUMENT_PARSER_PROVIDER_KEY,
    GuideDocumentParserAdapter,
    GuideDocumentParserRequest,
    GuideDocumentParserResponse,
)
from app.adapters.projects import project_guide_document_tools_factory
from app.core.config import Settings
from app.interfaces.external_services import (
    ExternalServiceAdapterFactory,
    ExternalServiceAdapterIdentity,
)
from app.interfaces.guide_document_tools import GuideTextLocator
from app.interfaces.project_guide_runtime import ProjectGuideRuntimeConfiguration
from app.modules.projects.api.guide_documents import OpenGuideDocument
from .helpers import SOURCE_BYTES, SOURCE_SHA256, generated_result, runtime_configuration
from app.interfaces.project_agents import GuideEvidenceRef


@asynccontextmanager
async def document_access(_attempt_id, manifest, _configuration):
    class Documents:
        @asynccontextmanager
        async def open(self, handle):
            item = next(item for item in manifest.documents if manifest.handle_for(item) == handle)
            with BytesIO(SOURCE_BYTES) as stream:
                yield OpenGuideDocument(item, stream)

        async def close(self):
            pass

    yield Documents()


class ScriptedParser:
    """Return one exact response while retaining the production source bindings."""

    identity = ExternalServiceAdapterIdentity(
        GUIDE_DOCUMENT_PARSER_CAPABILITY_KEY,
        GUIDE_DOCUMENT_PARSER_PROVIDER_KEY,
    )

    async def parse(self, request: GuideDocumentParserRequest, source: bytes):
        text = source.decode()
        return GuideDocumentParserResponse.create(
            request=request,
            text=text,
            locators=(GuideTextLocator(label="document", start=0, end=len(text)),),
            next_offset=None,
            total_characters=len(text),
        )


def scripted_guide_document_parser_factory(
    *, socket_path: Path, timeout_seconds: float
) -> ExternalServiceAdapterFactory[GuideDocumentParserAdapter]:
    """Inject the scripted parser through the worker's typed parser factory."""
    assert socket_path.is_absolute()
    assert timeout_seconds == 30.0
    factory = ExternalServiceAdapterFactory[GuideDocumentParserAdapter](
        GUIDE_DOCUMENT_PARSER_CAPABILITY_KEY
    )
    factory.register(GUIDE_DOCUMENT_PARSER_PROVIDER_KEY, ScriptedParser)
    return factory


def scripted_runtime_configuration(
    _settings: Settings,
    *,
    adapter_profile_builder: Callable[[Mapping[str, object]], Mapping[str, object]],
) -> ProjectGuideRuntimeConfiguration:
    """Accept the current composition signature and return fixed test settings."""
    assert callable(adapter_profile_builder)
    return runtime_configuration()


def scripted_document_access_runtime(
    _session_factory, attempt_id, manifest, configuration
):
    """Preserve the production access-runtime call shape around scripted bytes."""
    return document_access(attempt_id, manifest, configuration)


def scripted_model_profile_spec(project_id, configuration) -> ProjectModelProfileSpec:
    """Build the bounded profile required by the setup runtime's fixed tools."""
    source = profile_spec().model_dump(mode="python")
    source.update(
        project_id=project_id,
        profile_version=1,
        provider=configuration.model_provider,
        api=configuration.model_api,
        model_snapshot=configuration.model,
        allowed_tools=("read_document", "search_document"),
        maximum_tool_calls=configuration.maximum_tool_calls,
        maximum_tool_output_bytes=configuration.maximum_tool_output_characters * 4,
    )
    return ProjectModelProfileSpec.model_validate(source)


async def publish_scripted_model_profile(client, project_id, configuration, *, version=1):
    """Publish one exact scripted-runtime profile through the Operator API."""
    spec = scripted_model_profile_spec(project_id, configuration).model_copy(
        update={"profile_version": version}
    )
    published = await client.post(
        f"/api/v1/operations/projects/{project_id}/model-profiles",
        headers=auth_headers() | {"Idempotency-Key": str(uuid4())},
        json=spec.model_dump(mode="json"),
    )
    assert published.status_code == 201, published.text
    return published.json()


def configure_scripted_model_transport(monkeypatch, socket_path: Path) -> None:
    """Enable the typed setup-model session without providing a live transport."""
    assert socket_path.is_absolute() and not socket_path.exists()
    fixture_root = socket_path.parent
    values = {
        "ENVIRONMENT": "test",
        "ARTIFACT_STORE_BACKEND": "local",
        "ARTIFACT_LOCAL_ROOT": str(fixture_root / "durable-artifacts"),
        "ARTIFACT_SCRATCH_ROOT": str(fixture_root / "artifact-scratch"),
        "CHECKER_MODEL_PROXY_SOCKET": str(socket_path),
    }
    for scope in ("TASK", "PRODUCER", "PROJECT", "DEPLOYMENT"):
        values[f"ARTIFACT_ADMISSION_{scope}_MAXIMUM_BYTES"] = str(1024 * 1024)
    for name, value in values.items():
        monkeypatch.setenv("WORKSTREAM_" + name, value)
    get_settings.cache_clear()


@pytest.fixture
async def scripted_model_profile(automatic_source, project_client, monkeypatch, tmp_path):
    """Publish the exact inference profile selected by live coordinator tests."""
    configure_scripted_model_transport(monkeypatch, tmp_path / "unused-model-proxy.sock")
    factory, _actor, setup_id, _snapshot = automatic_source
    async with factory() as session:
        project_id = await session.scalar(
            select(ProjectSetupRun.project_id).where(ProjectSetupRun.id == str(setup_id))
        )
        assert project_id is not None
    set_dev_actor(
        monkeypatch,
        roles="viewer",
        subject="scripted-model-operator",
        issuer="flow-test",
        token="project-token",
    )
    admitted = await project_client.get("/api/v1/actors/me", headers=auth_headers())
    assert admitted.status_code == 200, admitted.text
    operator_id = admitted.json()["actor_profile_id"]
    set_dev_actor(
        monkeypatch,
        roles="project_manager",
        subject="project-manager-subject",
        issuer="flow-test",
        token="project-token",
    )
    grant = await project_client.post(
        "/api/v1/admin-role-grants",
        headers=auth_headers(),
        json={
            "target_actor_profile_id": operator_id,
            "role": "operator",
            "scope_type": "system",
            "scope_project_id": None,
            "reason": "Exercise profile-selected project guide compilation",
        },
    )
    assert grant.status_code == 201, grant.text
    set_dev_actor(
        monkeypatch,
        roles="viewer",
        subject="scripted-model-operator",
        issuer="flow-test",
        token="project-token",
    )
    configuration = scripted_runtime_configuration(
        get_settings(), adapter_profile_builder=lambda value: value
    )
    await publish_scripted_model_profile(project_client, project_id, configuration)
    set_dev_actor(
        monkeypatch,
        roles="project_manager",
        subject="project-manager-subject",
        issuer="flow-test",
        token="project-token",
    )
    yield


def document_tools(session_factory, *, document_access_factory=None):
    """Bind the test grant/parser to the production PROJECTS receipt owner."""
    return project_guide_document_tools_factory(
        session_factory,
        document_access_factory=document_access_factory or document_access,
        parser_factory=ScriptedParser,
    )


async def record_scripted_document_access(context, capabilities):
    for document in context.material.documents:
        handle = context.material.handle_for(document)
        result = await capabilities.tools.read_document(handle)
        assert result.source_item_id == document.source_item_id
        assert result.document_version_id == document.ingest_id
        assert result.sha256 == document.sha256
        assert result.text
        if document.sha256 == SOURCE_SHA256:
            assert result.text.encode() == SOURCE_BYTES


async def record_attempt_document_access(sessions, attempt_id, context):
    """Arrange real parser-bound access custody after a committed fence."""
    from app.modules.projects.api.guide_documents import GuideRuntimeCapabilities

    async with document_tools(sessions)(
        attempt_id, context.material, context.runtime_configuration
    ) as tools:
        await record_scripted_document_access(context, GuideRuntimeCapabilities(tools=tools))


class ScriptedGuideRuntime:
    outcome = generated_result()

    def __init__(self, configuration=None):
        self.identity = (configuration or runtime_configuration()).adapter_identity
        self.calls = 0

    def admit_execution(self):
        pass

    async def aclose(self):
        pass

    async def compile_project_guide(self, context, capabilities):
        self.calls += 1
        await record_scripted_document_access(context, capabilities)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        refs = tuple(
            GuideEvidenceRef(
                source_item_id=item.source_item_id,
                document_version_id=item.ingest_id,
                sha256=item.sha256,
            )
            for item in context.material.documents
        )
        return self.outcome.model_copy(
            update={
                field: tuple(
                    item.model_copy(update={"evidence_refs": refs})
                    for item in getattr(self.outcome, field)
                )
                for field in ("findings", "requirements")
            }
        )
