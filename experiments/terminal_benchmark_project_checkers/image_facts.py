#!/usr/bin/env python3
"""Resolve only exact linux/amd64 manifest facts from pinned image bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat


DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
MEDIA_TYPES = {
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
}
MAX_DOCUMENT_BYTES = 4 * 1024 * 1024
MAX_LAYOUT_BYTES = 2 * 1024 * 1024 * 1024


def _read_regular(path: Path, maximum_bytes: int = MAX_DOCUMENT_BYTES) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("image fact input is not a regular file")
        if metadata.st_size > maximum_bytes:
            raise ValueError("image fact input exceeds byte allowance")
        chunks: list[bytes] = []
        total = 0
        while chunk := os.read(descriptor, min(1024 * 1024, maximum_bytes + 1 - total)):
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum_bytes:
                raise ValueError("image fact input exceeds byte allowance")
        if total != metadata.st_size:
            raise ValueError("image fact input changed while reading")
    finally:
        os.close(descriptor)
    return b"".join(chunks)


def _verify_blob(path: Path, expected_digest: str, expected_size: object) -> int:
    if type(expected_size) is not int or expected_size < 0:
        raise ValueError("OCI layout blob size is invalid")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size != expected_size:
            raise ValueError("OCI layout blob size differs")
        digest = hashlib.sha256()
        total = 0
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
            total += len(chunk)
    finally:
        os.close(descriptor)
    if total != expected_size or f"sha256:{digest.hexdigest()}" != expected_digest:
        raise ValueError("OCI layout blob digest differs")
    return total


def _require_inventory(
    path: Path, *, regular_files: set[str], directories: set[str]
) -> None:
    observed: set[str] = set()
    with os.scandir(path) as entries:
        for entry in entries:
            if entry.name in regular_files:
                if not entry.is_file(follow_symlinks=False):
                    raise ValueError("OCI layout inventory contains non-regular file")
            elif entry.name in directories:
                if not entry.is_dir(follow_symlinks=False):
                    raise ValueError("OCI layout inventory contains non-directory")
            else:
                raise ValueError("OCI layout inventory contains unexpected entry")
            observed.add(entry.name)
    if observed != regular_files | directories:
        raise ValueError("OCI layout inventory is incomplete")


def _bytes(
    path: Path, expected_digest: str, *, trim_final_newline: bool = True
) -> bytes:
    data = _read_regular(path)
    if trim_final_newline and data.endswith(b"\n"):
        data = data[:-1]
    if f"sha256:{hashlib.sha256(data).hexdigest()}" != expected_digest:
        raise ValueError("manifest digest differs")
    return data


def select_child(path: Path, expected_digest: str) -> None:
    value = json.loads(_bytes(path, expected_digest))
    matches = [
        item
        for item in value.get("manifests", [])
        if item.get("platform", {}).get("os") == "linux"
        and item.get("platform", {}).get("architecture") == "amd64"
        and item.get("annotations", {}).get("vnd.docker.reference.type")
        != "attestation-manifest"
    ]
    if len(matches) != 1 or DIGEST.fullmatch(str(matches[0].get("digest"))) is None:
        raise ValueError("linux/amd64 child manifest differs")
    print(matches[0]["digest"])


def manifest_fact(
    path: Path,
    expected_digest: str,
    repository: str,
    *,
    trim_final_newline: bool = True,
) -> None:
    data = _bytes(path, expected_digest, trim_final_newline=trim_final_newline)
    value = json.loads(data)
    media_type = value.get("mediaType")
    config_descriptor = value.get("config")
    config = (
        config_descriptor.get("digest")
        if isinstance(config_descriptor, dict)
        else None
    )
    if media_type not in MEDIA_TYPES or DIGEST.fullmatch(str(config)) is None:
        raise ValueError("platform manifest is invalid")
    print(
        json.dumps(
            {
                "repository": repository,
                "platform_manifest_digest": expected_digest,
                "platform_manifest_media_type": media_type,
                "platform_manifest_byte_count": len(data),
                "operating_system": "linux",
                "architecture": "amd64",
                "config_image_id": config,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def layout_fact(path: Path, expected_digest: str, repository: str) -> None:
    metadata = path.lstat()
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValueError("OCI layout root is not a directory")
    _require_inventory(
        path,
        regular_files={"index.json", "oci-layout"},
        directories={"blobs"},
    )
    for directory in (path / "blobs", path / "blobs" / "sha256"):
        if not stat.S_ISDIR(directory.lstat().st_mode):
            raise ValueError("OCI layout blob root is not a directory")
    _require_inventory(path / "blobs", regular_files=set(), directories={"sha256"})
    layout_bytes = _read_regular(path / "oci-layout")
    layout = json.loads(layout_bytes)
    if layout != {"imageLayoutVersion": "1.0.0"}:
        raise ValueError("OCI layout version differs")
    index_path = path / "index.json"
    index_bytes = _read_regular(index_path)
    index = json.loads(index_bytes)
    manifests = index.get("manifests")
    if (
        index.get("schemaVersion") != 2
        or not isinstance(manifests, list)
        or len(manifests) != 1
    ):
        raise ValueError("OCI layout index differs")
    descriptor = manifests[0]
    if not isinstance(descriptor, dict):
        raise ValueError("OCI layout manifest descriptor is invalid")
    if descriptor.get("digest") != expected_digest:
        raise ValueError("OCI layout manifest digest differs")
    manifest_path = path / "blobs" / "sha256" / expected_digest.removeprefix("sha256:")
    data = _bytes(manifest_path, expected_digest, trim_final_newline=False)
    if type(descriptor.get("size")) is not int or descriptor.get("size") != len(data):
        raise ValueError("OCI layout manifest size differs")
    manifest = json.loads(data)
    if not isinstance(manifest, dict):
        raise ValueError("OCI layout manifest is invalid")
    if descriptor.get("mediaType") != manifest.get("mediaType"):
        raise ValueError("OCI layout manifest media type differs")
    layers = manifest.get("layers")
    if not isinstance(layers, list):
        raise ValueError("OCI layout layer inventory differs")
    referenced = [manifest.get("config"), *layers]
    if not referenced or len(referenced) > 256:
        raise ValueError("OCI layout blob inventory differs")
    expected_blobs = {expected_digest.removeprefix("sha256:")}
    total = len(layout_bytes) + len(index_bytes) + len(data)
    if total > MAX_LAYOUT_BYTES:
        raise ValueError("OCI layout byte allowance exceeded")
    blob_sizes: dict[str, int] = {}
    for item in referenced:
        if (
            not isinstance(item, dict)
            or DIGEST.fullmatch(str(item.get("digest"))) is None
        ):
            raise ValueError("OCI layout blob descriptor is invalid")
        digest = str(item["digest"])
        size = item.get("size")
        if type(size) is not int or size < 0:
            raise ValueError("OCI layout blob size is invalid")
        if digest in blob_sizes and blob_sizes[digest] != size:
            raise ValueError("OCI layout duplicate blob size differs")
        blob_sizes[digest] = size
        expected_blobs.add(digest.removeprefix("sha256:"))
    _require_inventory(
        path / "blobs" / "sha256",
        regular_files=expected_blobs,
        directories=set(),
    )
    for digest, size in blob_sizes.items():
        if total + size > MAX_LAYOUT_BYTES:
            raise ValueError("OCI layout byte allowance exceeded")
        blob = path / "blobs" / "sha256" / digest.removeprefix("sha256:")
        total += _verify_blob(blob, digest, size)
    manifest_fact(
        manifest_path,
        expected_digest,
        repository,
        trim_final_newline=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="operation", required=True)
    child = subparsers.add_parser("select-child")
    child.add_argument("path", type=Path)
    child.add_argument("expected_digest")
    fact = subparsers.add_parser("manifest-fact")
    fact.add_argument("path", type=Path)
    fact.add_argument("expected_digest")
    fact.add_argument("repository")
    layout = subparsers.add_parser("layout-fact")
    layout.add_argument("path", type=Path)
    layout.add_argument("expected_digest")
    layout.add_argument("repository")
    arguments = parser.parse_args()
    if DIGEST.fullmatch(arguments.expected_digest) is None:
        raise SystemExit("expected digest is invalid")
    try:
        if arguments.operation == "select-child":
            select_child(arguments.path, arguments.expected_digest)
        elif arguments.operation == "manifest-fact":
            manifest_fact(
                arguments.path, arguments.expected_digest, arguments.repository
            )
        else:
            layout_fact(arguments.path, arguments.expected_digest, arguments.repository)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
