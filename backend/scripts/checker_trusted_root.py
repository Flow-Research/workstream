"""Provision the trusted PRE interpreter from a verified image, without running it.

Docker is trusted offline build infrastructure. The produced bundle is not a
qualification receipt and is never accepted without its independently pinned
identity. No submitted archive or project image enters this command.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import struct
import tarfile
import tempfile
import time

from scripts import checker_smol_cache as cache
from scripts.checker_image_process import ExecutionBudget, ImageError, run

MAGIC = b"WSROOT1\n"
MAX_HEADER = 16384


def _path(value: str) -> str:
    if (not value or len(value.encode()) > 4096 or value.startswith("/")
            or "\\" in value or "\0" in value
            or any(part in {"", ".", ".."} for part in value.split("/"))):
        raise ImageError("trusted root path invalid")
    return value


def _frame(output, value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    if len(raw) > MAX_HEADER:
        raise ImageError("trusted root header exceeds limit")
    output.write(struct.pack(">I", len(raw)))
    output.write(raw)


def _link(path, target):
    if not target or "\0" in target or "\\" in target or len(target.encode()) > 4096:
        raise ImageError("trusted root link invalid")
    depth = 0 if target.startswith("/") else path.count("/")
    for part in target.split("/"):
        if part == "..":
            if depth == 0:
                raise ImageError("trusted root link escapes root")
            depth -= 1
        elif part not in {"", "."}:
            depth += 1


def _available(deadline):
    if deadline is not None and time.monotonic() >= deadline:
        raise ImageError("trusted root provisioning deadline exceeded")


def _members(archive, maximum_entries, maximum_bytes, deadline):
    members, total = {}, 0
    for index, item in enumerate(archive):
        _available(deadline)
        if index >= maximum_entries:
            raise ImageError("trusted root entry limit exceeded")
        name = item.name.removesuffix("/") if item.isdir() else item.name
        if name in {"", "."} and item.isdir():
            continue
        _path(name)
        if name in members or not (item.isdir() or item.isfile() or item.issym() or item.islnk()):
            raise ImageError("trusted root entry invalid")
        if item.size < 0 or (not item.isfile() and item.size):
            raise ImageError("trusted root entry size invalid")
        if item.issym():
            _link(name, item.linkname)
        total += item.size
        if total > maximum_bytes:
            raise ImageError("trusted root expanded byte limit exceeded")
        members[name] = item
    directories = set()
    for name in members:
        parts = name.split("/")
        for end in range(1, len(parts)):
            parent = "/".join(parts[:end])
            if parent in members and not members[parent].isdir():
                raise ImageError("trusted root has a nondirectory ancestor")
            directories.add(parent)
    directories.update(name for name, item in members.items() if item.isdir())
    if len(directories | members.keys()) > maximum_entries:
        raise ImageError("trusted root implicit directory limit exceeded")
    return members, directories


def _regular(name, members):
    visited = set()
    while True:
        if name in visited or name not in members:
            raise ImageError("trusted root hardlink invalid")
        visited.add(name)
        item = members[name]
        if item.isfile():
            return item
        if not item.islnk():
            raise ImageError("trusted root hardlink target is not regular")
        name = _path(item.linkname)


def pack_root(source, output, *, identity, maximum_entries, maximum_bytes, deadline=None):
    """Normalize a bounded Docker export; never extract paths onto the host."""
    if maximum_entries <= 0 or maximum_bytes <= 0:
        raise ImageError("trusted root bounds must be positive")
    output.write(MAGIC)
    _frame(output, {"kind": "identity", **identity})
    with tarfile.open(fileobj=source, mode="r:") as archive:
        members, directories = _members(archive, maximum_entries, maximum_bytes, deadline)
        for name in sorted(directories, key=lambda value: (value.count("/"), value)):
            _available(deadline)
            _frame(output, {"kind": "directory", "path": name})
        total, entries = 0, len(directories)
        for name, item in sorted(members.items()):
            _available(deadline)
            if not (item.isfile() or item.islnk()):
                continue
            regular = _regular(name, members)
            total += regular.size
            entries += 1
            if total > maximum_bytes:
                raise ImageError("trusted root hardlink expansion exceeds limit")
            _frame(output, {"kind": "file", "path": name, "byte_count": regular.size,
                            "executable": bool(regular.mode & 0o111)})
            with archive.extractfile(regular) as content:
                remaining = regular.size
                while remaining:
                    _available(deadline)
                    data = content.read(min(65536, remaining))
                    if not data:
                        raise ImageError("trusted root file truncated")
                    output.write(data)
                    remaining -= len(data)
        for name, item in sorted(members.items()):
            _available(deadline)
            if item.issym():
                entries += 1
                _frame(output, {"kind": "symlink", "path": name, "target": item.linkname})
        _frame(output, {"kind": "end"})
        _available(deadline)
    return {"expanded_bytes": total, "entries": entries}


def _inspect(docker, kind, selector, budget):
    raw = run([docker, kind, "inspect", selector], step="inspect trusted root custody", budget=budget)
    body = cache._json(raw)
    if type(body) is not list or len(body) != 1 or type(body[0]) is not dict:
        raise ImageError("trusted root inspection invalid")
    return body[0]


def _container_matches(value, config_id, token, container_id):
    return (value.get("Id") == container_id and value.get("Image") == config_id
            and value.get("Config", {}).get("Labels", {}).get("workstream.root-provision") == token
            and value.get("State", {}).get("Status") == "created"
            and value.get("State", {}).get("Running") is False)


def export_root(docker, config_id, config, sink, *, maximum_bytes, deadline):
    """Export a never-started exact image and clean only the invocation's container."""
    budget = ExecutionBudget(deadline, maximum_bytes + 1024 * 1024)
    image = _inspect(docker, "image", config_id, budget)
    if (image.get("Id") != config_id or image.get("Os") != "linux"
            or image.get("Architecture") != "amd64"
            or image.get("RootFS", {}).get("Layers") != config["rootfs"]["diff_ids"]
            or image.get("Config", {}).get("Volumes") or config.get("config", {}).get("Volumes")):
        raise ImageError("trusted root image differs")
    token = secrets.token_hex(16)
    name = "workstream-root-" + token
    container_id = None
    try:
        raw = run([docker, "create", "--pull=never", "--network=none", "--name", name,
                   "--label", "workstream.root-provision=" + token, config_id],
                  step="create trusted root export", budget=budget)
        container_id = raw.decode("ascii").strip()
        if re.fullmatch(r"[0-9a-f]{64}", container_id) is None:
            raise ImageError("trusted root container id invalid")
        value = _inspect(docker, "container", container_id, budget)
        if not _container_matches(value, config_id, token, container_id):
            raise ImageError("trusted root container differs")
        run([docker, "export", container_id], step="export trusted root", budget=budget,
            timeout=max(0.001, deadline - time.monotonic()),
            limit=maximum_bytes, stdout_sink=sink)
    finally:
        # A fresh cleanup budget is independent of an exhausted export budget.
        cleanup = ExecutionBudget(time.monotonic() + 30, 1024 * 1024)
        if container_id is None or re.fullmatch(r"[0-9a-f]{64}", container_id) is None:
            matches = run([docker, "ps", "-aq", "--no-trunc", "--filter", "name=^/" + name + "$",
                           "--filter", "label=workstream.root-provision=" + token],
                          step="discover trusted root export", budget=cleanup).decode().split()
            if len(matches) > 1:
                raise ImageError("trusted root cleanup discovery ambiguous")
            container_id = matches[0] if matches else None
        if container_id is not None:
            if re.fullmatch(r"[0-9a-f]{64}", container_id) is None:
                raise ImageError("trusted root discovered container id invalid")
            value = _inspect(docker, "container", container_id, cleanup)
            if not _container_matches(value, config_id, token, container_id):
                raise ImageError("trusted root cleanup ownership unconfirmed")
            run([docker, "rm", container_id], step="remove trusted root export", budget=cleanup)


