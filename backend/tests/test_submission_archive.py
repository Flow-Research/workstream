from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path
import stat
import struct
import threading
from typing import BinaryIO
import zipfile

import pytest

from app.modules.artifacts.preparation import ArtifactPreparationService, ArtifactScratchManager
from app.modules.artifacts.submission_archive import (
    SubmissionArchiveEntryType,
    SubmissionArchiveFailureCode,
    SubmissionArchiveInspector,
    SubmissionArchiveLimits,
    SubmissionArchiveRejectedError,
)
from app.modules.artifacts.zip_safety import zip_directory_facts
from tests.artifact_store_helpers import artifact_byte_stream, artifact_preparation_limits


def archive_bytes(entries: dict[str, bytes], *, compression: int = zipfile.ZIP_STORED) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=compression, allowZip64=True) as archive:
        for name, value in entries.items():
            archive.writestr(name, value)
    return output.getvalue()


def inspect(data: bytes, limits: SubmissionArchiveLimits | None = None):
    return SubmissionArchiveInspector(limits or SubmissionArchiveLimits()).inspect(BytesIO(data))


def rejection(data: bytes, code: SubmissionArchiveFailureCode) -> None:
    with pytest.raises(SubmissionArchiveRejectedError) as caught:
        inspect(data)
    assert caught.value.code is code
    assert str(caught.value) == code.value


def test_outer_zip_returns_sorted_typed_structure_and_implicit_directories() -> None:
    nested = archive_bytes({"inside.txt": b"ordinary nested bytes"})
    result = inspect(archive_bytes({"z.txt": b"z", "folder/a.zip": nested}))

    assert [(entry.normalized_path, entry.entry_type, entry.byte_count) for entry in result.entries] == [
        ("folder", SubmissionArchiveEntryType.DIRECTORY, 0),
        ("folder/a.zip", SubmissionArchiveEntryType.FILE, len(nested)),
        ("z.txt", SubmissionArchiveEntryType.FILE, 1),
    ]
    assert result.entry_count == 3
    assert result.file_count == 2
    assert result.directory_count == 1
    assert result.total_expanded_bytes == len(nested) + 1


@pytest.mark.parametrize(
    "name",
    (
        "../escape",
        "/absolute",
        "C:/drive",
        "a\\b",
        "a/./b",
        "a//b",
        "trailing. ",
    ),
)
def test_unsafe_paths_fail_with_one_redacted_code(name: str) -> None:
    rejection(archive_bytes({name: b"x"}), SubmissionArchiveFailureCode.UNSAFE_ENTRY)


@pytest.mark.parametrize(
    "entries",
    (
        {"A.txt": b"a", "a.txt": b"b"},
        {"café.txt": b"a", "café.txt": b"b"},
        {"node": b"file", "node/child": b"child"},
        {"node/child": b"child", "node": b"file"},
    ),
)
def test_collision_and_ancestry_confusion_fail_closed(entries: dict[str, bytes]) -> None:
    rejection(archive_bytes(entries), SubmissionArchiveFailureCode.COLLISION)


def test_symlink_entry_is_rejected() -> None:
    output = BytesIO()
    info = zipfile.ZipInfo("link")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(info, b"target")
    rejection(output.getvalue(), SubmissionArchiveFailureCode.UNSAFE_ENTRY)


@pytest.mark.parametrize("kind", (stat.S_IFIFO, stat.S_IFCHR, stat.S_IFBLK, stat.S_IFSOCK))
def test_other_special_entries_are_rejected(kind: int) -> None:
    output = BytesIO()
    info = zipfile.ZipInfo("special")
    info.create_system = 3
    info.external_attr = (kind | 0o600) << 16
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(info, b"content")
    rejection(output.getvalue(), SubmissionArchiveFailureCode.UNSAFE_ENTRY)


def test_encrypted_flag_is_rejected_before_member_open() -> None:
    data = bytearray(archive_bytes({"private.txt": b"content"}))
    local = data.index(b"PK\x03\x04")
    central = data.index(b"PK\x01\x02")
    data[local + 6 : local + 8] = (1).to_bytes(2, "little")
    data[central + 8 : central + 10] = (1).to_bytes(2, "little")
    rejection(bytes(data), SubmissionArchiveFailureCode.ENCRYPTED)


def test_actual_expansion_and_ratio_are_bounded() -> None:
    data = archive_bytes({"large.txt": b"0" * 4096}, compression=zipfile.ZIP_DEFLATED)
    with pytest.raises(SubmissionArchiveRejectedError) as caught:
        inspect(data, SubmissionArchiveLimits(maximum_entry_bytes=4096, maximum_expanded_bytes=4096, maximum_compression_ratio=2))
    assert caught.value.code is SubmissionArchiveFailureCode.LIMIT_EXCEEDED


