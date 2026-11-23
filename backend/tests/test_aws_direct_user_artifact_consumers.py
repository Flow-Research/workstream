"""Loopback HTTP signing, artifact readback and scoped access using direct IAM user credentials."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import hashlib
from pathlib import Path
import re
from types import SimpleNamespace
from uuid import uuid4

from aiobotocore.config import AioConfig
from aiohttp import web
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.artifacts import (
    create_artifact_store_bootstrap,
    guide_document_manifest_port,
)
from app.adapters.artifacts import s3_compatible
from app.adapters.projects import project_guide_document_scope_port
from app.interfaces.artifacts import (
    ArtifactStoreNamespaceClaim,
)
from app.modules.artifacts.guide_document_access import ScopedGuideDocumentGrant
from app.modules.artifacts.preparation import (
    ArtifactPreparationLimits,
    ArtifactPreparationService,
    ArtifactScratchManager,
)
from app.modules.artifacts.service import artifact_storage_namespace_spec
from app.modules.projects.api.guide_documents import (
    GuideDocumentManifestRequest,
    GuideDocumentUnavailable,
)
from tests.projects.guide_compilation.helpers import SOURCE_BYTES, context, seed_database
from tests.projects.guide_compilation.test_hidden_orchestrator_postgresql import (
    _authorized_attempt,
    _backend,
)
from app.adapters.artifacts.aws_direct_user import DIRECT_USER_METHOD
from tests.test_aws_direct_user_credentials import ACCESS_KEY_ID, USER_ARN, direct_user_settings


_ACCESS_KEY = re.compile(r"Credential=([^/]+)/")


class _ReadAuthority:
    """Observe the real grant's exact facts while allowing the seeded attempt."""

    def __init__(self) -> None:
        self.facts: list[object] = []

    async def prepare(self, *, facts: object, idempotency_key: object) -> object:
        assert idempotency_key is not None
        return facts

    async def consume(self, *, prepared_authorization: object, facts: object) -> None:
        assert prepared_authorization == facts
        self.facts.append(facts)

    def close(self) -> None:
        pass


