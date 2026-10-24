from __future__ import annotations

from dataclasses import replace
from io import BytesIO
import stat
import zipfile

import pytest

from app.modules.artifacts.api.submission_archive import (
    SubmissionArchiveLimits,
)
from app.modules.artifacts.submission_archive import (
    SubmissionArchiveInspector,
)
from app.modules.artifacts.submission_manifest import SubmissionManifest, build_submission_manifest
from app.core.hashing import canonical_json_hash


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


def test_stored_manifest_round_trip_retains_unicode_files_and_directories() -> None:
    manifest = _manifest(_archive([("café/α.txt", b"verified"), ("empty/", b"")]))
    assert SubmissionManifest.from_dict(manifest.as_dict(), sha256=manifest.sha256) == manifest
    body = manifest.as_dict()
    body["entries"][-1]["entry_type"] = "file"
    with pytest.raises(ValueError):
        SubmissionManifest.from_dict(body, sha256=manifest.sha256)


@pytest.mark.parametrize("corruption", ["missing", "extra", "duplicate", "order", "boolean_size", "hash"])
def test_stored_manifest_rejects_independent_invalid_metadata(corruption) -> None:
    manifest = _manifest(_archive([("a.txt", b"a"), ("z.txt", b"z")]))
    body = manifest.as_dict()
    if corruption == "missing":
        del body["entries"][0]["executable"]
    elif corruption == "extra":
        body["entries"][0]["content"] = "must not be retained"
    elif corruption == "duplicate":
        body["entries"][1] = body["entries"][0].copy()
    elif corruption == "order":
        body["entries"].reverse()
    elif corruption == "boolean_size":
        body["entries"][0]["byte_count"] = True
    else:
        body["entries"][0]["sha256"] = "sha256:" + "a" * 64
    # Shape cases have a matching hash, so they cannot fail on stale digest alone.
    digest = manifest.sha256 if corruption == "hash" else canonical_json_hash(body)
    with pytest.raises(ValueError):
        SubmissionManifest.from_dict(body, sha256=digest)


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


@pytest.mark.parametrize("path", ["../outside.txt", "/absolute.txt", "dir\\file.txt", "a//b", "a/./b", "a./b", "drive:c/file", "cafe\u0301.txt", "x" * 4097])
def test_stored_manifest_rejects_noncanonical_paths_with_matching_hash(path):
    body = _manifest(_archive([("safe.txt", b"data")])).as_dict()
    body["entries"][0]["normalized_path"] = path
    with pytest.raises(ValueError):
        SubmissionManifest.from_dict(body, sha256=canonical_json_hash(body))


def test_recovered_manifest_accepts_supported_configured_long_path():
    body = _manifest(_archive([("safe.txt", b"data")])).as_dict()
    body["entries"][0]["normalized_path"] = "x" * 1025
    recovered = SubmissionManifest.from_dict(body, sha256=canonical_json_hash(body))
    assert recovered.as_dict() == body


@pytest.mark.parametrize('paths', [
    ('A', 'a'), ('dir', 'dir/x'), ('DIR/x', 'dir'),
    ('STRASSE', 'Straße'), ('Σ', 'ς'), ('İ', 'i\u0307'),
])
def test_manifest_and_zip_reject_cross_entry_collisions(paths):
    from app.modules.artifacts.api.submission_archive import (
        SubmissionArchiveRejectedError,
    )

    body = _manifest(_archive([('safe', b'x')])).as_dict()
    entry = body['entries'][0]
    body['entries'] = sorted(
        [dict(entry, normalized_path=path) for path in paths],
        key=lambda item: item['normalized_path'],
    )
    with pytest.raises(SubmissionArchiveRejectedError, match='submission_archive_collision'):
        SubmissionManifest.from_dict(body, sha256=canonical_json_hash(body))
    with pytest.raises(SubmissionArchiveRejectedError, match='submission_archive_collision'):
        _manifest(_archive([(path, b'x') for path in paths]))


@pytest.mark.parametrize('paths', [('Dir/a', 'dir/'), ('Dir/a', 'dir/b')])
def test_inspector_rejects_case_aliases_of_implicit_directories(paths):
    from app.modules.artifacts.api.submission_archive import (
        SubmissionArchiveRejectedError,
    )

    with pytest.raises(SubmissionArchiveRejectedError, match='submission_archive_collision'):
        _manifest(_archive([(path, b'' if path.endswith('/') else b'x') for path in paths]))


def test_inventory_preserves_distinct_unicode_and_exact_directory_parents():
    manifest = _manifest(_archive([('café/', b''), ('café/a', b'x'), ('cafe', b'y')]))
    assert SubmissionManifest.from_dict(manifest.as_dict(), sha256=manifest.sha256) == manifest
