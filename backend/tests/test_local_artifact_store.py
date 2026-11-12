"""Filesystem, cancellation, and security proof for LocalStorage v2."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from pathlib import Path
import threading
from typing import cast

import pytest

from app.adapters.artifacts.local import LocalStorageAdapter, LocalStorageBootstrap
from app.interfaces.artifacts import (
    ArtifactByteRange,
    ArtifactConfigurationError,
    ArtifactInputMismatchError,
    ArtifactIntegrityError,
    ArtifactOperationConflictError,
    ArtifactStoreUnavailableError,
    ArtifactStoreNamespaceClaim,
    artifact_provider_object_ref,
    parse_artifact_provider_object_ref,
)
from app.modules.artifacts.sources import ArtifactCommitment, CommittedArtifactSource
from tests.artifact_store_helpers import (
    initialize_local_store,
    local_namespace_claim,
    minted_source,
)


def object_path(root: Path, provider_object_ref: str) -> Path:
    """Resolve a test-only local provider reference inside its private root."""
    return root / "objects" / provider_object_ref


def test_local_layout_is_private_content_derived_and_v2_only(tmp_path: Path) -> None:
    """Persist one private content path without v1 metadata or product identity."""

    async def exercise() -> str:
        root = tmp_path / "artifacts"
        adapter = initialize_local_store(root=root, buffer_bytes=2)
        try:
            async with minted_source(tmp_path / "scratch", b"private bytes") as source:
                return (await adapter.put(source)).provider_object_ref
        finally:
            adapter.close()

    provider_object_ref = asyncio.run(exercise())
    digest = hashlib.sha256(b"private bytes").hexdigest()
    root = tmp_path / "artifacts"
    assert provider_object_ref == f"sha256/{digest[:2]}/{digest[2:]}"
    assert object_path(root, provider_object_ref).read_bytes() == b"private bytes"
    assert (root.stat().st_mode & 0o777) == 0o700
    assert (object_path(root, provider_object_ref).stat().st_mode & 0o777) == 0o400
    assert set(path.name for path in root.iterdir()) == {
        ".workstream-artifact-store-v2",
        "locks",
        "objects",
        "tmp",
    }
    assert not {"intents", "metadata", "receipts", "retentions", "quarantine"} & {
        path.name for path in root.iterdir()
    }
    assert "private" not in provider_object_ref


def test_local_layout_initialization_serializes_and_publishes_marker_atomically(
    tmp_path: Path,
) -> None:
    """Allow concurrent bootstrap only after one complete marker is durable."""
    root = tmp_path / "artifacts"
    root.mkdir(mode=0o700)
    bootstraps = [
        LocalStorageBootstrap(LocalStorageAdapter(root=root)),
        LocalStorageBootstrap(LocalStorageAdapter(root=root)),
    ]
    claims = [local_namespace_claim(bootstrap) for bootstrap in bootstraps]

    def initialize(index: int) -> None:
        bootstraps[index].initialize_after_namespace_claim(claims[index])

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(initialize, index) for index in range(2)]
            for future in futures:
                future.result(timeout=5)
    finally:
        for bootstrap in bootstraps:
            bootstrap.close()

    assert (root / ".workstream-artifact-store-v2").read_bytes() == (
        b"workstream-artifact-store-v2\n"
    )
    assert not (root / ".workstream-artifact-store-v2.initializing").exists()


def test_local_recovers_only_one_complete_durable_marker_temporary(
    tmp_path: Path,
) -> None:
    """Finish an interrupted atomic rename only for exact marker bytes."""
    root = tmp_path / "artifacts"
    root.mkdir(mode=0o700)
    temporary = root / ".workstream-artifact-store-v2.initializing"
    temporary.write_bytes(b"workstream-artifact-store-v2\n")
    temporary.chmod(0o600)

    adapter = initialize_local_store(root=root)
    adapter.close()

    assert (root / ".workstream-artifact-store-v2").read_bytes() == (
        b"workstream-artifact-store-v2\n"
    )
    assert not temporary.exists()


def test_local_recovers_linked_marker_after_interrupted_temporary_unlink(
    tmp_path: Path,
) -> None:
    """Reduce the exact two-link crash state back to one canonical marker."""
    root = tmp_path / "artifacts"
    root.mkdir(mode=0o700)
    temporary = root / ".workstream-artifact-store-v2.initializing"
    marker = root / ".workstream-artifact-store-v2"
    temporary.write_bytes(b"workstream-artifact-store-v2\n")
    temporary.chmod(0o600)
    os.link(temporary, marker)
    assert temporary.stat().st_ino == marker.stat().st_ino
    assert temporary.stat().st_nlink == 2

    adapter = initialize_local_store(root=root)
    adapter.close()

    assert marker.read_bytes() == b"workstream-artifact-store-v2\n"
    assert marker.stat().st_nlink == 1
    assert not temporary.exists()


def test_local_refuses_v1_or_unknown_disk_layout(tmp_path: Path) -> None:
    """Do not install a dual reader over an incompatible pre-cutover root."""
    root = tmp_path / "artifacts"
    root.mkdir(mode=0o700)
    (root / "intents").mkdir(mode=0o700)
    with pytest.raises(ArtifactConfigurationError, match="layout is incompatible"):
        initialize_local_store(root=root)

    marker_root = tmp_path / "bad-marker"
    marker_root.mkdir(mode=0o700)
    marker = marker_root / ".workstream-artifact-store-v2"
    marker.write_bytes(b"wrong\n")
    marker.chmod(0o600)
    with pytest.raises(ArtifactConfigurationError, match="layout is incompatible"):
        initialize_local_store(root=marker_root)

    executable_marker_root = tmp_path / "executable-marker"
    executable_marker_root.mkdir(mode=0o700)
    executable_marker = executable_marker_root / ".workstream-artifact-store-v2"
    executable_marker.write_bytes(b"workstream-artifact-store-v2\n")
    executable_marker.chmod(0o700)
    with pytest.raises(ArtifactConfigurationError, match="layout is incompatible"):
        initialize_local_store(root=executable_marker_root)

    for index, relative_path in enumerate(
        (
            "legacy",
            "objects/legacy",
            "objects/sha256/zz",
            "objects/sha256/aa/not-an-object",
            "tmp/not-a-temporary",
            "locks/not-a-lock",
        )
    ):
        extra_entry_root = tmp_path / f"extra-entry-{index}"
        initialized = initialize_local_store(root=extra_entry_root)
        initialized.close()
        extra_entry = extra_entry_root / relative_path
        extra_entry.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if "not-" in extra_entry.name:
            extra_entry.write_bytes(b"foreign")
            extra_entry.chmod(0o600)
        else:
            extra_entry.mkdir(mode=0o700)
        with pytest.raises(ArtifactConfigurationError, match="layout is incompatible"):
            initialize_local_store(root=extra_entry_root)


def test_local_sanitizes_root_initialization_oserror(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = str(tmp_path / "secret")

    def fail(_self: object, _root: Path) -> None:
        raise OSError(secret)

    monkeypatch.setattr(LocalStorageAdapter, "_open_root", fail)
    with pytest.raises(ArtifactConfigurationError) as raised:
        LocalStorageAdapter(root=tmp_path / "artifacts")
    assert secret not in str(raised.value)
    assert raised.value.__cause__ is None


def test_local_rejects_symlink_and_nonprivate_roots(tmp_path: Path) -> None:
    """Pin only a dedicated owner-private, no-follow root directory."""
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    linked = tmp_path / "linked"
    linked.symlink_to(target, target_is_directory=True)
    with pytest.raises(ArtifactConfigurationError, match="root is unsafe"):
        LocalStorageAdapter(root=linked)

    public = tmp_path / "public"
    public.mkdir(mode=0o755)
    with pytest.raises(ArtifactConfigurationError, match="directory is unsafe"):
        LocalStorageAdapter(root=public)


def test_local_rejects_root_and_files_not_owned_by_runtime_user(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Apply the canonical scratch ownership rule to every local descriptor."""
    root = tmp_path / "artifacts"
    root.mkdir(mode=0o700)
    regular = tmp_path / "object"
    regular.write_bytes(b"bytes")
    regular.chmod(0o600)
    regular_descriptor = os.open(regular, os.O_RDONLY)
    actual_euid = os.geteuid()
    monkeypatch.setattr(os, "geteuid", lambda: actual_euid + 1)
    try:
        with pytest.raises(ArtifactConfigurationError, match="directory is unsafe"):
            LocalStorageAdapter(root=root)
        with pytest.raises(ArtifactIntegrityError, match="object is unsafe"):
            LocalStorageAdapter._assert_private_regular(regular_descriptor)
        with pytest.raises(ArtifactIntegrityError, match="object is unsafe"):
            LocalStorageAdapter._assert_recoverable_object(regular_descriptor)
    finally:
        os.close(regular_descriptor)