def provision_root(archive: Path, repository: str, manifest_digest: str, *,
                   archive_output: Path, config_output: Path, bundle_output: Path,
                   descriptor_output: Path, docker: str, default_behavior_sha256: str,
                   maximum_export_bytes: int, maximum_root_bytes: int,
                   maximum_entries: int, timeout_seconds: float):
    """Bind an exclusive sealed runtime bundle to the already verified image graph."""
    if (any(type(value) is not int or value <= 0 for value in
            (maximum_export_bytes, maximum_root_bytes, maximum_entries))
            or not 0 < timeout_seconds <= 7200
            or cache.DIGEST.fullmatch(default_behavior_sha256) is None):
        raise ImageError("trusted root provisioning limits invalid")
    paths = [p.parent.resolve(strict=True) / p.name for p in
             (archive_output, config_output, bundle_output, descriptor_output)]
    if len(set(paths)) != 4 or archive.resolve(strict=True) in paths:
        raise ImageError("trusted root outputs must be distinct")
    deadline = time.monotonic() + timeout_seconds
    receipt = cache.provision(archive, repository, manifest_digest,
                              archive_output=archive_output, config_output=config_output)
    raw_config = config_output.read_bytes()
    if "sha256:" + hashlib.sha256(raw_config).hexdigest() != receipt["config_image_id"]:
        raise ImageError("trusted root config changed")
    config = cache._json(raw_config)
    identity = {"platform_manifest_digest": manifest_digest,
                "config_image_id": receipt["config_image_id"],
                "default_behavior_sha256": default_behavior_sha256}
    created = []
    try:
        with tempfile.TemporaryFile() as exported:
            export_root(docker, receipt["config_image_id"], config, exported,
                        maximum_bytes=maximum_export_bytes, deadline=deadline)
            exported.seek(0)
            with cache._output_files(paths[2:], created) as (bundle, descriptor):
                facts = pack_root(exported, bundle, identity=identity,
                                  maximum_entries=maximum_entries, maximum_bytes=maximum_root_bytes,
                                  deadline=deadline)
                bundle.flush()
                size = bundle.tell()
                bundle.seek(0)
                result = {"schema_version": "workstream.trusted_root.v1", **identity, **facts,
                          "bundle_sha256": cache.digest(bundle), "bundle_byte_count": size}
                _available(deadline)
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
    for option in ("repository", "manifest", "docker", "default-behavior-sha256"):
        parser.add_argument("--" + option, required=True)
    for option in ("maximum-export-bytes", "maximum-root-bytes", "maximum-entries"):
        parser.add_argument("--" + option, type=int, required=True)
    parser.add_argument("--timeout-seconds", type=float, required=True)
    args = vars(parser.parse_args())
    args["manifest_digest"] = args.pop("manifest")
    print(json.dumps(provision_root(**args), sort_keys=True))


if __name__ == "__main__":
    main()
