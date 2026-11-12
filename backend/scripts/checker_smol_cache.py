#!/usr/bin/env python3
"""Verify an approved image graph and write a canonical Smol cache archive.

No pulling, registration, policy mutation or extraction is performed. Source
Docker-save metadata is not authority; approved graph bytes remain unchanged.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import tarfile
import time

from scripts.checker_image_manifest import DIGEST, verify_platform_manifest
from scripts.checker_image_process import ImageError

MAX_METADATA = 10 * 1024 * 1024
MAX_WRAPPER = 1024 * 1024
MAX_HEADERS = 4096
BLOCK = 512


def _counted_digest(stream, maximum_bytes=None, deadline=None):
    value, count = hashlib.sha256(), 0
    while chunk := stream.read(1024 * 1024):
        count += len(chunk)
        if maximum_bytes is not None and count > maximum_bytes:
            raise ImageError("image verification byte limit exceeded")
        if deadline is not None and time.monotonic() >= deadline:
            raise ImageError("image verification deadline exceeded")
        value.update(chunk)
    if deadline is not None and time.monotonic() >= deadline:
        raise ImageError("image verification deadline exceeded")
    return "sha256:" + value.hexdigest(), count


def digest(stream, *, maximum_bytes=None, deadline=None) -> str:
    return _counted_digest(stream, maximum_bytes, deadline)[0]


@dataclass(frozen=True)
class Member:
    offset: int
    size: int


class MemberReader:
    """Read one preflighted regular member without interpreting tar extensions."""

    def __init__(self, source, member: Member):
        self.source, self.member, self.position = source, member, 0
        self.hash = hashlib.sha256()

    def read(self, size=-1):
        remaining = self.member.size - self.position
        size = remaining if size < 0 else min(size, remaining)
        self.source.seek(self.member.offset + self.position)
        data = self.source.read(size)
        if len(data) != size:
            raise ImageError("image member changed while reading")
        self.position += len(data)
        self.hash.update(data)
        return data


def _text(field: bytes) -> str:
    value, separator, padding = field.partition(b"\0")
    if separator and any(padding):
        raise ImageError("noncanonical archive text")
    return value.decode("ascii")


def _number(field: bytes) -> int:
    value = field.strip(b"\0 ")
    if not value or any(item not in b"01234567" for item in value):
        raise ImageError("invalid archive number")
    return int(value, 8)


def _path(name: str) -> None:
    if (not name or len(name) > 255 or name.startswith("/")
            or re.fullmatch(r"[A-Za-z0-9._:/-]+", name) is None
            or any(part in {"", ".", ".."} for part in name.split("/"))):
        raise ImageError("noncanonical archive path")


def _preflight(source, length: int) -> dict[str, Member]:
    """Bound raw headers before any tar parser can consume extension metadata."""
    if not length or length % BLOCK:
        raise ImageError("invalid archive length")
    files, directories, ancestors = {}, set(), set()
    offset = count = 0
    while offset + BLOCK <= length:
        source.seek(offset)
        header = source.read(BLOCK)
        if len(header) != BLOCK:
            raise ImageError("archive changed during preflight")
        if not any(header):
            if length - offset < 2 * BLOCK:
                raise ImageError("archive trailer is incomplete")
            source.seek(offset)
            remaining = length - offset
            while remaining:
                chunk = source.read(min(remaining, 1024 * 1024))
                if not chunk or any(chunk):
                    raise ImageError("archive trailer contains data")
                remaining -= len(chunk)
            return files
        count += 1
        if count > MAX_HEADERS:
            raise ImageError("archive header limit exceeded")
        if (_number(header[148:156]) != sum(header[:148]) + 8 * 32 + sum(header[156:])
                or header[257:265] != b"ustar\x0000"
                or header[156:157] not in {b"0", b"\0", b"5"}
                or any(header[157:257])):
            raise ImageError("unsupported archive header")
        name, prefix = _text(header[:100]), _text(header[345:500])
        name = f"{prefix}/{name}" if prefix else name
        directory = header[156:157] == b"5"
        if directory and name.endswith("/"):
            name = name[:-1]
        _path(name)
        size = _number(header[124:136])
        if name in files or (directory and (size != 0 or name in directories)):
            raise ImageError("duplicate or invalid archive member")
        if not directory and (name in directories or name in ancestors):
            raise ImageError("archive file conflicts with a directory")
        parent = name
        while "/" in parent:
            parent = parent.rsplit("/", 1)[0]
            if parent in files:
                raise ImageError("archive ancestor is a file")
            ancestors.add(parent)
        data = offset + BLOCK
        offset = data + (size + BLOCK - 1) // BLOCK * BLOCK
        if offset > length:
            raise ImageError("archive member exceeds input")
        if directory:
            directories.add(name)
        else:
            files[name] = Member(data, size)
    raise ImageError("archive trailer is missing")


def _json(raw: bytes):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ImageError("duplicate image metadata key")
            value[key] = item
        return value
    return json.loads(raw, object_pairs_hook=unique)


def _graph(source, members, manifest_digest, *, maximum_layer_bytes=None, deadline=None):
    def regular(name):
        _path(name)
        return MemberReader(source, members[name])

    def metadata(name, maximum=MAX_METADATA):
        if not 0 < members[name].size <= maximum:
            raise ImageError("image metadata exceeds limit")
        return regular(name).read()

    platform_path = "blobs/sha256/" + manifest_digest.removeprefix("sha256:")
    raw_manifest = metadata(platform_path, MAX_WRAPPER)
    _json(raw_manifest)
    manifest = verify_platform_manifest(raw_manifest, manifest_digest)
    config_id = manifest["config"]["digest"]
    config_path = "blobs/sha256/" + config_id[7:]
    raw_config = metadata(config_path)
    if ("sha256:" + hashlib.sha256(raw_config).hexdigest() != config_id
            or len(raw_config) != manifest["config"]["size"]):
        raise ImageError("config descriptor differs")
    config = _json(raw_config)
    if ((config["os"], config["architecture"]) != ("linux", "amd64")
            or config["rootfs"]["type"] != "layers"
            or manifest["config"]["mediaType"] not in {
                "application/vnd.oci.image.config.v1+json",
                "application/vnd.docker.container.image.v1+json"}):
        raise ImageError("unsupported image configuration")
    saved = _json(metadata("manifest.json"))
    if not isinstance(saved, list) or len(saved) != 1 or saved[0]["Config"] != config_path:
        raise ImageError("archive must contain exactly the approved image")
    layers, descriptors, diff_ids = saved[0]["Layers"], manifest["layers"], config["rootfs"]["diff_ids"]
    if (not isinstance(layers, list) or not isinstance(diff_ids, list) or not layers
            or len(layers) != len(diff_ids) or len(layers) != len(descriptors)):
        raise ImageError("rootfs layer count differs")
    expected = {platform_path: manifest_digest, config_path: config_id}
    approved_layers = set()
    remaining = maximum_layer_bytes
    for name, diff_id, descriptor in zip(layers, diff_ids, descriptors, strict=True):
        if not isinstance(diff_id, str) or DIGEST.fullmatch(diff_id) is None:
            raise ImageError("rootfs digest is invalid")
        approved = "blobs/sha256/" + descriptor["digest"][7:]
        if (approved in approved_layers or descriptor["size"] <= 0
                or members[approved].size != descriptor["size"]
                or descriptor["mediaType"] not in {
                    "application/vnd.oci.image.layer.v1.tar",
                    "application/vnd.oci.image.layer.v1.tar+gzip",
                    "application/vnd.docker.image.rootfs.diff.tar.gzip"}):
            raise ImageError("approved layer descriptor differs")
        approved_layers.add(approved)
        for selected, approved_digest in ((approved, descriptor["digest"]), (name, None)):
            if not isinstance(selected, str) or selected == "manifest.json":
                raise ImageError("invalid selected layer")
            raw_digest = digest(regular(selected), maximum_bytes=maximum_layer_bytes, deadline=deadline)
            if approved_digest is not None and raw_digest != approved_digest:
                raise ImageError("approved layer blob digest differs")
            reader = regular(selected)
            magic = reader.read(2)
            reader = regular(selected)
            expanded = gzip.GzipFile(fileobj=reader) if magic == b"\x1f\x8b" else reader
            observed, count = _counted_digest(expanded, remaining, deadline)
            if remaining is not None:
                remaining -= count
            if observed != diff_id:
                raise ImageError("rootfs layer digest differs")
            if selected in expected and expected[selected] != raw_digest:
                raise ImageError("image graph path conflicts")
            expected[selected] = raw_digest
    wrapper = json.dumps([{"Config": config_path, "RepoTags": [], "Layers": layers}],
                         sort_keys=True, separators=(",", ":")).encode()
    if len(wrapper) > MAX_WRAPPER or len(expected) + 1 > MAX_HEADERS:
        raise ImageError("canonical image metadata exceeds limit")
    return manifest, config_id, raw_config, wrapper, expected


def _identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _unchanged(source, archive, original):
    if (_identity(os.fstat(source.fileno())) != original
            or _identity(archive.lstat()) != original):
        raise ImageError("source archive changed")


def _tar_info(name, size):
    info = tarfile.TarInfo(name)
    info.size, info.mode, info.uid, info.gid, info.mtime = size, 0o400, 0, 0, 0
    info.uname = info.gname = ""
    info.type = tarfile.REGTYPE
    info.tobuf(format=tarfile.USTAR_FORMAT)  # Refuse implicit PAX/GNU extensions.
    return info


def _copy_member(bundle, source, name, member, expected_digest):
    reader = MemberReader(source, member)
    bundle.addfile(_tar_info(name, member.size), reader)
    if reader.position != member.size or "sha256:" + reader.hash.hexdigest() != expected_digest:
        raise ImageError("source image graph changed during copy")


def provision(archive: Path, repository: str, manifest_digest: str, *,
              archive_output: Path, config_output: Path,
              maximum_layer_bytes=None, deadline=None) -> dict:
    created = []
    try:
        if DIGEST.fullmatch(manifest_digest) is None:
            raise ImageError("platform manifest digest is invalid")
        archive = archive.resolve(strict=True)
        outputs = [path.parent.resolve(strict=True) / path.name for path in (archive_output, config_output)]
        if outputs[0] == outputs[1] or archive in outputs:
            raise ImageError("cache outputs must be distinct from each other and source")
        descriptor = os.open(archive, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as source:
            before = os.fstat(source.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ImageError("source archive is not regular")
            identity = _identity(before)
            members = _preflight(source, before.st_size)
            manifest, config_id, raw_config, wrapper, expected = _graph(
                source, members, manifest_digest, maximum_layer_bytes=maximum_layer_bytes, deadline=deadline)
            for name in expected:
                _tar_info(name, members[name].size)
            _unchanged(source, archive, identity)
            with _output_files(outputs, created) as (cache, config):
                with tarfile.open(fileobj=cache, mode="w", format=tarfile.USTAR_FORMAT) as bundle:
                    bundle.addfile(_tar_info("manifest.json", len(wrapper)), io.BytesIO(wrapper))
                    for name in sorted(expected):
                        _copy_member(bundle, source, name, members[name], expected[name])
                # This body is the same approved config copied and rehashed above.
                config.write(raw_config)
                _unchanged(source, archive, identity)
                for output in (cache, config):
                    output.flush()
                    os.fchmod(output.fileno(), 0o400)
                    os.fsync(output.fileno())
                cache.seek(0)
                archive_digest = digest(cache)
                for path, device, inode in created:
                    current = path.lstat()
                    if (current.st_dev, current.st_ino) != (device, inode):
                        raise ImageError("cache output identity changed")
            for parent in {path.parent for path in outputs}:
                directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
    except BaseException as error:
        cleanup_failed = False
        for path, device, inode in reversed(created):
            try:
                current = path.lstat()
                if (current.st_dev, current.st_ino) == (device, inode):
                    path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                cleanup_failed = True
        if cleanup_failed:
            raise ImageError("image cache partial cleanup failed") from error
        if isinstance(error, (OSError, ValueError, KeyError, TypeError, EOFError, RecursionError, tarfile.TarError)):
            raise ImageError("image cache preparation failed") from error
        raise
    return {
        "repository": repository,
        "platform_manifest_digest": manifest_digest,
        "platform_manifest_media_type": manifest["mediaType"],
        "platform_manifest_byte_count": members["blobs/sha256/" + manifest_digest[7:]].size,
        "config_image_id": config_id,
        "operating_system": "linux", "architecture": "amd64",
        "smol": {"archive": str(outputs[0]), "archive_sha256": archive_digest,
                 "image_config": str(outputs[1])},
    }


@contextmanager
def _output_files(paths, created):
    with ExitStack() as stack:
        handles = []
        for path in paths:
            descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
            info = os.fstat(descriptor)
            created.append((path, info.st_dev, info.st_ino))
            handles.append(stack.enter_context(os.fdopen(descriptor, "w+b")))
        yield handles


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--archive-output", type=Path, required=True)
    parser.add_argument("--config-output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(provision(args.archive, args.repository, args.manifest,
                               archive_output=args.archive_output, config_output=args.config_output)))


if __name__ == "__main__":
    main()
