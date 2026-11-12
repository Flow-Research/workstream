"""Proof for canonical sealed submission-tree projection and scratch custody."""

from __future__ import annotations

from io import BytesIO
from dataclasses import replace
import os
from pathlib import Path
import stat
import zipfile

import pytest

from app.modules.artifacts.preparation import (
    HARD_MAXIMUM_ARTIFACT_BYTES,
    ArtifactPreparationLimits,
    ArtifactScratchCapacityError,
    ArtifactScratchManager,
)
from app.modules.artifacts.api.submission_archive import (
    SubmissionArchiveEntryType,
    SubmissionArchiveFailureCode,
    SubmissionArchiveLimits,
    SubmissionArchiveRejectedError,
)
from app.modules.artifacts.submission_archive import (
    SubmissionArchiveInspector,
)
from app.modules.artifacts.submission_manifest import build_submission_manifest


def _zip(*, executable: bool = False) -> bytes:
    output = BytesIO()
    info = zipfile.ZipInfo("src/run.sh")
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | (0o755 if executable else 0o644)) << 16
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(info, b"echo bounded\n")
        archive.writestr("README.md", b"proof\n")
    return output.getvalue()


def _limits(**changes: object) -> ArtifactPreparationLimits:
    values = {
        "aggregate_reserved_bytes": 2 * HARD_MAXIMUM_ARTIFACT_BYTES,
        "maximum_files": 2,
        "maximum_concurrency": 2,
        "minimum_free_bytes": 0,
        "reservation_ttl_seconds": 30.0,
        "total_deadline_seconds": 10.0,
        "cleanup_margin_seconds": 5.0,
        "stream_buffer_bytes": 1024,
        "maximum_source_bytes": 1024 * 1024,
        "maximum_workspace_entries": 2_000,
    }
    values.update(changes)
    return ArtifactPreparationLimits(**values)


class _ProjectionProcessor:
    def __init__(self, inspector, inspection):
        self.inspector = inspector
        self.inspection = inspection
        self.escaped_tree = None
        self.retained_content = None

    def process_blocking(self, reader, workspace):
        def verify(tree):
            self.escaped_tree = tree
            self.retained_content = tree._content
            assert not hasattr(tree, "path")
            assert not hasattr(tree, "execute")
            assert not hasattr(tree, "_root_fd")
            assert not hasattr(tree, "_read")
            assert tree.read_file("README.md", maximum_bytes=16) == b"proof\n"
            assert tree.read_file("src/run.sh", maximum_bytes=32) == b"echo bounded\n"
            return tuple((entry.normalized_path, entry.executable) for entry in tree.entries)

        return self.inspector.project_and_run(
            reader,
            workspace,
            expected=self.inspection,
            callback=verify,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("executable", (False, True))
async def test_projection_is_callback_scoped_and_cleanup_is_complete(
    tmp_path: Path, executable: bool
) -> None:
    data = _zip(executable=executable)
    inspector = SubmissionArchiveInspector(SubmissionArchiveLimits())
    inspection = inspector.inspect(BytesIO(data))
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=_limits())
    processor = _ProjectionProcessor(inspector, inspection)

    with manager.extraction_workspace(
        reserved_bytes=inspection.total_expanded_bytes,
        maximum_entries=inspection.entry_count,
    ) as workspace:
        result = processor.process_blocking(BytesIO(data), workspace)

    assert ("src/run.sh", executable) in result
    assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    assert processor.escaped_tree is not None
    with pytest.raises(RuntimeError, match="closed"):
        processor.escaped_tree.read_file("README.md", maximum_bytes=16)
    assert processor.retained_content == {}
    assert processor.escaped_tree._entries == ()
    manager.close()


