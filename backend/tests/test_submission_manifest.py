from __future__ import annotations

from dataclasses import replace
from io import BytesIO
import stat
import zipfile

import pytest

from app.modules.artifacts.submission_archive import (
    SubmissionArchiveInspector,
    SubmissionArchiveLimits,
)
from app.modules.artifacts.submission_manifest import build_submission_manifest


def _archive(
    entries: list[tuple[zipfile.ZipInfo | str, bytes]],
    *,
    compression: int = zipfile.ZIP_STORED,
    comment: bytes = b"",
) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=compression) as archive:
        archive.comment = comment
        for name, value in entries:
            archive.writestr(name, value)
    return output.getvalue()


def _manifest(data: bytes):
    inspection = SubmissionArchiveInspector(SubmissionArchiveLimits()).inspect(BytesIO(data))
    return build_submission_manifest(inspection)


def _unix_file(name: str, mode: int) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(2024, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | mode) << 16
    return info


def test_manifest_is_closed_sorted_and_derived_from_member_bytes() -> None:
    manifest = _manifest(_archive([("z.txt", b"z"), ("dir/a.txt", b"actual")]))

    assert manifest.schema_version == "workstream.submission_bundle_manifest.v1"
    assert manifest.as_dict() == {
        "schema_version": "workstream.submission_bundle_manifest.v1",
        "entries": [
            {"normalized_path": "dir", "entry_type": "directory"},
            {
                "normalized_path": "dir/a.txt",
                "entry_type": "file",
                "sha256": "sha256:e5c6fde86910ded72db5cc7afc32f850440d4ef7caa5dbb69f5bdc0d3e39cb3b",
                "byte_count": 6,
                "executable": False,
            },
            {
                "normalized_path": "z.txt",
                "entry_type": "file",
                "sha256": "sha256:594e519ae499312b29433b7dd8a97ff068defcba9755b6d5d00e84c524d67b06",
                "byte_count": 1,
                "executable": False,
            },
        ],
    }
    assert manifest.sha256.startswith("sha256:")


def test_packaging_changes_do_not_change_semantic_identity() -> None:
    first_info = zipfile.ZipInfo("file.txt", date_time=(2024, 1, 1, 0, 0, 0))
    first_info.comment = b"entry one"
    second_info = zipfile.ZipInfo("file.txt", date_time=(2025, 2, 2, 2, 2, 2))
    second_info.comment = b"entry two"
    second_info.compress_type = zipfile.ZIP_DEFLATED
    first = _manifest(_archive([(first_info, b"same")], comment=b"archive one"))
    second = _manifest(
        _archive(
            [(second_info, b"same")],
            compression=zipfile.ZIP_DEFLATED,
            comment=b"archive two",
        )
    )

    assert first.sha256 == second.sha256
    assert first.as_dict() == second.as_dict()


def test_explicit_and_synthetic_parent_match_but_empty_directory_is_semantic() -> None:
    synthetic = _manifest(_archive([("dir/file", b"x")]))
    explicit = _manifest(_archive([("dir/", b""), ("dir/file", b"x")]))
    with_empty = _manifest(_archive([("dir/file", b"x"), ("empty/", b"")]))

    assert explicit.sha256 == synthetic.sha256
    assert with_empty.sha256 != synthetic.sha256


def test_only_normalized_unix_execute_intent_changes_identity() -> None:
    regular = _manifest(_archive([(_unix_file("run", 0o644), b"x")]))
    read_only = _manifest(_archive([(_unix_file("run", 0o400), b"x")]))
    executable = _manifest(_archive([(_unix_file("run", 0o755), b"x")]))
    setuid_executable = _manifest(_archive([(_unix_file("run", 0o4755), b"x")]))
    windows = zipfile.ZipInfo("run")
    windows.create_system = 0
    windows.external_attr = 0o755 << 16
    windows_manifest = _manifest(_archive([(windows, b"x")]))

    assert regular.sha256 == read_only.sha256 == windows_manifest.sha256
    assert executable.sha256 == setuid_executable.sha256
    assert executable.sha256 != regular.sha256
    assert executable.as_dict()["entries"][0]["executable"] is True


def test_content_path_and_type_changes_are_semantic() -> None:
    baseline = _manifest(_archive([("a", b"x")]))

    assert _manifest(_archive([("a", b"y")])).sha256 != baseline.sha256
    assert _manifest(_archive([("b", b"x")])).sha256 != baseline.sha256
    assert _manifest(_archive([("a/", b"")])).sha256 != baseline.sha256


def test_manifest_rejects_tampered_digest_and_aggregates() -> None:
    manifest = _manifest(_archive([("a", b"x")]))

    with pytest.raises(ValueError, match="digest is inconsistent"):
        replace(manifest, sha256=f"sha256:{'0' * 64}")
    with pytest.raises(ValueError, match="aggregates are inconsistent"):
        replace(manifest, file_count=0)
