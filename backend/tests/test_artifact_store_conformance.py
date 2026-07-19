"""Provider-neutral ArtifactStore v2 conformance vectors."""

from __future__ import annotations

import asyncio
from dataclasses import FrozenInstanceError
import hashlib
import inspect
from pathlib import Path

import pytest

from app.interfaces.artifacts import (
    ArtifactByteRange,
    ArtifactObjectHead,
    ArtifactObjectMissingError,
    ArtifactPutObservation,
    ArtifactPutResult,
    ArtifactRangeInvalidError,
    ArtifactStore,
    ArtifactStoreNamespaceClaim,
    ArtifactStoreNamespaceIdentity,
)
from app.interfaces.external_services import ExternalServiceAdapterIdentity
from tests.artifact_store_helpers import (
    initialize_local_store,
    minted_source,
)


class ArtifactStoreConformanceTests:
    """Reusable v2 vectors for LocalStorage and later provider adapters."""

    expected_identity: ExternalServiceAdapterIdentity

    def make_store(self, root: Path) -> ArtifactStore:
        """Construct the provider under test."""
        raise NotImplementedError

    @staticmethod
    def close_store(store: ArtifactStore) -> None:
        """Release optional provider resources after one vector."""
        close = getattr(store, "close", None)
        if close is not None:
            close()

    @pytest.mark.asyncio
    async def test_identity_and_exact_public_surface(self, tmp_path: Path) -> None:
        """Expose only shared identity and the four ArtifactStore v2 operations."""
        store = self.make_store(tmp_path / "store")
        try:
            assert store.identity == self.expected_identity
            public = {
                name
                for name in dir(store)
                if not name.startswith("_") and name not in {"close"}
            }
            assert public == {"head", "identity", "observe_put_result", "open", "put"}
            for removed in (
                "store",
                "recover_committed_store",
                "stat",
                "verify",
                "retain",
                "release",
                "get_operation_receipt",
            ):
                assert not hasattr(store, removed)
        finally:
            self.close_store(store)

    @pytest.mark.asyncio
    async def test_put_head_observe_and_full_open(self, tmp_path: Path) -> None:
        """Publish exact bytes and expose bounded provider-neutral facts."""
        store = self.make_store(tmp_path / "store")
        content = b"hello"
        expected_digest = hashlib.sha256(content).hexdigest()
        try:
            async with minted_source(
                tmp_path / "scratch",
                b"hel",
                b"lo",
                media_type="text/plain",
            ) as source:
                commitment = source.commitment
                result = await store.put(source)
            assert result == ArtifactPutResult(
                f"sha256/{expected_digest[:2]}/{expected_digest[2:]}",
                replayed=False,
            )
            head = await store.head(result.provider_object_ref)
            assert head.exists is True
            assert head.byte_count == len(content)
            assert head.media_type is None
            assert await store.observe_put_result(commitment) == ArtifactPutObservation(
                result.provider_object_ref,
                committed=True,
            )
            chunks = [chunk async for chunk in store.open(result.provider_object_ref)]
            assert b"".join(chunks) == content
            assert all(0 < len(chunk) <= 2 for chunk in chunks)
        finally:
            self.close_store(store)

    @pytest.mark.asyncio
    async def test_exact_replay_returns_same_reference_without_overwrite(
        self,
        tmp_path: Path,
    ) -> None:
        """Verify all existing bytes before accepting a commitment replay."""
        store = self.make_store(tmp_path / "store")
        try:
            async with minted_source(tmp_path / "scratch-a", b"replay") as first_source:
                first = await store.put(first_source)
            async with minted_source(tmp_path / "scratch-b", b"re", b"play") as replay_source:
                replay = await store.put(replay_source)
            assert replay.provider_object_ref == first.provider_object_ref
            assert first.replayed is False
            assert replay.replayed is True
            assert b"".join(
                [chunk async for chunk in store.open(first.provider_object_ref)]
            ) == b"replay"
        finally:
            self.close_store(store)

    @pytest.mark.asyncio
    async def test_concurrent_identical_puts_publish_once(self, tmp_path: Path) -> None:
        """Allow one immutable publication and return one exact replay."""
        first_store = self.make_store(tmp_path / "store")
        second_store = self.make_store(tmp_path / "store")
        try:
            async with minted_source(
                tmp_path / "scratch-a",
                b"same bytes",
                media_type="text/plain",
            ) as first_source:
                async with minted_source(
                    tmp_path / "scratch-b",
                    b"same ",
                    b"bytes",
                    media_type="text/plain",
                ) as second_source:
                    first, second = await asyncio.gather(
                        first_store.put(first_source),
                        second_store.put(second_source),
                    )
            assert first.provider_object_ref == second.provider_object_ref
            assert sorted((first.replayed, second.replayed)) == [False, True]
        finally:
            self.close_store(first_store)
            self.close_store(second_store)

    @pytest.mark.asyncio
    async def test_missing_head_observation_and_open(self, tmp_path: Path) -> None:
        """Distinguish safe absence from operations that require existing bytes."""
        store = self.make_store(tmp_path / "store")
        try:
            async with minted_source(tmp_path / "scratch", b"absent") as source:
                commitment = source.commitment
                provider_object_ref = (
                    f"sha256/{commitment.sha256[7:9]}/{commitment.sha256[9:]}"
                )
                assert (await store.head(provider_object_ref)).exists is False
                assert await store.observe_put_result(commitment) == ArtifactPutObservation(
                    provider_object_ref,
                    committed=False,
                )
                with pytest.raises(ArtifactObjectMissingError):
                    _ = [chunk async for chunk in store.open(provider_object_ref)]
        finally:
            self.close_store(store)

    @pytest.mark.asyncio
    async def test_ranges_cover_zero_eof_and_invalid_offsets(self, tmp_path: Path) -> None:
        """Apply zero-based exclusive-end range semantics exactly."""
        store = self.make_store(tmp_path / "store")
        try:
            async with minted_source(tmp_path / "scratch", b"abcdef") as source:
                result = await store.put(source)

            async def read(selected: ArtifactByteRange) -> bytes:
                return b"".join(
                    [chunk async for chunk in store.open(result.provider_object_ref, selected)]
                )

            assert await read(ArtifactByteRange(offset=2, length=3)) == b"cde"
            assert await read(ArtifactByteRange(offset=4)) == b"ef"
            assert await read(ArtifactByteRange(offset=1, length=99)) == b"bcdef"
            assert await read(ArtifactByteRange(offset=0, length=0)) == b""
            assert await read(ArtifactByteRange(offset=6)) == b""
            assert await read(ArtifactByteRange(offset=6, length=1)) == b""
            with pytest.raises(ArtifactRangeInvalidError):
                await read(ArtifactByteRange(offset=7))
        finally:
            self.close_store(store)

    @pytest.mark.asyncio
    async def test_empty_object_is_present_and_readable(self, tmp_path: Path) -> None:
        """Keep a committed zero-byte object distinct from a missing object."""
        store = self.make_store(tmp_path / "store")
        try:
            async with minted_source(tmp_path / "scratch", b"") as source:
                result = await store.put(source)
                commitment = source.commitment
            assert (await store.head(result.provider_object_ref)).byte_count == 0
            assert await store.observe_put_result(commitment) == ArtifactPutObservation(
                result.provider_object_ref,
                committed=True,
            )
            assert [chunk async for chunk in store.open(result.provider_object_ref)] == []
        finally:
            self.close_store(store)