class _LoopbackS3:
    """Small S3 HTTP surface that preserves signed request observations."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.requests: list[tuple[str, str, str]] = []
        self.identity_requests: list[str] = []
        self._runner: web.AppRunner | None = None
        self.endpoint_url = ""

    async def start(self) -> None:
        application = web.Application()
        application.router.add_route("*", "/{path:.*}", self._handle)
        self._runner = web.AppRunner(application)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await site.start()
        host, port = self._runner.addresses[0]
        self.endpoint_url = f"http://{host}:{port}"

    async def close(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()

    async def _handle(self, request: web.Request) -> web.Response:
        authorization = request.headers.get("Authorization", "")
        access_key = _ACCESS_KEY.search(authorization)
        if access_key is None:
            return web.Response(status=403)
        if request.method == "POST":
            action = await request.post()
            assert action["Action"] == "GetCallerIdentity"
            self.identity_requests.append(access_key.group(1))
            return web.Response(text=(
                '<GetCallerIdentityResponse xmlns="https://sts.amazonaws.com/doc/2011-06-15/">'
                '<GetCallerIdentityResult><Account>123456789012</Account>'
                f'<Arn>{USER_ARN}</Arn><UserId>AIDA00000000000001</UserId>'
                '</GetCallerIdentityResult></GetCallerIdentityResponse>'
            ), content_type="application/xml")
        path = request.match_info["path"]
        self.requests.append((request.method, path, access_key.group(1)))
        if request.method == "PUT":
            if request.headers.get("If-None-Match") == "*" and path in self.objects:
                return web.Response(
                    status=412,
                    body=(
                        b"<Error><Code>PreconditionFailed</Code>"
                        b"<Message>object exists</Message></Error>"
                    ),
                    content_type="application/xml",
                )
            body = await request.read()
            self.objects[path] = body
            return web.Response(
                status=200,
                headers={"ETag": f'"{hashlib.md5(body).hexdigest()}"'},  # noqa: S324
            )
        if path not in self.objects:
            return web.Response(
                status=404,
                body=b"<Error><Code>NoSuchKey</Code></Error>",
                content_type="application/xml",
            )
        body = self.objects[path]
        if request.method == "HEAD":
            return web.Response(status=200, headers={"Content-Length": str(len(body))})
        if request.method == "GET":
            return web.Response(status=200, body=body)
        return web.Response(status=405)


@pytest.fixture
async def loopback_s3() -> AsyncIterator[_LoopbackS3]:
    endpoint = _LoopbackS3()
    await endpoint.start()
    try:
        yield endpoint
    finally:
        await endpoint.close()


def _preparation(root: Path) -> tuple[ArtifactScratchManager, ArtifactPreparationService]:
    manager = ArtifactScratchManager(
        root=root,
        limits=ArtifactPreparationLimits(
            maximum_files=3,
            maximum_concurrency=3,
            minimum_free_bytes=0,
            reservation_ttl_seconds=30,
            total_deadline_seconds=10,
            cleanup_margin_seconds=5,
            stream_buffer_bytes=1024,
            maximum_source_bytes=1024 * 1024,
        ),
    )
    return manager, ArtifactPreparationService(manager)


async def _bytes(content: bytes) -> AsyncIterator[bytes]:
    for offset in range(0, len(content), 5):
        yield content[offset : offset + 5]


@asynccontextmanager
async def _direct_user_store(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    endpoint: _LoopbackS3,
):
    """Compose the production provider and reroute only its test HTTP socket."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    settings = direct_user_settings(
        tmp_path,
        artifact_stream_buffer_bytes=1024,
        artifact_s3_connect_timeout_seconds=10,
        artifact_s3_read_timeout_seconds=30,
        artifact_s3_write_timeout_seconds=30,
        artifact_s3_pool_timeout_seconds=10,
        artifact_s3_operation_total_timeout_seconds=60,
    )
    assert settings.artifact_s3_endpoint_url is None

    sessions = []
    original_session_factory = s3_compatible.create_isolated_aws_credential_session

    def routed_session(configuration):
        session = original_session_factory(
            configuration,
            environ={"HOME": str(tmp_path)},
        )
        original_create_client = session.create_client

        def create_client(service_name: str, **kwargs: object):
            if service_name == "sts":
                return original_create_client(service_name, endpoint_url=endpoint.endpoint_url, **kwargs)
            assert service_name == "s3"
            assert kwargs["endpoint_url"] is None
            kwargs["endpoint_url"] = endpoint.endpoint_url
            config = kwargs["config"]
            assert isinstance(config, AioConfig)
            kwargs["config"] = config.merge(
                AioConfig(
                    s3={
                        "addressing_style": "path",
                        "payload_signing_enabled": False,
                    }
                )
            )
            return original_create_client(service_name, **kwargs)

        session.create_client = create_client
        sessions.append(session)
        return session

    monkeypatch.setattr(
        s3_compatible,
        "create_isolated_aws_credential_session",
        routed_session,
    )
    bootstrap = create_artifact_store_bootstrap(settings)
    namespace = artifact_storage_namespace_spec(settings, bootstrap)
    store = bootstrap.initialize_after_namespace_claim(
        ArtifactStoreNamespaceClaim(
            bootstrap.identity,
            bootstrap.namespace_identity,
            namespace.namespace_fingerprint,
        )
    )
    try:
        yield SimpleNamespace(
            settings=settings,
            store=store,
            namespace=namespace,
            sessions=sessions,
        )
    finally:
        bootstrap.close()


async def _upload(
    store: object,
    preparation: ArtifactPreparationService,
    content: bytes,
) -> str:
    prepared = await preparation.prepare(
        _bytes(content),
        media_type="application/pdf",
    )
    try:
        result = await store.put(prepared.committed_source)
        return result.provider_object_ref
    finally:
        await prepared.close()