@pytest.mark.asyncio
async def test_workspace_expansion_is_charged_before_projection(tmp_path: Path) -> None:
    data = _zip()
    inspector = SubmissionArchiveInspector(SubmissionArchiveLimits())
    inspection = inspector.inspect(BytesIO(data))
    manager = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=_limits(aggregate_reserved_bytes=HARD_MAXIMUM_ARTIFACT_BYTES),
    )
    reservation, descriptor = await manager.allocate()
    os.close(descriptor)
    # Leave one byte less than this projection needs, counting the actual
    # progressive file reservation instead of assuming a full-ceiling charge.
    occupied = (
        manager.limits.aggregate_reserved_bytes
        - (await manager.usage()).reserved_bytes
        - inspection.total_expanded_bytes
        + 1
    )
    with manager.extraction_workspace(reserved_bytes=occupied, maximum_entries=0):
        with pytest.raises(ArtifactScratchCapacityError, match="byte limit"):
            with manager.extraction_workspace(
                reserved_bytes=inspection.total_expanded_bytes,
                maximum_entries=inspection.entry_count,
            ):
                raise AssertionError("workspace must not be exposed")

    assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    await manager.release(reservation)
    manager.close()


@pytest.mark.parametrize(
    "drift",
    ("path", "type", "sha256", "byte_count", "executable", "entry_count", "aggregate"),
)
def test_projection_rejects_manifest_drift_before_callback(tmp_path: Path, drift: str) -> None:
    data = _zip()
    inspector = SubmissionArchiveInspector(SubmissionArchiveLimits())
    inspection = inspector.inspect(BytesIO(data))
    manifest = build_submission_manifest(inspection)
    called = False

    def callback(_tree):
        nonlocal called
        called = True

    entries = list(inspection.entries)
    file_index = next(index for index, entry in enumerate(entries) if entry.sha256 is not None)
    if drift == "path":
        entries[file_index] = replace(entries[file_index], normalized_path="changed.txt")
    elif drift == "type":
        entries[file_index] = replace(
            entries[file_index], entry_type=SubmissionArchiveEntryType.DIRECTORY
        )
    elif drift == "sha256":
        entries[file_index] = replace(entries[file_index], sha256="sha256:" + "0" * 64)
    elif drift == "byte_count":
        entries[file_index] = replace(
            entries[file_index], byte_count=entries[file_index].byte_count + 1
        )
    elif drift == "executable":
        entries[file_index] = replace(
            entries[file_index], executable=not entries[file_index].executable
        )
    drifted = replace(
        inspection,
        entries=tuple(entries),
        entry_count=inspection.entry_count + (1 if drift == "entry_count" else 0),
        total_expanded_bytes=(inspection.total_expanded_bytes + (1 if drift == "aggregate" else 0)),
    )
    with pytest.raises(SubmissionArchiveRejectedError) as caught:
        inspector.project_and_run(
            BytesIO(data),
            tmp_path,
            expected=drifted,
            callback=callback,
        )
    assert manifest.sha256
    assert caught.value.code is SubmissionArchiveFailureCode.INTEGRITY_FAILURE
    assert called is False


def test_workspace_cleanup_bound_is_separate_from_prepared_file_limit(tmp_path: Path) -> None:
    manager = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=_limits(maximum_files=1, maximum_concurrency=1, maximum_workspace_entries=8),
    )
    with manager.extraction_workspace(reserved_bytes=8, maximum_entries=8) as workspace:
        workspace_fd = os.open(workspace, os.O_RDONLY | os.O_DIRECTORY)
        try:
            current_fd = os.dup(workspace_fd)
            for index in range(4):
                os.mkdir(f"level-{index}", mode=0o700, dir_fd=current_fd)
                next_fd = os.open(f"level-{index}", os.O_RDONLY | os.O_DIRECTORY, dir_fd=current_fd)
                descriptor = os.open(
                    f"entry-{index}",
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o600,
                    dir_fd=next_fd,
                )
                os.close(descriptor)
                os.close(current_fd)
                current_fd = next_fd
            os.close(current_fd)
        finally:
            os.close(workspace_fd)
    assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    manager.close()