def test_corrupt_member_is_fully_read_and_rejected() -> None:
    data = bytearray(archive_bytes({"payload.txt": b"unique payload bytes"}))
    offset = data.index(b"unique payload bytes")
    data[offset] ^= 0xFF
    rejection(bytes(data), SubmissionArchiveFailureCode.INTEGRITY_FAILURE)


def test_local_header_name_disagreement_is_rejected_during_full_read() -> None:
    data = bytearray(archive_bytes({"payload.txt": b"content"}))
    local_name = data.index(b"payload.txt")
    data[local_name] = ord("x")
    rejection(bytes(data), SubmissionArchiveFailureCode.INTEGRITY_FAILURE)


def test_directory_local_header_cannot_hide_unsafe_path() -> None:
    data = bytearray(archive_bytes({"safe/": b""}))
    local_name = data.index(b"safe/")
    data[local_name : local_name + 5] = b"../x/"
    rejection(bytes(data), SubmissionArchiveFailureCode.INTEGRITY_FAILURE)


def test_declared_uncompressed_size_mismatch_is_rejected() -> None:
    data = bytearray(archive_bytes({"payload.txt": b"content"}))
    central = data.index(b"PK\x01\x02")
    data[central + 24 : central + 28] = (99).to_bytes(4, "little")
    rejection(bytes(data), SubmissionArchiveFailureCode.INTEGRITY_FAILURE)


def test_data_descriptor_archive_is_read_without_special_casing() -> None:
    class UnseekableBuffer(BytesIO):
        def seekable(self) -> bool:
            return False

        def seek(self, *_args: object, **_kwargs: object) -> int:
            raise OSError("not seekable")

    output = UnseekableBuffer()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("descriptor.txt", b"descriptor content")
    result = inspect(output.getvalue())
    assert result.total_expanded_bytes == len(b"descriptor content")

    malformed = bytearray(output.getvalue())
    descriptor = malformed.index(b"PK\x07\x08")
    malformed[descriptor + 4] ^= 0xFF
    rejection(bytes(malformed), SubmissionArchiveFailureCode.INTEGRITY_FAILURE)


def test_malformed_non_zip_and_multidisk_are_rejected() -> None:
    rejection(b"not a zip", SubmissionArchiveFailureCode.MALFORMED)
    data = bytearray(archive_bytes({"a": b"a"}))
    marker = data.rfind(b"PK\x05\x06")
    data[marker + 4 : marker + 6] = (1).to_bytes(2, "little")
    rejection(bytes(data), SubmissionArchiveFailureCode.MALFORMED)


@pytest.mark.parametrize("wrapped", ("prefix", "suffix"))
def test_additional_bytes_outside_exact_zip_envelope_are_rejected(wrapped: str) -> None:
    data = archive_bytes({"a": b"a"})
    candidate = b"JUNK" + data if wrapped == "prefix" else data + b"JUNK"
    rejection(candidate, SubmissionArchiveFailureCode.MALFORMED)


def test_pk_prefixed_payload_and_inter_record_gap_are_rejected() -> None:
    data = archive_bytes({"a": b"a"})
    rejection(b"PK\x03\x04JUNK" + data, SubmissionArchiveFailureCode.MALFORMED)

    gap = b"HIDDEN"
    mutated = bytearray(data)
    central = mutated.index(b"PK\x01\x02")
    mutated[central:central] = gap
    eocd = mutated.rfind(b"PK\x05\x06")
    old_offset = int.from_bytes(mutated[eocd + 16 : eocd + 20], "little")
    mutated[eocd + 16 : eocd + 20] = (old_offset + len(gap)).to_bytes(4, "little")
    rejection(bytes(mutated), SubmissionArchiveFailureCode.INTEGRITY_FAILURE)


def test_directory_entry_cannot_hide_payload_bytes() -> None:
    rejection(archive_bytes({"directory/": b"hidden"}), SubmissionArchiveFailureCode.UNSAFE_ENTRY)


def test_stored_member_cannot_hide_bytes_beyond_declared_file_size() -> None:
    import binascii

    data = bytearray(archive_bytes({"file": b"abcXYZ"}))
    local = data.index(b"PK\x03\x04")
    central = data.index(b"PK\x01\x02")
    crc = binascii.crc32(b"abc")
    for offset in (local + 14, central + 16):
        data[offset : offset + 4] = crc.to_bytes(4, "little")
    for offset in (local + 22, central + 24):
        data[offset : offset + 4] = (3).to_bytes(4, "little")
    rejection(bytes(data), SubmissionArchiveFailureCode.INTEGRITY_FAILURE)


