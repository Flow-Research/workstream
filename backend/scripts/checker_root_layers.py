"""Restricted trusted-platform root construction from an approved OCI graph.

Layer paths are inventory keys, never host extraction paths. Unsupported alias,
sparse, special-file or hardlink semantics fail closed instead of invoking an
external filesystem materializer.
"""
from dataclasses import dataclass
import gzip
import hashlib
import json
import os
import tarfile
import tempfile
import time

from scripts import checker_smol_cache as cache
from scripts.checker_image_process import ImageError


def available(deadline):
    if time.monotonic() >= deadline:
        raise ImageError("trusted root provisioning deadline exceeded")


def path_name(value):
    if (not value or len(value.encode()) > 4096 or value.startswith("/")
            or "\\" in value or "\0" in value
            or any(part in {"", ".", ".."} for part in value.split("/"))):
        raise ImageError("trusted root path invalid")
    return value


def link_target(path, target):
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


@dataclass(frozen=True)
class RootEntry:
    """A normalized entry; regular content refers only to our private byte spool."""

    kind: str
    size: int = 0
    sha256: str = ""
    executable: bool = False
    offset: int = 0
    target: str = ""


def _delete(tree, name, children_only=False):
    if name and name not in tree:
        return
    if name and tree[name].kind != "directory":
        if not children_only:
            del tree[name]
        return
    prefix = name + "/" if name else ""
    for path in list(tree):
        if (not children_only and path == name) or path.startswith(prefix):
            del tree[path]


def _parents(tree, name, create=False):
    parts = name.split("/")
    for index in range(1, len(parts)):
        parent = "/".join(parts[:index])
        if parent in tree and tree[parent].kind != "directory":
            raise ImageError("trusted layer has a nondirectory ancestor")
        if create:
            tree.setdefault(parent, RootEntry("directory"))


def _layer_entries(layer, remaining_entries, deadline):
    entries, seen, whiteouts = [], set(), []
    count = 0
    for item in layer:
        available(deadline)
        count += 1
        if count > remaining_entries:
            raise ImageError("trusted layer aggregate entry limit exceeded")
        name = item.name.removeprefix("./").removesuffix("/") if item.isdir() else item.name.removeprefix("./")
        if name in {"", "."} and item.isdir():
            if "." in seen:
                raise ImageError("trusted layer root directory duplicated")
            seen.add(".")
            continue
        path_name(name)
        if name in seen or item.issparse() or not (item.isdir() or item.isfile() or item.issym() or item.islnk()):
            raise ImageError("trusted layer entry invalid")
        seen.add(name)
        if item.size < 0 or (not item.isfile() and item.size):
            raise ImageError("trusted layer entry size invalid")
        parent, _, basename = name.rpartition("/")
        if basename.startswith(".wh."):
            if not item.isfile() or item.size:
                raise ImageError("trusted layer whiteout invalid")
            if basename == ".wh..wh..opq":
                whiteouts.append((parent, True))
            else:
                target = basename[4:]
                path_name(target)
                whiteouts.append((parent + "/" + target if parent else target, False))
        else:
            entries.append((name, item))
    layer.fileobj.seek(layer.offset)
    trailer_size = 0
    while chunk := layer.fileobj.read(65536):
        available(deadline)
        trailer_size += len(chunk)
        if any(chunk):
            raise ImageError("trusted layer trailing content invalid")
    if trailer_size < 1024 or trailer_size % 512:
        raise ImageError("trusted layer trailer truncated")
    return entries, whiteouts, count


def apply_layer(layer_file, spool, tree, *, maximum_entries, remaining_entries, deadline):
    """Apply lower-layer deletion first, then additions in their declared order."""
    with tarfile.open(fileobj=layer_file, mode="r:") as layer:
        entries, whiteouts, count = _layer_entries(layer, remaining_entries, deadline)
        for target, opaque in whiteouts:
            available(deadline)
            _parents(tree, target + "/marker" if opaque and target else target)
            _delete(tree, target, children_only=opaque)
        for name, item in entries:
            available(deadline)
            _parents(tree, name, create=True)
            if not (item.isdir() and name in tree and tree[name].kind == "directory"):
                _delete(tree, name)
            if item.isdir():
                entry = RootEntry("directory")
            elif item.issym():
                link_target(name, item.linkname)
                entry = RootEntry("symlink", target=item.linkname)
            elif item.islnk():
                target = path_name(item.linkname.removeprefix("./"))
                if target not in tree or tree[target].kind != "file":
                    raise ImageError("trusted layer hardlink target is not a known regular file")
                entry = tree[target]
            else:
                offset, digest, remaining = spool.tell(), hashlib.sha256(), item.size
                with layer.extractfile(item) as content:
                    while remaining:
                        available(deadline)
                        chunk = content.read(min(remaining, 65536))
                        if not chunk:
                            raise ImageError("trusted layer file truncated")
                        spool.write(chunk)
                        digest.update(chunk)
                        remaining -= len(chunk)
                entry = RootEntry("file", item.size, digest.hexdigest(), bool(item.mode & 0o111), offset)
            tree[name] = entry
            if len(tree) > maximum_entries:
                raise ImageError("trusted root implicit directory limit exceeded")
    return count


def construct_root(source, spool, *, manifest_digest, config_image_id,
                   maximum_layer_bytes, maximum_entries, deadline):
    """Reverify the graph and each consumed layer before returning its final inventory."""
    members = cache._preflight(source, os.fstat(source.fileno()).st_size)
    _, config_id, raw_config, wrapper, expected = cache._graph(
        source, members, manifest_digest, maximum_layer_bytes=maximum_layer_bytes, deadline=deadline)
    if config_id != config_image_id:
        raise ImageError("trusted root config differs")
    layers = json.loads(wrapper)[0]["Layers"]
    diff_ids = json.loads(raw_config)["rootfs"]["diff_ids"]
    tree, expanded, count = {}, 0, 0
    for name, diff_id in zip(layers, diff_ids, strict=True):
        available(deadline)
        raw = cache.MemberReader(source, members[name])
        magic = raw.read(2)
        raw = cache.MemberReader(source, members[name])
        reader = gzip.GzipFile(fileobj=raw) if magic == b"\x1f\x8b" else raw
        digest = hashlib.sha256()
        with tempfile.TemporaryFile() as layer:
            while chunk := reader.read(65536):
                available(deadline)
                expanded += len(chunk)
                if expanded > maximum_layer_bytes:
                    raise ImageError("trusted layer aggregate byte limit exceeded")
                layer.write(chunk)
                digest.update(chunk)
            if ("sha256:" + digest.hexdigest() != diff_id
                    or "sha256:" + raw.hash.hexdigest() != expected[name]):
                raise ImageError("trusted layer consumed identity differs")
            layer.seek(0)
            count += apply_layer(layer, spool, tree, maximum_entries=maximum_entries,
                                 remaining_entries=maximum_entries - count, deadline=deadline)
            layer.seek(0)
            if cache.digest(layer, deadline=deadline) != diff_id:
                raise ImageError("trusted layer spool identity differs")
    available(deadline)
    return tree