class TestLocalArtifactStoreConformance(ArtifactStoreConformanceTests):
    """Run the shared v2 contract against LocalStorage."""

    expected_identity = ExternalServiceAdapterIdentity("artifact_store", "local")

    def make_store(self, root: Path) -> ArtifactStore:
        """Construct one small-buffer local provider."""
        return initialize_local_store(root, buffer_bytes=2)


def test_v2_value_types_are_immutable_and_range_values_are_exact() -> None:
    """Reject mutation, booleans, negative values, and ambiguous missing heads."""
    result = ArtifactPutResult("sha256/00/" + "0" * 62, replayed=False)
    with pytest.raises(FrozenInstanceError):
        result.replayed = True  # type: ignore[misc]
    for kwargs in ({"offset": True}, {"offset": -1}, {"length": True}, {"length": -1}):
        with pytest.raises(ValueError):
            ArtifactByteRange(**kwargs)  # type: ignore[arg-type]
    for provider_ref in ("", "x" * 1025, "sha256/00/" + "0" * 61 + "\n", 7):
        with pytest.raises(ValueError, match="provider object reference"):
            ArtifactPutResult(provider_ref, replayed=False)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="replay observation"):
        ArtifactPutResult("sha256/00/" + "0" * 62, replayed=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="put observation"):
        ArtifactPutObservation("sha256/00/" + "0" * 62, committed=1)  # type: ignore[arg-type]