def test_deflate_member_cannot_hide_unused_compressed_tail() -> None:
    data = bytearray(
        archive_bytes({"file": b"deflated content"}, compression=zipfile.ZIP_DEFLATED)
    )
    local = data.index(b"PK\x03\x04")
    central = data.index(b"PK\x01\x02")
    compressed = int.from_bytes(data[local + 18 : local + 22], "little")
    tail = b"UNUSED"
    data[central:central] = tail
    shifted_central = central + len(tail)
    for offset in (local + 18, shifted_central + 20):
        data[offset : offset + 4] = (compressed + len(tail)).to_bytes(4, "little")
    eocd = data.rfind(b"PK\x05\x06")
    data[eocd + 16 : eocd + 20] = shifted_central.to_bytes(4, "little")
    rejection(bytes(data), SubmissionArchiveFailureCode.INTEGRITY_FAILURE)


def test_unsupported_zip_compression_method_fails_closed() -> None:
    rejection(
        archive_bytes({"file": b"content"}, compression=zipfile.ZIP_BZIP2),
        SubmissionArchiveFailureCode.MALFORMED,
    )


def test_limit_configuration_rejects_invalid_or_oversized_values() -> None:
    with pytest.raises(ValueError, match="512 MiB"):
        SubmissionArchiveLimits(maximum_expanded_bytes=512 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="entry limit"):
        SubmissionArchiveLimits(maximum_entry_bytes=2, maximum_expanded_bytes=1)
    with pytest.raises(ValueError, match="limits are invalid"):
        SubmissionArchiveLimits(maximum_entries=0)
    with pytest.raises(ValueError, match="inventory"):
        SubmissionArchiveLimits(maximum_entries=100_001)
    with pytest.raises(ValueError, match="deadline"):
        SubmissionArchiveLimits(maximum_inspection_seconds=False)
    with pytest.raises(ValueError, match="deadline"):
        SubmissionArchiveLimits(maximum_inspection_seconds=float("inf"))


def test_entry_inventory_and_total_expansion_limits_are_enforced() -> None:
    data = archive_bytes({"a": b"aa", "b": b"bb"})
    with pytest.raises(SubmissionArchiveRejectedError) as inventory:
        inspect(data, SubmissionArchiveLimits(maximum_entries=1))
    assert inventory.value.code is SubmissionArchiveFailureCode.LIMIT_EXCEEDED
    with pytest.raises(SubmissionArchiveRejectedError) as directory:
        inspect(data, SubmissionArchiveLimits(maximum_central_directory_bytes=1))
    assert directory.value.code is SubmissionArchiveFailureCode.LIMIT_EXCEEDED
    with pytest.raises(SubmissionArchiveRejectedError) as entry:
        inspect(data, SubmissionArchiveLimits(maximum_entry_bytes=1, maximum_expanded_bytes=4))
    assert entry.value.code is SubmissionArchiveFailureCode.LIMIT_EXCEEDED
    with pytest.raises(SubmissionArchiveRejectedError) as total:
        inspect(data, SubmissionArchiveLimits(maximum_entry_bytes=2, maximum_expanded_bytes=3))
    assert total.value.code is SubmissionArchiveFailureCode.LIMIT_EXCEEDED


def test_explicit_directory_is_structural_and_deadline_is_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = inspect(archive_bytes({"folder/file": b"x", "folder/": b""}))
    assert result.entries[0].entry_type is SubmissionArchiveEntryType.DIRECTORY
    monkeypatch.setattr("app.modules.artifacts.submission_archive.time.monotonic", lambda: 2.0)
    inspector = SubmissionArchiveInspector(
        SubmissionArchiveLimits(maximum_inspection_seconds=1.0)
    )
    with zipfile.ZipFile(BytesIO(archive_bytes({"a": b"a"}))) as archive:
        with pytest.raises(SubmissionArchiveRejectedError) as caught:
            inspector._read_entries(  # noqa: SLF001 - deterministic deadline boundary
                archive, archive.infolist(), started=0.0
            )
    assert caught.value.code is SubmissionArchiveFailureCode.TIMEOUT