def test_adapter_failure_after_handoff_revokes_tree_and_cleans_workspace(
    tmp_path: Path,
) -> None:
    data = _zip()
    inspector = SubmissionArchiveInspector(SubmissionArchiveLimits())
    inspection = inspector.inspect(BytesIO(data))
    manager = ArtifactScratchManager(root=tmp_path / "scratch", limits=_limits())
    escaped = None

    def fail(tree):
        nonlocal escaped
        escaped = tree
        assert tree.read_file("README.md", maximum_bytes=16) == b"proof\n"
        raise RuntimeError("adapter failed")

    with pytest.raises(RuntimeError, match="adapter failed"):
        with manager.extraction_workspace(
            reserved_bytes=inspection.total_expanded_bytes,
            maximum_entries=inspection.entry_count,
        ) as workspace:
            inspector.project_and_run(
                BytesIO(data),
                workspace,
                expected=inspection,
                callback=fail,
            )

    assert escaped is not None
    with pytest.raises(RuntimeError, match="closed"):
        escaped.read_file("README.md", maximum_bytes=16)
    assert escaped._content == {}
    assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    manager.close()


def _source_read_fixture(*, failure=None):
    """Controlled commit/authority boundaries; provider I/O is explicitly simulated."""
    from contextlib import asynccontextmanager
    from datetime import UTC, datetime
    from types import SimpleNamespace
    import hashlib
    from app.core.identifiers import new_record_id
    from app.modules.artifacts.api.submission_intake import SubmissionIntakePreSourceFacts
    from app.modules.artifacts.schemas import ArtifactAuthorityDeniedError
    from app.modules.artifacts.selected_pre_submit_execution import SelectedPreSubmitSourceReads
    from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitLeaseFacts
    from tests.checkers.external.test_selected_pre_submit_coordination import _source_reservation

    events = []
    payload = b"authorized original bytes"
    reservation = _source_reservation()
    reservation = replace(reservation, source=reservation.source.model_copy(update={
        "raw_sha256": "sha256:" + hashlib.sha256(payload).hexdigest(), "raw_byte_count": len(payload),
    }))
    lease = SelectedPreSubmitLeaseFacts(reservation, new_record_id(), 1, reservation.pre_deadline_at)
    class Session:
        active = False
        def in_transaction(self):
            return self.active
        @asynccontextmanager
        async def begin(self):
            assert not self.active
            self.active = True
            events.append("begin")
            try:
                yield self
                if failure == "commit":
                    raise RuntimeError("commit acknowledgement lost")
                events.append("commit")
            finally:
                self.active = False
        async def scalar(self, query):
            assert self.active
            return datetime.now(UTC)
    session = Session()
    class Authority:
        async def prepare(self, *, facts, idempotency_key):
            assert session.active and facts.run_id == idempotency_key
            events.append("prepare")
            if failure == "authority":
                raise ArtifactAuthorityDeniedError("source read denied")
            return self
        async def consume(self, *, prepared_authorization, facts):
            assert prepared_authorization is self and session.active
            events.append("consume")
        def close(self):
            events.append("close_authority")
    class Sources:
        async def lock_pre_source(self, **kwargs):
            assert session.active
            events.append("lock_source")
            return SubmissionIntakePreSourceFacts(
                source=reservation.source, project_id=reservation.project_id,
                task_id=new_record_id() if failure == "source" else reservation.task_id,
                assignment_id=reservation.assignment_id, actor_profile_id=reservation.actor_profile_id,
                identity_link_id=reservation.identity_link_id, metadata_sha256=reservation.metadata_sha256,
                locked_context_sha256=reservation.locked_context_sha256,
                lease_id=reservation.foreground_lease_id, lease_generation=reservation.foreground_lease_generation,
                lease_expires_at=reservation.pre_deadline_at, pre_deadline_at=reservation.pre_deadline_at,
            )
    class Capability:
        consumed = False
        def consume(self, *, run_id, lease):
            assert not self.consumed and run_id == lease.reservation.attempt_id
            self.consumed = True
            return lease
    class Store:
        def open_source(self, source, *, maximum_chunk_bytes):
            assert not session.active and events.index("commit") > events.index("consume")
            assert source == reservation.source and maximum_chunk_bytes == 64 * 1024
            events.append("open_source")
            async def chunks():
                try:
                    yield payload
                finally:
                    events.append("close_source")
            return chunks()
    return SimpleNamespace(
        issuer=SelectedPreSubmitSourceReads(session=session, sources=Sources(), authority=Authority(), store=Store()),
        session=session, lease=lease, capability=Capability(), events=events, payload=payload,
    )