@pytest.mark.parametrize("buffer_bytes", [True, 0, -1, 1024 * 1024 + 1, 1.5])
def test_local_rejects_invalid_buffer_configuration(
    tmp_path: Path,
    buffer_bytes: object,
) -> None:
    with pytest.raises(ValueError, match="artifact buffer"):
        LocalStorageAdapter(
            root=tmp_path / "artifacts",
            buffer_bytes=buffer_bytes,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("timeout", [True, 0, -1, float("inf"), "1"])
def test_local_rejects_invalid_lock_timeout(tmp_path: Path, timeout: object) -> None:
    with pytest.raises(ValueError, match="lock timeout"):
        LocalStorageAdapter(
            root=tmp_path / "artifacts",
            lock_timeout_seconds=timeout,  # type: ignore[arg-type]
        )


def test_local_requires_claim_and_rejects_same_path_replacement_before_mutation(
    tmp_path: Path,
) -> None:
    """Bind layout mutation to the root descriptor admitted by PostgreSQL."""
    root = tmp_path / "artifacts"
    root.mkdir(mode=0o700)
    bootstrap = LocalStorageBootstrap(LocalStorageAdapter(root=root))
    claim = local_namespace_claim(bootstrap)

    with pytest.raises(ArtifactConfigurationError, match="namespace is not initialized"):
        asyncio.run(bootstrap._adapter.head("sha256/00/" + "0" * 62))

    original = tmp_path / "original-artifacts"
    root.rename(original)
    root.mkdir(mode=0o700)
    with pytest.raises(ArtifactConfigurationError, match="root changed"):
        bootstrap.initialize_after_namespace_claim(claim)

    assert list(root.iterdir()) == []
    assert list(original.iterdir()) == []


def test_local_rejects_nonmatching_namespace_claim_before_layout_mutation(
    tmp_path: Path,
) -> None:
    """Do not accept a proof for any fingerprint other than this root."""
    root = tmp_path / "artifacts"
    root.mkdir(mode=0o700)
    bootstrap = LocalStorageBootstrap(LocalStorageAdapter(root=root))
    claim = local_namespace_claim(bootstrap)
    mismatched = ArtifactStoreNamespaceClaim(
        adapter_identity=claim.adapter_identity,
        namespace_identity=claim.namespace_identity,
        namespace_fingerprint="sha256:" + "f" * 64,
    )

    with pytest.raises(ArtifactConfigurationError, match="claim does not match"):
        bootstrap.initialize_after_namespace_claim(mismatched)

    assert list(root.iterdir()) == []
    assert bootstrap._adapter._root_fd == -1


def test_local_closes_after_repeated_initialization_attempt(tmp_path: Path) -> None:
    """A repeated bootstrap call fails closed instead of retaining descriptors."""
    root = tmp_path / "artifacts"
    root.mkdir(mode=0o700)
    bootstrap = LocalStorageBootstrap(LocalStorageAdapter(root=root))
    claim = local_namespace_claim(bootstrap)
    bootstrap.initialize_after_namespace_claim(claim)

    with pytest.raises(ArtifactConfigurationError, match="already initialized"):
        bootstrap.initialize_after_namespace_claim(claim)

    assert bootstrap._adapter._root_fd == -1


def test_local_closes_pinned_descriptors_after_integrity_failure(tmp_path: Path) -> None:
    """Release bootstrap ownership after any sanitized store initialization error."""
    root = tmp_path / "artifacts"
    root.mkdir(mode=0o700)
    marker = root / ".workstream-artifact-store-v2"
    marker.write_bytes(b"workstream-artifact-store-v2\n")
    marker.chmod(0o644)
    bootstrap = LocalStorageBootstrap(LocalStorageAdapter(root=root))
    claim = local_namespace_claim(bootstrap)

    with pytest.raises(ArtifactIntegrityError, match="object is unsafe"):
        bootstrap.initialize_after_namespace_claim(claim)

    assert bootstrap._adapter._root_fd == -1


def test_local_reopens_one_valid_populated_layout(tmp_path: Path) -> None:
    """Accept canonical immutable objects and persistent digest locks on restart."""

    async def publish(root: Path) -> str:
        adapter = initialize_local_store(root=root, buffer_bytes=2)
        try:
            async with minted_source(tmp_path / "scratch", b"restart-safe") as source:
                return (await adapter.put(source)).provider_object_ref
        finally:
            adapter.close()

    root = tmp_path / "populated"
    provider_object_ref = asyncio.run(publish(root))
    reopened = initialize_local_store(root=root)
    try:
        assert asyncio.run(reopened.head(provider_object_ref)).exists is True
    finally:
        reopened.close()


@pytest.mark.parametrize("mode", [0o600, 0o400])
def test_local_startup_fails_closed_for_orphan_provider_temporary(
    tmp_path: Path,
    mode: int,
) -> None:
    """Require explicit cleanup instead of deleting a possibly live provider temp."""
    root = tmp_path / f"orphan-{mode:o}"
    initialized = initialize_local_store(root=root)
    initialized.close()
    orphan = root / "tmp" / (".put." + "a" * 32 + ".tmp")
    orphan.write_bytes(b"unpublished")
    orphan.chmod(mode)

    with pytest.raises(
        ArtifactConfigurationError,
        match="startup requires orphan temporary cleanup",
    ):
        initialize_local_store(root=root)

    assert orphan.read_bytes() == b"unpublished"


@pytest.mark.asyncio
async def test_v2_operations_reject_unsealed_or_malformed_values(tmp_path: Path) -> None:
    adapter = initialize_local_store(root=tmp_path / "artifacts")
    try:
        with pytest.raises(ArtifactInputMismatchError, match="not sealed"):
            await adapter.put(cast(CommittedArtifactSource, object()))
        with pytest.raises(ArtifactOperationConflictError, match="commitment"):
            await adapter.observe_put_result(cast(ArtifactCommitment, object()))
        with pytest.raises(ArtifactOperationConflictError, match="byte range"):
            adapter.open("sha256/00/" + "0" * 62, cast(ArtifactByteRange, object()))
        with pytest.raises(ArtifactOperationConflictError, match="provider reference"):
            await adapter.head(cast(str, 7))
        with pytest.raises(ArtifactOperationConflictError, match="commitment"):
            adapter._acquire_lock("not-a-digest")
    finally:
        adapter.close()


@pytest.mark.asyncio
async def test_exact_replay_rejects_corrupt_existing_bytes_without_overwrite(
    tmp_path: Path,
) -> None:
    """Treat a pre-existing deterministic path as untrusted until fully hashed."""
    root = tmp_path / "artifacts"
    adapter = initialize_local_store(root=root, buffer_bytes=2)
    try:
        async with minted_source(tmp_path / "scratch", b"expected") as source:
            commitment = source.commitment
            provider_object_ref = (
                f"sha256/{commitment.sha256[7:9]}/{commitment.sha256[9:]}"
            )
            target = object_path(root, provider_object_ref)
            target.parent.mkdir(mode=0o700)
            target.write_bytes(b"corrupt!")
            os.chmod(target, 0o400)
            with pytest.raises(ArtifactIntegrityError, match="violates commitment"):
                await adapter.put(source)
            assert target.read_bytes() == b"corrupt!"
    finally:
        adapter.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("replacement", ["symlink", "directory", "public_file"])
async def test_head_rejects_symlink_nonregular_and_nonprivate_objects(
    tmp_path: Path,
    replacement: str,
) -> None:
    """Fail closed when private immutable object invariants are violated."""
    root = tmp_path / replacement
    adapter = initialize_local_store(root=root, buffer_bytes=2)
    try:
        async with minted_source(tmp_path / f"scratch-{replacement}", b"object") as source:
            result = await adapter.put(source)
        target = object_path(root, result.provider_object_ref)
        target.unlink()
        if replacement == "symlink":
            outside = tmp_path / "secret"
            outside.write_bytes(b"do not read")
            target.symlink_to(outside)
        elif replacement == "directory":
            target.mkdir(mode=0o700)
        else:
            target.write_bytes(b"object")
            os.chmod(target, 0o644)
        with pytest.raises(ArtifactIntegrityError):
            await adapter.head(result.provider_object_ref)
    finally:
        adapter.close()


@pytest.mark.asyncio
async def test_put_rejects_symlink_digest_directory(tmp_path: Path) -> None:
    """Never follow an attacker-controlled digest-prefix directory."""
    root = tmp_path / "artifacts"
    adapter = initialize_local_store(root=root, buffer_bytes=2)
    try:
        async with minted_source(tmp_path / "scratch", b"prefix") as source:
            prefix = source.commitment.sha256[7:9]
            outside = tmp_path / "outside"
            outside.mkdir(mode=0o700)
            (root / "objects" / "sha256" / prefix).symlink_to(
                outside,
                target_is_directory=True,
            )
            with pytest.raises(ArtifactIntegrityError):
                await adapter.put(source)
            assert list(outside.iterdir()) == []
    finally:
        adapter.close()


@pytest.mark.asyncio
async def test_provider_failures_are_sanitized_without_paths_or_causes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Do not retain raw provider path details in stable adapter failures."""
    root = tmp_path / "private-secret-root"
    adapter = initialize_local_store(root=root)
    provider_object_ref = "sha256/00/" + "0" * 62

    def fail(_: str) -> int:
        raise OSError(f"permission denied: {root}/credential-value")

    monkeypatch.setattr(adapter, "_head_object", fail)
    try:
        with pytest.raises(ArtifactStoreUnavailableError) as raised:
            await adapter.head(provider_object_ref)
        assert str(root) not in str(raised.value)
        assert "credential-value" not in str(raised.value)
        assert raised.value.__cause__ is None
    finally:
        adapter.close()


@pytest.mark.asyncio
async def test_put_and_open_map_raw_oserrors_to_sanitized_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = initialize_local_store(root=tmp_path / "artifacts")

    async def fail_lock(_digest: str) -> tuple[object, int]:
        raise OSError("secret lock path")

    monkeypatch.setattr(adapter, "_acquire_lock_async", fail_lock)
    try:
        async with minted_source(tmp_path / "scratch", b"put") as source:
            with pytest.raises(ArtifactStoreUnavailableError) as put_error:
                await adapter.put(source)
        assert put_error.value.__cause__ is None

        async def fail_open(_provider_ref: str) -> tuple[int, int]:
            raise OSError("secret object path")

        monkeypatch.setattr(adapter, "_open_object_async", fail_open)
        with pytest.raises(ArtifactStoreUnavailableError) as open_error:
            _ = [
                chunk
                async for chunk in adapter.open("sha256/00/" + "0" * 62)
            ]
        assert open_error.value.__cause__ is None
    finally:
        adapter.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stream_values",
    [("not-bytes",), (b"too-long",), (b"changed",)],
)
async def test_put_defends_against_broken_sealed_source_streams(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stream_values: tuple[object, ...],
) -> None:
    adapter = initialize_local_store(root=tmp_path / "artifacts", buffer_bytes=2)
    try:
        async with minted_source(tmp_path / "scratch", b"content") as source:
            async def broken_stream(_self: CommittedArtifactSource) -> AsyncIterator[object]:
                for value in stream_values:
                    yield value

            monkeypatch.setattr(CommittedArtifactSource, "stream", broken_stream)
            with pytest.raises(ArtifactInputMismatchError):
                await adapter.put(source)
    finally:
        adapter.close()


@pytest.mark.asyncio
async def test_put_handles_exclusive_publication_race_as_exact_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = initialize_local_store(root=tmp_path / "artifacts", buffer_bytes=2)
    original_publish = adapter._publish_exclusive

    def publish_then_report_race(temporary_name: str, provider_ref: str) -> bool:
        assert original_publish(temporary_name, provider_ref) is True
        return False

    monkeypatch.setattr(adapter, "_publish_exclusive", publish_then_report_race)
    try:
        async with minted_source(tmp_path / "scratch", b"race") as source:
            result = await adapter.put(source)
        assert result.replayed is True
    finally:
        adapter.close()


@pytest.mark.asyncio
async def test_head_recovers_crash_after_link_before_temporary_unlink(
    tmp_path: Path,
) -> None:
    """Repair the only valid two-link state while owning the digest lock."""
    root = tmp_path / "artifacts"
    adapter = initialize_local_store(root=root, buffer_bytes=2)
    try:
        async with minted_source(tmp_path / "scratch", b"crash recovery") as source:
            commitment = source.commitment
            provider_ref = artifact_provider_object_ref(commitment)
            descriptor, temporary_name = adapter._create_temporary()
            try:
                adapter._write_all(descriptor, memoryview(b"crash recovery"))
                adapter._seal_temporary(descriptor)
                prefix, filename = parse_artifact_provider_object_ref(provider_ref)
                prefix_fd = adapter._open_prefix(prefix, create=True)
                try:
                    os.link(
                        temporary_name,
                        filename,
                        src_dir_fd=adapter._tmp_fd,
                        dst_dir_fd=prefix_fd,
                        follow_symlinks=False,
                    )
                    os.fsync(prefix_fd)
                finally:
                    os.close(prefix_fd)
            finally:
                os.close(descriptor)

            target = object_path(root, provider_ref)
            assert target.stat().st_nlink == 2
            assert [path.name for path in (root / "tmp").iterdir()] == [temporary_name]

            observed = await adapter.head(provider_ref)

            assert observed.exists is True
            assert observed.byte_count == len(b"crash recovery")
            assert target.stat().st_nlink == 1
            assert list((root / "tmp").iterdir()) == []
            assert b"".join([chunk async for chunk in adapter.open(provider_ref)]) == b"crash recovery"
    finally:
        adapter.close()


@pytest.mark.asyncio
async def test_head_rejects_unowned_second_hard_link(tmp_path: Path) -> None:
    """Never treat an arbitrary external hard link as interrupted publication."""
    root = tmp_path / "artifacts"
    adapter = initialize_local_store(root=root)
    try:
        async with minted_source(tmp_path / "scratch", b"linked") as source:
            result = await adapter.put(source)
        target = object_path(root, result.provider_object_ref)
        outside_link = tmp_path / "unowned-link"
        os.link(target, outside_link)

        with pytest.raises(ArtifactIntegrityError, match="ambiguous"):
            await adapter.head(result.provider_object_ref)
    finally:
        adapter.close()


@pytest.mark.asyncio
async def test_new_digest_prefix_is_fsynced_before_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persist the new digest-directory entry before acknowledging publication."""
    adapter = initialize_local_store(root=tmp_path / "artifacts")
    fsynced: list[int] = []
    original_fsync = os.fsync

    def record_fsync(descriptor: int) -> None:
        fsynced.append(descriptor)
        original_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", record_fsync)
    try:
        async with minted_source(tmp_path / "scratch", b"durable prefix") as source:
            await adapter.put(source)
        assert adapter._sha256_fd in fsynced
    finally:
        adapter.close()


@pytest.mark.asyncio
async def test_lost_prefix_creation_race_fsyncs_parent_before_link(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Durably observe a concurrently created prefix before publishing into it."""
    adapter = initialize_local_store(root=tmp_path / "artifacts")
    original_mkdir = os.mkdir
    original_fsync = os.fsync
    original_link = os.link
    events: list[str] = []
    injected_race = False

    def race_mkdir(
        path: str,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> None:
        nonlocal injected_race
        if dir_fd == adapter._sha256_fd and not injected_race:
            original_mkdir(path, mode, dir_fd=dir_fd)
            injected_race = True
            raise FileExistsError
        original_mkdir(path, mode, dir_fd=dir_fd)

    def record_fsync(descriptor: int) -> None:
        if descriptor == adapter._sha256_fd:
            events.append("parent_fsync")
        original_fsync(descriptor)

    def record_link(*args: object, **kwargs: object) -> None:
        events.append("link")
        original_link(*args, **kwargs)

    monkeypatch.setattr(os, "mkdir", race_mkdir)
    monkeypatch.setattr(os, "fsync", record_fsync)
    monkeypatch.setattr(os, "link", record_link)
    try:
        async with minted_source(tmp_path / "scratch", b"prefix race") as source:
            await adapter.put(source)
        assert injected_race is True
        assert events.index("parent_fsync") < events.index("link")
    finally:
        adapter.close()


@pytest.mark.asyncio
async def test_invalid_provider_refs_fail_before_filesystem_io(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject traversal and v1 opaque IDs without touching provider storage."""
    adapter = initialize_local_store(root=tmp_path / "artifacts")
    called = False

    def unexpected(_: str) -> int:
        nonlocal called
        called = True
        raise AssertionError

    monkeypatch.setattr(adapter, "_head_object", unexpected)
    try:
        for provider_object_ref in ("../secret", "art_" + "0" * 32, "sha256/AA/x"):
            with pytest.raises(ArtifactOperationConflictError):
                await adapter.head(provider_object_ref)
        assert called is False
    finally:
        adapter.close()


@pytest.mark.asyncio
async def test_put_cancellation_finishes_write_cleanup_and_lock_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve caller cancellation after off-loop I/O and owned cleanup finish."""
    root = tmp_path / "artifacts"
    adapter = initialize_local_store(root=root, buffer_bytes=2)
    started = threading.Event()
    finish = threading.Event()
    original_write = adapter._write_all

    def blocked_write(descriptor: int, chunk: memoryview) -> None:
        started.set()
        finish.wait(timeout=5)
        original_write(descriptor, chunk)

    monkeypatch.setattr(adapter, "_write_all", blocked_write)
    try:
        async with minted_source(tmp_path / "scratch", b"cancel") as source:
            digest_hex = source.commitment.sha256[7:]
            task = asyncio.create_task(adapter.put(source))
            assert await asyncio.to_thread(started.wait, 5)
            task.cancel("caller cancelled local put")
            await asyncio.sleep(0)
            task.cancel()
            finish.set()
            with pytest.raises(asyncio.CancelledError, match="caller cancelled local put"):
                await task
            assert list((root / "tmp").iterdir()) == []
            lock = await adapter._acquire_lock_async(digest_hex)
            await adapter._run_io(adapter._release_lock, lock)
    finally:
        adapter.close()


@pytest.mark.asyncio
async def test_lock_wait_has_a_bounded_deadline(tmp_path: Path) -> None:
    """Fail retryably instead of blocking forever behind another writer."""
    adapter = initialize_local_store(
        root=tmp_path / "artifacts",
        lock_timeout_seconds=0.05,
    )
    digest_hex = "0" * 64
    held = adapter._acquire_lock(digest_hex)
    try:
        with pytest.raises(ArtifactStoreUnavailableError, match="lock deadline"):
            await adapter._acquire_lock_async(digest_hex)
    finally:
        adapter._release_lock(held)
        adapter.close()


@pytest.mark.asyncio
async def test_all_operation_file_io_runs_off_the_event_loop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep object writes, publication, head, and reads off the event-loop thread."""
    adapter = initialize_local_store(root=tmp_path / "artifacts", buffer_bytes=2)
    event_loop_thread = threading.get_ident()
    observed_threads: list[int] = []

    def track(name: str) -> None:
        original = getattr(adapter, name)

        def wrapped(*args: object) -> object:
            observed_threads.append(threading.get_ident())
            return original(*args)

        monkeypatch.setattr(adapter, name, wrapped)

    for method_name in ("_write_all", "_publish_exclusive", "_head_object", "_open_object"):
        track(method_name)
    try:
        async with minted_source(tmp_path / "scratch", b"bounded io") as source:
            result = await adapter.put(source)
        await adapter.head(result.provider_object_ref)
        assert b"".join(
            [chunk async for chunk in adapter.open(result.provider_object_ref)]
        ) == b"bounded io"
        assert observed_threads
        assert event_loop_thread not in observed_threads
    finally:
        adapter.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("read_result", [b"", b"oversized"])
async def test_open_rejects_truncated_or_oversized_provider_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    read_result: bytes,
) -> None:
    adapter = initialize_local_store(root=tmp_path / "artifacts", buffer_bytes=2)
    try:
        async with minted_source(tmp_path / "scratch", b"content") as source:
            result = await adapter.put(source)
        monkeypatch.setattr(os, "pread", lambda *_args: read_result)
        with pytest.raises(ArtifactIntegrityError):
            _ = b"".join(
                [chunk async for chunk in adapter.open(result.provider_object_ref)]
            )
    finally:
        adapter.close()


def test_short_write_and_idempotent_cleanup_fail_safely(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = initialize_local_store(root=tmp_path / "artifacts")
    try:
        monkeypatch.setattr(os, "write", lambda *_args: 0)
        with pytest.raises(OSError, match="short artifact write"):
            adapter._write_all(adapter._tmp_fd, memoryview(b"x"))
        adapter._cleanup_resources(-1, ".put." + "0" * 32 + ".tmp", None)
    finally:
        adapter.close()


def test_cleanup_attempts_lock_release_after_temporary_unlink_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Contain cleanup errors without leaking the owned digest lock."""
    adapter = initialize_local_store(root=tmp_path / "artifacts")
    released: list[tuple[object, int]] = []
    lock = (object(), -1)

    def fail_unlink(*_args: object, **_kwargs: object) -> None:
        raise OSError("private temporary path")

    monkeypatch.setattr(os, "unlink", fail_unlink)
    monkeypatch.setattr(adapter, "_release_lock", released.append)
    try:
        adapter._cleanup_resources(None, ".put." + "0" * 32 + ".tmp", lock)
    finally:
        adapter.close()

    assert released == [lock]


def local_source_intent(store):
    from datetime import UTC, datetime, timedelta
    from app.core.identifiers import new_record_id
    from app.modules.artifacts.api.submission_intake import SubmissionSourceLocation, SubmissionSourceUploadIntent
    return SubmissionSourceUploadIntent(
        location=SubmissionSourceLocation(operation_id=new_record_id(), namespace_id="primary",
            namespace_fingerprint=store._expected_namespace_fingerprint(), provider_profile="local-v2"),
        upload_fence=1, maximum_raw_bytes=6 * 1024 * 1024, declared_raw_bytes=None,
        part_bytes=5 * 1024 * 1024, idle_timeout_seconds=20.0,
        upload_deadline_at=datetime.now(UTC) + timedelta(seconds=90),
    )


async def local_source_completion(store, upload, data):
    from app.modules.artifacts.api.submission_intake import SubmissionSourceCompletion
    parts = []
    for offset in range(0, len(data), upload.intent.part_bytes):
        parts.append(await store.upload_source_part(upload, len(parts) + 1, data[offset:offset + upload.intent.part_bytes]))
    return SubmissionSourceCompletion(upload=upload, parts=tuple(parts),
        raw_sha256="sha256:" + hashlib.sha256(data).hexdigest(), raw_byte_count=len(data))


@pytest.mark.asyncio
@pytest.mark.parametrize("read_cap", [4096, 65536])
async def test_local_submission_source_keeps_one_inode_and_survives_late_abort_and_restart(tmp_path, read_cap):
    from app.interfaces.artifacts import ArtifactPreconditionFailedError
    root = tmp_path / "store"
    store = initialize_local_store(root=root, buffer_bytes=256 * 1024)
    intent = local_source_intent(store)
    upload = await store.begin_source_upload(intent)
    path = root / "objects" / intent.location.object_ref
    inode = path.stat().st_ino
    data = b"x" * (5 * 1024 * 1024) + b"original tail"
    completion = await local_source_completion(store, upload, data)
    sealed = await store.complete_source_upload(completion)
    assert await store.discover_source_uploads(intent) == ()
    assert path.stat().st_ino == inode and path.stat().st_nlink == 1
    assert path.stat().st_mode & 0o777 == 0o400
    await store.request_source_abort(upload)
    assert await store.observe_source_upload(completion) == sealed
    with pytest.raises(ArtifactPreconditionFailedError):
        await store.upload_source_part(upload, 1, b"replacement")
    store.close()
    store = initialize_local_store(root=root, buffer_bytes=256 * 1024)
    try:
        chunks = [chunk async for chunk in store.open_source(sealed, maximum_chunk_bytes=read_cap)]
        assert max(map(len, chunks)) <= read_cap and b"".join(chunks) == data
        assert path.stat().st_ino == inode
        assert list(root.rglob("bundle.zip")) == [path]
    finally:
        store.close()


@pytest.mark.asyncio
async def test_local_submission_source_abort_tombstone_retains_bytes_and_fences_complete(tmp_path):
    from app.interfaces.artifacts import ArtifactPreconditionFailedError
    root = tmp_path / "store"
    store = initialize_local_store(root=root)
    try:
        intent = local_source_intent(store)
        upload = await store.begin_source_upload(intent)
        assert await store.discover_source_uploads(intent) == (upload,)
        completion = await local_source_completion(store, upload, b"partial owned bytes")
        await store.request_source_abort(upload)
        assert (root / "objects" / intent.location.object_ref).read_bytes() == b"partial owned bytes"
        assert await store.discover_source_uploads(intent) == ()
        assert await store.observe_source_upload(completion) is None
        with pytest.raises(ArtifactPreconditionFailedError):
            await store.complete_source_upload(completion)
        with pytest.raises(ArtifactPreconditionFailedError):
            await store.begin_source_upload(intent)
    finally:
        store.close()


@pytest.mark.asyncio
async def test_local_submission_source_rejects_replaced_inode_even_with_identical_bytes(tmp_path):
    root = tmp_path / "store"
    store = initialize_local_store(root=root)
    try:
        upload = await store.begin_source_upload(local_source_intent(store))
        completion = await local_source_completion(store, upload, b"identical bytes")
        sealed = await store.complete_source_upload(completion)
        path = root / "objects" / upload.intent.location.object_ref
        replacement = path.with_name("replacement")
        replacement.write_bytes(b"identical bytes")
        replacement.chmod(0o400)
        replacement.replace(path)
        with pytest.raises(ArtifactIntegrityError, match="generation"):
            await store.observe_source_upload(completion)
        with pytest.raises(ArtifactIntegrityError, match="generation"):
            _ = [chunk async for chunk in store.open_source(sealed)]
    finally:
        store.close()


@pytest.mark.asyncio
async def test_local_submission_cancel_drains_writer_before_abort_and_allows_safe_startup(tmp_path, monkeypatch):
    from app.interfaces.artifacts import ArtifactPreconditionFailedError
    root = tmp_path / "store"
    store = initialize_local_store(root=root)
    upload = await store.begin_source_upload(local_source_intent(store))
    entered, release = threading.Event(), threading.Event()
    original = store._write_all

    def paused(descriptor, chunk):
        if bytes(chunk) == b"in flight":
            entered.set()
            if not release.wait(5):
                raise AssertionError("writer was not released")
        return original(descriptor, chunk)

    monkeypatch.setattr(store, "_write_all", paused)
    writer = asyncio.create_task(store.upload_source_part(upload, 1, b"in flight"))
    abort = None
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        reopened = await asyncio.to_thread(initialize_local_store, root=root)
        reopened.close()  # Layout validation tolerates an active private write.
        writer.cancel()
        abort = asyncio.create_task(store.request_source_abort(upload))
        await asyncio.sleep(0.05)
        assert not writer.done() and not abort.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await writer
        await abort
        assert (root / "objects" / upload.intent.location.object_ref).read_bytes() == b"in flight"
        with pytest.raises(ArtifactPreconditionFailedError):
            await store.upload_source_part(upload, 1, b"late writer")
    finally:
        release.set()
        await asyncio.gather(writer, *([abort] if abort else []), return_exceptions=True)
        store.close()


@pytest.mark.asyncio
async def test_local_submission_interrupted_seal_cannot_admit_more_parts(tmp_path, monkeypatch):
    from app.interfaces.artifacts import ArtifactPreconditionFailedError
    root = tmp_path / "store"
    store = initialize_local_store(root=root)
    upload = await store.begin_source_upload(local_source_intent(store))
    completion = await local_source_completion(store, upload, b"exact raw bytes")
    original = os.fchmod

    def fail_seal(descriptor, mode):
        if mode == 0o400:
            raise OSError("simulated interrupted seal")
        return original(descriptor, mode)

    with monkeypatch.context() as patch:
        patch.setattr(os, "fchmod", fail_seal)
        with pytest.raises(ArtifactStoreUnavailableError):
            await store.complete_source_upload(completion)
    store.close()
    store = initialize_local_store(root=root)
    try:
        assert await store.observe_source_upload(completion) is None
        with pytest.raises(ArtifactPreconditionFailedError):
            await store.upload_source_part(upload, 1, b"overwrite")
        await store.request_source_abort(upload)
        assert (root / "objects" / upload.intent.location.object_ref).read_bytes() == b"exact raw bytes"
    finally:
        store.close()


@pytest.mark.asyncio
async def test_local_submission_rejects_foreign_namespace_handle_and_false_receipts(tmp_path):
    root = tmp_path / "store"
    store = initialize_local_store(root=root)
    try:
        intent = local_source_intent(store)
        foreign = intent.model_copy(update={"location": intent.location.model_copy(
            update={"namespace_fingerprint": "sha256:" + "f" * 64})})
        with pytest.raises(ArtifactOperationConflictError, match="namespace"):
            await store.begin_source_upload(foreign)
        assert not (root / "objects" / "submission-source").exists()
        upload = await store.begin_source_upload(intent)
        with pytest.raises(ArtifactOperationConflictError, match="identity"):
            await store.upload_source_part(upload.model_copy(update={"provider_upload_id": "foreign"}), 1, b"forged")
        completion = await local_source_completion(store, upload, b"original")
        with pytest.raises(ArtifactIntegrityError, match="part"):
            await store.complete_source_upload(completion.model_copy(update={"parts": (
                completion.parts[0].model_copy(update={"provider_etag": "false"}),)}))
        with pytest.raises(ArtifactIntegrityError, match="digest"):
            await store.complete_source_upload(completion.model_copy(update={"raw_sha256": "sha256:" + "0" * 64}))
        sealed = await store.complete_source_upload(completion)
        assert b"".join([part async for part in store.open_source(sealed)]) == b"original"
    finally:
        store.close()


@pytest.mark.asyncio
async def test_local_submission_lost_begin_ack_keeps_discoverable_abort_ownership(tmp_path, monkeypatch):
    from app.adapters.artifacts.local_submission_source import LocalSubmissionSource
    from app.interfaces.artifacts import ArtifactPreconditionFailedError
    root = tmp_path / "store"
    store = initialize_local_store(root=root)
    intent = local_source_intent(store)
    original = LocalSubmissionSource.publish

    def lost_ack(self, directory, name, value):
        original(self, directory, name, value)
        if name == "upload.json":
            raise OSError("lost begin acknowledgement")

    with monkeypatch.context() as patch:
        patch.setattr(LocalSubmissionSource, "publish", lost_ack)
        with pytest.raises(ArtifactStoreUnavailableError):
            await store.begin_source_upload(intent)
    store.close()
    store = initialize_local_store(root=root)
    try:
        uploads = await store.discover_source_uploads(intent)
        assert len(uploads) == 1 and uploads[0].intent == intent
        assert await store.source_upload_parts_absent(uploads[0]) is False
        await store.request_source_abort(uploads[0])
        assert await store.source_upload_parts_absent(uploads[0]) is True
        assert await store.discover_source_uploads(intent) == ()
        with pytest.raises(ArtifactPreconditionFailedError):
            await store.begin_source_upload(intent)
    finally:
        store.close()


@pytest.mark.asyncio
async def test_local_submission_symlink_cannot_write_outside_owned_source(tmp_path):
    root = tmp_path / "store"
    store = initialize_local_store(root=root)
    upload = await store.begin_source_upload(local_source_intent(store))
    path = root / "objects" / upload.intent.location.object_ref
    outside = tmp_path / "retained"
    outside.write_bytes(b"retained bytes")
    path.unlink()
    path.symlink_to(outside)
    try:
        with pytest.raises(ArtifactStoreUnavailableError):
            await store.upload_source_part(upload, 1, b"overwrite")
        assert outside.read_bytes() == b"retained bytes"
    finally:
        store.close()
    with pytest.raises((ArtifactConfigurationError, ArtifactIntegrityError)):
        initialize_local_store(root=root)


@pytest.mark.asyncio
async def test_local_submission_parent_sync_failure_closes_new_directory(tmp_path, monkeypatch):
    import errno
    store = initialize_local_store(root=tmp_path / "store")
    opened = []
    original = store._ensure_directory

    def track_directory(parent, name):
        descriptor = original(parent, name)
        opened.append(descriptor)
        return descriptor

    def fail_sync(_descriptor):
        raise OSError(errno.EIO, "simulated parent directory sync failure")

    try:
        with monkeypatch.context() as patch:
            patch.setattr(store, "_ensure_directory", track_directory)
            patch.setattr(os, "fsync", fail_sync)
            with pytest.raises(ArtifactStoreUnavailableError):
                await store.begin_source_upload(local_source_intent(store))
        assert opened
        for descriptor in opened:
            with pytest.raises(OSError) as failure:
                os.fstat(descriptor)
            assert failure.value.errno == errno.EBADF
    finally:
        # Close leaked test descriptors if this regression is run against the defect.
        for descriptor in opened:
            try:
                os.close(descriptor)
            except OSError:
                pass
        store.close()
