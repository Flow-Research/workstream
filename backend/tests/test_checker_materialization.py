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
from app.modules.artifacts.submission_archive import (
    SubmissionArchiveEntryType,
    SubmissionArchiveFailureCode,
    SubmissionArchiveInspector,
    SubmissionArchiveLimits,
    SubmissionArchiveRejectedError,
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