@pytest.mark.asyncio
async def test_pre_source_grant_requires_commit_and_is_one_use_and_callback_scoped():
    from app.core.identifiers import new_record_id
    from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitInfrastructureUnavailable

    value = _source_read_fixture()
    async with value.issuer.issue(lease=value.lease, execution_authority=value.capability) as grant:
        assert value.events == ["begin", "prepare", "lock_source", "consume", "commit"]
        with pytest.raises(SelectedPreSubmitInfrastructureUnavailable):
            grant.open_source(lease=replace(value.lease, lease_id=new_record_id()))
        reader = grant.open_source(lease=value.lease)
        with pytest.raises(SelectedPreSubmitInfrastructureUnavailable):
            grant.open_source(lease=value.lease)
        assert b"".join([chunk async for chunk in reader]) == value.payload
    assert value.events[-2:] == ["close_source", "close_authority"]
    with pytest.raises(SelectedPreSubmitInfrastructureUnavailable):
        grant.open_source(lease=value.lease)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["authority", "source", "commit"])
async def test_pre_source_grant_never_exposes_bytes_before_authorized_commit(failure):
    from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitInfrastructureUnavailable

    value = _source_read_fixture(failure=failure)
    error = RuntimeError if failure == "commit" else SelectedPreSubmitInfrastructureUnavailable
    with pytest.raises(error):
        async with value.issuer.issue(lease=value.lease, execution_authority=value.capability):
            raise AssertionError("uncommitted or unauthorized source grant escaped")
    assert "open_source" not in value.events
    assert "commit" not in value.events
    if failure != "commit":
        assert "consume" not in value.events


@pytest.mark.asyncio
async def test_pre_source_grant_refuses_reads_in_database_transaction():
    from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitInfrastructureUnavailable

    value = _source_read_fixture()
    async with value.issuer.issue(lease=value.lease, execution_authority=value.capability) as grant:
        async with value.session.begin():
            with pytest.raises(SelectedPreSubmitInfrastructureUnavailable):
                grant.open_source(lease=value.lease)
    assert "open_source" not in value.events


@pytest.mark.asyncio
async def test_pre_source_grant_closes_abandoned_reader_when_callback_ends():
    value = _source_read_fixture()
    async with value.issuer.issue(lease=value.lease, execution_authority=value.capability) as grant:
        reader = grant.open_source(lease=value.lease)
        assert await anext(reader) == value.payload
        assert "close_source" not in value.events
    assert value.events[-2:] == ["close_source", "close_authority"]
    with pytest.raises(StopAsyncIteration):
        await anext(reader)


@pytest.mark.asyncio
async def test_pre_source_grant_cannot_start_escaped_reader_after_callback():
    from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitInfrastructureUnavailable

    value = _source_read_fixture()
    async with value.issuer.issue(lease=value.lease, execution_authority=value.capability) as grant:
        reader = grant.open_source(lease=value.lease)
    with pytest.raises((StopAsyncIteration, SelectedPreSubmitInfrastructureUnavailable)):
        await anext(reader)
    assert "open_source" not in value.events
