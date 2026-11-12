"""Provision the trusted PRE interpreter from a verified image, without running it.

The approved archive is the sole source of platform file contents. The produced bundle is not a
qualification receipt and is never accepted without its independently pinned
identity. No submitted archive or project image enters this command.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import stat
import tempfile
import time

from scripts import checker_smol_cache as cache
from scripts.checker_image_process import ImageError
from scripts.checker_root_layers import available, construct_root

MAGIC = b"WSROOT1\n"
MAX_HEADER = 16384


class _BundleWriter:
    """Bind the expected serialized bytes independently of the output file read."""

    def __init__(self, output):
        self.output, self.digest, self.count = output, hashlib.sha256(), 0

    def write(self, data):
        if self.output.write(data) != len(data):
            raise ImageError("trusted root output write incomplete")
        self.digest.update(data)
        self.count += len(data)


def _frame(output, value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    if len(raw) > MAX_HEADER:
        raise ImageError("trusted root header exceeds limit")
    output.write(struct.pack(">I", len(raw)))
    output.write(raw)


def pack_root(spool, output, *, tree, identity, maximum_bytes, deadline):
    """Write the verified final inventory, rehashing retained file content."""
    output.write(MAGIC)
    _frame(output, {"kind": "identity", **identity})
    directories = [name for name, entry in tree.items() if entry.kind == "directory"]
    for name in sorted(directories, key=lambda value: (value.count("/"), value)):
        available(deadline)
        _frame(output, {"kind": "directory", "path": name})
    total = 0
    for name, entry in sorted(tree.items()):
        available(deadline)
        if entry.kind != "file":
            continue
        total += entry.size
        if total > maximum_bytes:
            raise ImageError("trusted root expanded byte limit exceeded")
        _frame(output, {"kind": "file", "path": name, "byte_count": entry.size,
                        "executable": entry.executable})
        spool.seek(entry.offset)
        digest, remaining = hashlib.sha256(), entry.size
        while remaining:
            available(deadline)
            chunk = spool.read(min(remaining, 65536))
            if not chunk:
                raise ImageError("trusted root spool truncated")
            output.write(chunk)
            digest.update(chunk)
            remaining -= len(chunk)
        if digest.hexdigest() != entry.sha256:
            raise ImageError("trusted root retained file identity differs")
    for name, entry in sorted(tree.items()):
        available(deadline)
        if entry.kind == "symlink":
            _frame(output, {"kind": "symlink", "path": name, "target": entry.target})
    _frame(output, {"kind": "end"})
    available(deadline)
    return {"expanded_bytes": total, "entries": len(tree)}


def provision_root(archive: Path, repository: str, manifest_digest: str, *,
                   archive_output: Path, config_output: Path, bundle_output: Path,
                   descriptor_output: Path, default_behavior_sha256: str,
                   maximum_layer_bytes: int, maximum_root_bytes: int,
                   maximum_entries: int, timeout_seconds: float):
    """Bind an exclusive sealed runtime bundle to the already verified image graph."""
    if (any(type(value) is not int or value <= 0 for value in
            (maximum_layer_bytes, maximum_root_bytes, maximum_entries))
            or not 0 < timeout_seconds <= 7200
            or cache.DIGEST.fullmatch(default_behavior_sha256) is None):
        raise ImageError("trusted root provisioning limits invalid")
    paths = [p.parent.resolve(strict=True) / p.name for p in
             (archive_output, config_output, bundle_output, descriptor_output)]
    if len(set(paths)) != 4 or archive.resolve(strict=True) in paths:
        raise ImageError("trusted root outputs must be distinct")
    deadline = time.monotonic() + timeout_seconds
    receipt = cache.provision(archive, repository, manifest_digest,
                              archive_output=archive_output, config_output=config_output,
                              maximum_layer_bytes=maximum_layer_bytes, deadline=deadline)
    identity = {"platform_manifest_digest": manifest_digest,
                "config_image_id": receipt["config_image_id"],
                "default_behavior_sha256": default_behavior_sha256}
    created = []
    try:
        fd = os.open(paths[0], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as source, tempfile.TemporaryFile() as spool:
            metadata = os.fstat(source.fileno())
            if not stat.S_ISREG(metadata.st_mode):
                raise ImageError("trusted root cache is not regular")
            original = cache._identity(metadata)
            if cache.digest(source, deadline=deadline) != receipt["smol"]["archive_sha256"]:
                raise ImageError("trusted root source cache changed")
            source.seek(0)
            tree = construct_root(source, spool, manifest_digest=manifest_digest,
                                  config_image_id=receipt["config_image_id"],
                                  maximum_layer_bytes=maximum_layer_bytes,
                                  maximum_entries=maximum_entries, deadline=deadline)
            with cache._output_files(paths[2:], created) as (bundle, descriptor):
                writer = _BundleWriter(bundle)
                facts = pack_root(spool, writer, tree=tree, identity=identity,
                                  maximum_bytes=maximum_root_bytes, deadline=deadline)
                cache._unchanged(source, paths[0], original)
                source.seek(0)
                if cache.digest(source, deadline=deadline) != receipt["smol"]["archive_sha256"]:
                    raise ImageError("trusted root source cache changed")
                bundle.flush()
                size = bundle.tell()
                bundle.seek(0)
                observed_digest = cache.digest(bundle, deadline=deadline)
                if (observed_digest != "sha256:" + writer.digest.hexdigest() or size != writer.count):
                    raise ImageError("trusted root serialized output identity differs")
                result = {"schema_version": "workstream.trusted_root.v1", **identity, **facts,
                          "bundle_sha256": observed_digest, "bundle_byte_count": size}
                available(deadline)
                descriptor.write(json.dumps(result, sort_keys=True, separators=(",", ":")).encode())
                for output in (bundle, descriptor):
                    output.flush()
                    os.fchmod(output.fileno(), 0o400)
                    os.fsync(output.fileno())
                for path, device, inode in created:
                    info = path.lstat()
                    if (info.st_dev, info.st_ino) != (device, inode):
                        raise ImageError("trusted root publication changed")
            for parent in {path.parent for path in paths[2:]}:
                fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
        return result
    except BaseException:
        for path, device, inode in reversed(created):
            try:
                info = path.lstat()
                if (info.st_dev, info.st_ino) == (device, inode):
                    path.unlink()
            except FileNotFoundError:
                pass
        raise


def main():
    """Require explicit approved identities, output paths and provisioning bounds."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("archive", "archive-output", "config-output", "bundle-output", "descriptor-output"):
        parser.add_argument("--" + option, type=Path, required=True)
    for option in ("repository", "manifest", "default-behavior-sha256"):
        parser.add_argument("--" + option, required=True)
    for option in ("maximum-layer-bytes", "maximum-root-bytes", "maximum-entries"):
        parser.add_argument("--" + option, type=int, required=True)
    parser.add_argument("--timeout-seconds", type=float, required=True)
    args = vars(parser.parse_args())
    args["manifest_digest"] = args.pop("manifest")
    print(json.dumps(provision_root(**args), sort_keys=True))


if __name__ == "__main__":
    main()