def test_zip64_directory_probe_is_explicitly_bounded() -> None:
    zip64_record = (
        b"PK\x06\x06"
        + struct.pack("<QHHIIQQQQ", 44, 45, 45, 0, 0, 0, 0, 0, 0)
    )
    locator = b"PK\x06\x07" + struct.pack("<IQI", 0, 0, 1)
    eocd = b"PK\x05\x06" + struct.pack(
        "<HHHHIIH", 0, 0, 0xFFFF, 0xFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0
    )
    data = zip64_record + locator + eocd
    with pytest.raises(zipfile.BadZipFile, match="unsupported"):
        zip_directory_facts(BytesIO(data))
    assert zip_directory_facts(BytesIO(data), allow_zip64=True) == (0, 0)
    result = inspect(data)
    assert result.entry_count == 0

    missing_locator = bytearray(data)
    missing_locator[len(zip64_record) : len(zip64_record) + 4] = b"NOPE"
    with pytest.raises(zipfile.BadZipFile, match="locator"):
        zip_directory_facts(BytesIO(missing_locator), allow_zip64=True)


@pytest.mark.asyncio
async def test_inspection_runs_through_prepared_artifact_and_cleanup_remains_owned(
    tmp_path: Path,
) -> None:
    manager = ArtifactScratchManager(
        root=tmp_path / "scratch", limits=artifact_preparation_limits()
    )
    prepared = await ArtifactPreparationService(manager).prepare(
        artifact_byte_stream(archive_bytes({"work.txt": b"complete"})),
        media_type="application/zip",
    )
    async with prepared:
        result = await prepared.inspect(SubmissionArchiveInspector(SubmissionArchiveLimits()))
        assert result.file_count == 1
        assert not hasattr(result, "reader")
        assert not hasattr(result, "scratch_path")
    assert (await manager.usage()).reservation_count == 0
    assert list((tmp_path / "scratch" / "files").iterdir()) == []
    manager.close()


@pytest.mark.asyncio
async def test_rejected_inspection_is_redacted_and_prepared_scratch_is_released(
    tmp_path: Path,
) -> None:
    manager = ArtifactScratchManager(
        root=tmp_path / "scratch", limits=artifact_preparation_limits()
    )
    prepared = await ArtifactPreparationService(manager).prepare(
        artifact_byte_stream(archive_bytes({"../../secret-name": b"secret-value"})),
        media_type="application/zip",
    )
    with pytest.raises(SubmissionArchiveRejectedError) as caught:
        async with prepared:
            await prepared.inspect(SubmissionArchiveInspector(SubmissionArchiveLimits()))
    assert "secret-name" not in str(caught.value)
    assert "secret-value" not in str(caught.value)
    assert (await manager.usage()).reservation_count == 0
    manager.close()


@pytest.mark.asyncio
async def test_timeout_through_prepared_inspection_releases_scratch(
    tmp_path: Path,
) -> None:
    manager = ArtifactScratchManager(
        root=tmp_path / "scratch", limits=artifact_preparation_limits()
    )
    prepared = await ArtifactPreparationService(manager).prepare(
        artifact_byte_stream(archive_bytes({"work.txt": b"complete"})),
        media_type="application/zip",
    )
    class DeterministicTimeoutInspector(SubmissionArchiveInspector):
        def _check_deadline(self, started: float) -> None:
            del started
            self._reject(SubmissionArchiveFailureCode.TIMEOUT)

    with pytest.raises(SubmissionArchiveRejectedError) as caught:
        async with prepared:
            await prepared.inspect(
                DeterministicTimeoutInspector(
                    SubmissionArchiveLimits(maximum_inspection_seconds=1.0)
                )
            )
    assert caught.value.code is SubmissionArchiveFailureCode.TIMEOUT
    assert (await manager.usage()).reservation_count == 0
    manager.close()


@pytest.mark.asyncio
async def test_cancelled_prepared_inspection_finishes_then_releases_scratch(
    tmp_path: Path,
) -> None:
    manager = ArtifactScratchManager(
        root=tmp_path / "scratch", limits=artifact_preparation_limits()
    )
    prepared = await ArtifactPreparationService(manager).prepare(
        artifact_byte_stream(archive_bytes({"work.txt": b"complete"})),
        media_type="application/zip",
    )
    entered = threading.Event()
    release = threading.Event()

    class BlockingInspector:
        def inspect(self, reader: BinaryIO) -> int:
            entered.set()
            assert release.wait(5)
            return len(reader.read())

    async with prepared:
        task = asyncio.create_task(prepared.inspect(BlockingInspector()))
        assert await asyncio.to_thread(entered.wait, 5)
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert (await manager.usage()).reservation_count == 0
    manager.close()