def test_namespace_startup_values_are_closed_and_immutable() -> None:
    """Reject malformed provider descriptors and namespace admission proofs."""
    identity = ArtifactStoreNamespaceIdentity(
        provider_profile="local-v2",
        descriptor_items=(
            ("private_prefix", "objects/sha256"),
            ("private_root_identity", "sha256:" + "0" * 64),
        ),
    )
    claim = ArtifactStoreNamespaceClaim(
        adapter_identity=ExternalServiceAdapterIdentity("artifact_store", "local"),
        namespace_identity=identity,
        namespace_fingerprint="sha256:" + "0" * 64,
    )
    with pytest.raises(FrozenInstanceError):
        claim.namespace_fingerprint = "sha256:" + "1" * 64  # type: ignore[misc]
    assert identity.as_dict() == {
        "private_prefix": "objects/sha256",
        "private_root_identity": "sha256:" + "0" * 64,
    }
    for profile, items in (
        (
            "minio-v1",
            (
                ("addressing_style", "path"),
                ("bucket", "workstream-artifacts"),
                ("endpoint_identity", "sha256:" + "1" * 64),
                ("private_prefix", "workstream/artifacts"),
                ("region", "us-east-1"),
            ),
        ),
        (
            "aws-s3-v1",
            (
                ("addressing_style", "virtual"),
                ("bucket", "workstream-artifacts"),
                ("private_prefix", "workstream/artifacts"),
                ("region", "us-east-1"),
            ),
        ),
    ):
        assert ArtifactStoreNamespaceIdentity(profile, items).as_dict() == dict(items)

    for profile, items in (
        ("", (("private_prefix", "objects/sha256"),)),
        ("local-v2", (("z", "1"), ("a", "2"))),
        ("local-v2", (("a", "1"), ("a", "2"))),
        ("local-v2", (("", "1"),)),
        ("local-v2", (("backend", "local"),)),
        ("local-v2", (("private_prefix", "objects/sha256"),)),
        (
            "local-v2",
            (
                ("private_prefix", "objects/sha256"),
                ("private_root_identity", "sha256:" + "0" * 64),
                ("unknown", "value"),
            ),
        ),
        (
            "unknown-v1",
            (
                ("private_prefix", "objects/sha256"),
                ("private_root_identity", "sha256:" + "0" * 64),
            ),
        ),
        (
            "minio-v1",
            (
                ("addressing_style", "path"),
                ("bucket", "workstream-artifacts"),
                ("private_prefix", "workstream/artifacts"),
                ("region", "us-east-1"),
            ),
        ),
        (
            "aws-s3-v1",
            (
                ("addressing_style", "virtual"),
                ("bucket", "workstream-artifacts"),
                ("endpoint_identity", "sha256:" + "1" * 64),
                ("private_prefix", "workstream/artifacts"),
                ("region", "us-east-1"),
            ),
        ),
        (
            "minio-v1",
            (
                ("addressing_style", "path"),
                ("bucket", "Bad..Bucket"),
                ("endpoint_identity", "sha256:" + "1" * 64),
                ("private_prefix", "workstream/artifacts"),
                ("region", "us-east-1"),
            ),
        ),
        (
            "aws-s3-v1",
            (
                ("addressing_style", "virtual"),
                ("bucket", "workstream-artifacts"),
                ("private_prefix", "../bad//prefix"),
                ("region", "us-east-1"),
            ),
        ),
    ):
        with pytest.raises(ValueError):
            ArtifactStoreNamespaceIdentity(profile, items)
    with pytest.raises(ValueError, match="not immutable"):
        ArtifactStoreNamespaceIdentity(
            "local-v2",
            [  # type: ignore[arg-type]
                ("private_prefix", "objects/sha256"),
                ("private_root_identity", "sha256:" + "0" * 64),
            ],
        )
    for kwargs in (
        {"adapter_identity": object()},
        {"namespace_identity": object()},
        {"namespace_fingerprint": "sha256:bad"},
        {"namespace_fingerprint": "sha256:" + "G" * 64},
    ):
        values = {
            "adapter_identity": claim.adapter_identity,
            "namespace_identity": identity,
            "namespace_fingerprint": claim.namespace_fingerprint,
            **kwargs,
        }
        with pytest.raises(ValueError):
            ArtifactStoreNamespaceClaim(**values)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="existence observation"):
        ArtifactObjectHead("sha256/00/" + "0" * 62, exists=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="exact byte count"):
        ArtifactObjectHead("sha256/00/" + "0" * 62, exists=True)
    with pytest.raises(ValueError, match="cannot contain"):
        ArtifactObjectHead(
            "sha256/00/" + "0" * 62,
            exists=False,
            media_type="text/plain",
        )
    with pytest.raises(ValueError, match="media type"):
        ArtifactObjectHead(
            "sha256/00/" + "0" * 62,
            exists=True,
            byte_count=1,
            media_type="bad\nmedia",
        )


def test_artifact_store_protocol_declares_only_v2_operations() -> None:
    """Prevent v1 operation or receipt methods from returning to the port."""
    methods = {
        name
        for name, value in inspect.getmembers(ArtifactStore)
        if not name.startswith("_") and (inspect.isfunction(value) or isinstance(value, property))
    }
    assert methods == {"head", "identity", "observe_put_result", "open", "put"}
