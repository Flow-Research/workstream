"""Neutral bounded ZIP directory primitives shared by ART consumers."""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import BinaryIO
import zipfile


_EOCD = b"PK\x05\x06"
_ZIP64_LOCATOR = b"PK\x06\x07"
_ZIP64_EOCD = b"PK\x06\x06"


@dataclass(frozen=True, slots=True)
class ZipDirectoryLayout:
    entry_count: int
    directory_bytes: int
    directory_offset: int
    end_record_offset: int


def zip_directory_facts(
    source: BinaryIO, *, allow_zip64: bool = False
) -> tuple[int, int]:
    """Read bounded EOCD facts before ZipFile allocates its inventory."""
    layout = zip_directory_layout(source, allow_zip64=allow_zip64)
    return layout.entry_count, layout.directory_bytes


def zip_directory_layout(
    source: BinaryIO, *, allow_zip64: bool = False
) -> ZipDirectoryLayout:
    """Return the exact central-directory envelope after bounded tail parsing."""
    source.seek(0, 2)
    size = source.tell()
    source.seek(max(0, size - 65_557))
    tail = source.read(65_557)
    marker = tail.rfind(_EOCD)
    if marker < 0 or len(tail) - marker < 22:
        raise zipfile.BadZipFile("missing end of central directory")
    absolute_marker = max(0, size - 65_557) + marker
    comment_bytes = int.from_bytes(tail[marker + 20 : marker + 22], "little")
    if marker + 22 + comment_bytes != len(tail):
        raise zipfile.BadZipFile("trailing archive content")
    disk, directory_disk, _disk_entries, entries, directory_bytes, directory_offset = (
        struct.unpack_from("<HHHHII", tail, marker + 4)
    )
    if disk or directory_disk:
        raise zipfile.BadZipFile("multi-disk archive")
    if entries != 0xFFFF and directory_bytes != 0xFFFFFFFF:
        if directory_offset + directory_bytes != absolute_marker:
            raise zipfile.BadZipFile("central directory offset disagreement")
        return ZipDirectoryLayout(
            entries, directory_bytes, directory_offset, absolute_marker
        )
    if not allow_zip64:
        raise zipfile.BadZipFile("zip64 archive is unsupported")
    if absolute_marker < 20:
        raise zipfile.BadZipFile("missing zip64 locator")
    source.seek(absolute_marker - 20)
    locator = source.read(20)
    if len(locator) != 20 or locator[:4] != _ZIP64_LOCATOR:
        raise zipfile.BadZipFile("missing zip64 locator")
    locator_disk, record_offset, disk_count = struct.unpack_from("<IQI", locator, 4)
    if locator_disk or disk_count != 1:
        raise zipfile.BadZipFile("multi-disk archive")
    source.seek(record_offset)
    record = source.read(56)
    if len(record) < 56 or record[:4] != _ZIP64_EOCD:
        raise zipfile.BadZipFile("missing zip64 end record")
    record_disk, directory_record_disk = struct.unpack_from("<II", record, 16)
    disk_entries64, entries64, directory_bytes64, directory_offset64 = struct.unpack_from(
        "<QQQQ", record, 24
    )
    if record_disk or directory_record_disk or disk_entries64 != entries64:
        raise zipfile.BadZipFile("multi-disk archive")
    if directory_offset64 + directory_bytes64 != record_offset:
        raise zipfile.BadZipFile("central directory offset disagreement")
    return ZipDirectoryLayout(
        entries64, directory_bytes64, directory_offset64, record_offset
    )
