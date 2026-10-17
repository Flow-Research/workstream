"""Focused offline proof for native AWS activation boundaries."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from botocore.exceptions import ClientError

from app.adapters.artifacts.aws_live_proof import _canonical_observed_role_arn
from app.adapters.artifacts.s3_compatible import (
    S3CompatibleArtifactStore,
    S3CompatibleArtifactStoreBootstrap,
)
from app.interfaces.artifacts import (
    ArtifactProviderActivationLease,
    ArtifactProviderLiveProofRequiredError,
    ArtifactStoreNamespaceClaim,
    artifact_store_namespace_material,
)
from tests.artifact_store_helpers import minted_source


_ACTIVATION_ID = UUID("0199e648-0b77-7000-8000-000000000001")
_PROVIDER_REF = "sha256/00/" + "0" * 62


class _Guard:
    def __init__(self, events: list[object], *, deny: bool = False) -> None:
        self.events = events
        self.deny = deny

    async def select_for_call(
        self, *, namespace_fingerprint: str
    ) -> ArtifactProviderActivationLease:
        self.events.append(("select", namespace_fingerprint))
        if self.deny:
            raise ArtifactProviderLiveProofRequiredError("proof is absent")
        return ArtifactProviderActivationLease(_ACTIVATION_ID)

    async def require_for_call(
        self,
        activation_id: UUID,
        *,
        namespace_fingerprint: str,
    ) -> ArtifactProviderActivationLease:
        self.events.append(("require", activation_id, namespace_fingerprint))
        assert activation_id == _ACTIVATION_ID
        return ArtifactProviderActivationLease(activation_id)


class _Body:
    def __init__(self, content: bytes) -> None:
        self._content = content
        self._read = False

    async def __aenter__(self) -> _Body:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def read(self, _limit: int) -> bytes:
        if self._read:
            return b""
        self._read = True
        return self._content


class _Client:
    def __init__(
        self,
        events: list[object],
        content: bytes,
        *,
        put_error: BaseException | None = None,
    ) -> None:
        self.events = events
        self.content = content
        self.put_error = put_error

    async def put_object(self, **kwargs: object) -> dict[str, object]:
        self.events.append("put_object")
        body = kwargs["Body"]
        if not isinstance(body, bytes):
            received = bytearray()
            while chunk := await body.read(1024):
                received.extend(chunk)
            assert bytes(received) == self.content
        if self.put_error is not None:
            raise self.put_error
        return {}

    async def head_object(self, **_kwargs: object) -> dict[str, object]:
        self.events.append("head_object")
        return {"ContentLength": len(self.content)}

    async def get_object(self, **_kwargs: object) -> dict[str, object]:
        self.events.append("get_object")
        return {"Body": _Body(self.content)}


def _precondition_error() -> ClientError:
    return ClientError(
        {"Error": {"Code": "PreconditionFailed"}, "ResponseMetadata": {"HTTPStatusCode": 412}},
        "PutObject",
    )


def _initialized_store(
    guard: _Guard,
    *,
    session_factory: Any,
) -> tuple[S3CompatibleArtifactStore, str]:
    store = S3CompatibleArtifactStore(
        provider_profile="aws_s3",
        region="us-east-1",
        endpoint_url=None,
        bucket="workstream-artifacts-prod",
        private_prefix="workstream/artifacts",
        addressing_style="virtual",
        session_factory=session_factory,
        activation_guard=guard,
        buffer_bytes=1024,
        connect_timeout_seconds=30,
        read_timeout_seconds=30,
        write_timeout_seconds=30,
        pool_timeout_seconds=30,
        operation_total_timeout_seconds=60,
        max_pool_connections=1,
    )
    bootstrap = S3CompatibleArtifactStoreBootstrap(store)
    namespace = bootstrap.namespace_identity
    _, fingerprint = artifact_store_namespace_material(
        backend="s3_compatible",
        adapter_identity=bootstrap.identity,
        namespace_identity=namespace,
    )
    initialized = bootstrap.initialize_after_namespace_claim(
        ArtifactStoreNamespaceClaim(bootstrap.identity, namespace, fingerprint)
    )
    return initialized, fingerprint


@pytest.mark.asyncio
async def test_open_selects_on_consumption_and_rechecks_same_id_before_nested_get(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []
    guard = _Guard(events)
    store, fingerprint = _initialized_store(
        guard,
        session_factory=lambda: (_ for _ in ()).throw(AssertionError("session constructed")),
    )
    client = _Client(events, b"provider bytes")

    @asynccontextmanager
    async def fake_client() -> Any:
        yield client

    monkeypatch.setattr(store, "_client", fake_client)
    stream = store.open(_PROVIDER_REF)
    assert events == []

    assert b"".join([chunk async for chunk in stream]) == b"provider bytes"
    assert events == [
        ("select", fingerprint),
        ("require", _ACTIVATION_ID, fingerprint),
        "head_object",
        ("require", _ACTIVATION_ID, fingerprint),
        ("require", _ACTIVATION_ID, fingerprint),
        "get_object",
    ]


@pytest.mark.asyncio
async def test_activation_denial_precedes_session_factory_and_sdk_call() -> None:
    events: list[object] = []
    guard = _Guard(events, deny=True)

    def session_factory() -> object:
        events.append("session")
        raise AssertionError("credential session constructed before activation")

    store, fingerprint = _initialized_store(guard, session_factory=session_factory)
    with pytest.raises(ArtifactProviderLiveProofRequiredError):
        await store.head(_PROVIDER_REF)
    assert events == [("select", fingerprint)]


def _assert_same_activation_immediately_precedes_sdk_calls(
    events: list[object],
    fingerprint: str,
) -> None:
    guards = [event for event in events if isinstance(event, tuple)]
    assert guards[0] == ("select", fingerprint)
    assert all(event == ("require", _ACTIVATION_ID, fingerprint) for event in guards[1:])
    for index, event in enumerate(events):
        if event in {"put_object", "head_object", "get_object"}:
            assert events[index - 1] == ("require", _ACTIVATION_ID, fingerprint)


@pytest.mark.asyncio
async def test_put_and_head_recheck_same_activation_immediately_before_sdk_calls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    content = b"guarded provider bytes"
    for operation in ("put", "head"):
        events: list[object] = []
        store, fingerprint = _initialized_store(
            _Guard(events),
            session_factory=lambda: (_ for _ in ()).throw(AssertionError("session constructed")),
        )
        client = _Client(events, content)

        @asynccontextmanager
        async def fake_client() -> Any:
            yield client

        monkeypatch.setattr(store, "_client", fake_client)
        if operation == "put":
            async with minted_source(tmp_path / operation, content) as source:
                result = await store.put(source)
            assert result.replayed is False
        else:
            result = await store.head(_PROVIDER_REF)
            assert result.exists is True
        _assert_same_activation_immediately_precedes_sdk_calls(events, fingerprint)


@pytest.mark.asyncio
@pytest.mark.parametrize("put_error", [_precondition_error(), TimeoutError("uncertain")])
async def test_replay_and_uncertain_write_reuse_one_activation_for_every_sdk_call(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    put_error: BaseException,
) -> None:
    content = b"retained exact bytes"
    events: list[object] = []
    store, fingerprint = _initialized_store(
        _Guard(events),
        session_factory=lambda: (_ for _ in ()).throw(AssertionError("session constructed")),
    )
    client = _Client(events, content, put_error=put_error)

    @asynccontextmanager
    async def fake_client() -> Any:
        yield client

    monkeypatch.setattr(store, "_client", fake_client)
    async with minted_source(tmp_path / type(put_error).__name__, content) as source:
        result = await store.put(source)

    assert result.replayed is True
    assert events.count("put_object") == 1
    assert events.count("head_object") == 2
    assert events.count("get_object") == 1
    _assert_same_activation_immediately_precedes_sdk_calls(events, fingerprint)


@pytest.mark.asyncio
async def test_observe_put_result_reuses_one_activation_across_head_and_exact_read(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    content = b"observed provider bytes"
    events: list[object] = []
    store, fingerprint = _initialized_store(
        _Guard(events),
        session_factory=lambda: (_ for _ in ()).throw(AssertionError("session constructed")),
    )
    client = _Client(events, content)

    @asynccontextmanager
    async def fake_client() -> Any:
        yield client

    monkeypatch.setattr(store, "_client", fake_client)
    async with minted_source(tmp_path / "observe", content) as source:
        observation = await store.observe_put_result(source.commitment)

    assert observation.committed is True
    assert events.count("head_object") == 2
    assert events.count("get_object") == 1
    _assert_same_activation_immediately_precedes_sdk_calls(events, fingerprint)


def test_sts_assumed_role_binding_requires_exact_partition_account_and_role_name() -> None:
    expected = "arn:aws:iam::123456789012:role/path/workstream-runtime"
    assert (
        _canonical_observed_role_arn(
            "arn:aws:sts::123456789012:assumed-role/workstream-runtime/session",
            expected,
        )
        == expected
    )
    assert (
        _canonical_observed_role_arn(
            "arn:aws:sts::999999999999:assumed-role/workstream-runtime/session",
            expected,
        )
        != expected
    )
    assert (
        _canonical_observed_role_arn(
            "arn:aws:sts::123456789012:assumed-role/other/session",
            expected,
        )
        != expected
    )


def test_proof_transport_is_not_imported_by_product_or_store_composition() -> None:
    root = Path(__file__).parents[1] / "app"
    consumers = [
        root / "adapters" / "artifacts" / "__init__.py",
        root / "adapters" / "artifacts" / "internal_workers.py",
        root / "main.py",
        root / "modules" / "artifacts" / "service.py",
    ]
    assert all("aws_live_proof" not in path.read_text(encoding="utf-8") for path in consumers)


def test_direct_read_owners_use_the_shared_artifact_store_port() -> None:
    root = Path(__file__).parents[1] / "app" / "modules" / "artifacts"
    consumers = [
        root / "guide_document_access.py",
        root / "post_submit_materialization.py",
        root / "task_guide_documents.py",
        root / "task_import_sources.py",
    ]
    for path in consumers:
        source = path.read_text(encoding="utf-8")
        assert ".open(" in source
        assert "s3_compatible" not in source
        assert "aws_live_proof" not in source