@pytest.mark.asyncio
async def test_direct_user_signs_sealed_upload_and_exact_readback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    loopback_s3: _LoopbackS3,
) -> None:
    """Exercise IAM identity, signing, HTTP, storage, and exact download."""
    manager, preparation = _preparation(tmp_path / "preparation")
    try:
        async with _direct_user_store(monkeypatch, tmp_path / "identity", loopback_s3) as case:
            provider_ref = await _upload(case.store, preparation, SOURCE_BYTES)
            assert len(case.sessions) == 1
            credentials = await case.sessions[0].get_credentials()
            assert credentials is not None and credentials.method == DIRECT_USER_METHOD

            downloaded = b"".join([block async for block in case.store.open(provider_ref)])
            assert downloaded == SOURCE_BYTES
            assert "sha256:" + hashlib.sha256(downloaded).hexdigest() == (
                "sha256:" + hashlib.sha256(SOURCE_BYTES).hexdigest()
            )
            assert (await manager.usage()).reservation_count == 0
    finally:
        manager.close()

    assert loopback_s3.identity_requests == [ACCESS_KEY_ID]
    methods_and_keys = [(method, key) for method, _path, key in loopback_s3.requests]
    assert methods_and_keys == [
        ("PUT", ACCESS_KEY_ID),
        ("HEAD", ACCESS_KEY_ID),
        ("GET", ACCESS_KEY_ID),
    ]


@pytest.mark.asyncio
async def test_setup_agent_grant_reads_only_assigned_direct_user_object(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    loopback_s3: _LoopbackS3,
    clean_postgres_database: str,
) -> None:
    """Preserve exact setup-document scope, commitment, and scratch cleanup."""
    source_manager, source_preparation = _preparation(tmp_path / "source-scratch")
    grant_manager, grant_preparation = _preparation(tmp_path / "grant-scratch")
    engine = None
    grant = None
    try:
        async with _direct_user_store(monkeypatch, tmp_path / "identity", loopback_s3) as case:
            provider_ref = await _upload(
                case.store,
                source_preparation,
                SOURCE_BYTES,
            )
            values = await seed_database(
                clean_postgres_database,
                namespace=case.namespace,
                provider_object_ref=provider_ref,
            )
            engine = create_async_engine(clean_postgres_database)
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as session:
                material = await guide_document_manifest_port(session).load(
                    GuideDocumentManifestRequest(
                        project_id=values["project"],
                        guide_id=values["guide"],
                        guide_source_snapshot_id=values["snapshot"],
                        project_setup_run_id=values["setup_1"],
                        setup_generation=1,
                    )
                )
            compilation_context = context(values).model_copy(update={"material": material})
            request = await _authorized_attempt(
                clean_postgres_database,
                values,
                compilation_context=compilation_context,
            )
            backend = _backend(sessions)
            state = await backend.load(request.attempt_id)
            assert (await backend.fence(state)).dispatch_permitted
            document = material.documents[0]

            authority = _ReadAuthority()
            grant = ScopedGuideDocumentGrant(
                sessions,
                case.store,
                case.namespace,
                grant_preparation,
                lambda _session: authority,
                scope_factory=project_guide_document_scope_port,
                manifest_factory=guide_document_manifest_port,
                attempt_id=request.attempt_id,
                manifest=material,
                lifetime_seconds=90,
                maximum_document_bytes=1024 * 1024,
            )

            before_denial = len(loopback_s3.requests)
            with pytest.raises(GuideDocumentUnavailable, match="access_denied"):
                async with grant.open(str(uuid4())):
                    pytest.fail("unassigned document bytes left the grant")
            assert len(loopback_s3.requests) == before_denial

            handle = material.handle_for(document)
            async with grant.open(handle) as opened:
                body = opened.reader.read()
                assert opened.document == document
                assert body == SOURCE_BYTES
                assert len(body) == document.byte_count
                assert "sha256:" + hashlib.sha256(body).hexdigest() == document.sha256
            assert len(authority.facts) == 1
            assert authority.facts[0].guide_source_item_id == document.source_item_id
            assert (await grant_manager.usage()).reservation_count == 0
            assert (await source_manager.usage()).reservation_count == 0
    finally:
        if grant is not None:
            await grant.close()
        if engine is not None:
            await engine.dispose()
        grant_manager.close()
        source_manager.close()
