"""The node cache must execute the complete approved image graph."""
import gzip
import hashlib
import io
import json
import tarfile

import pytest

from scripts.checker_image_process import ImageError
from scripts import checker_smol_cache as cache
from scripts.checker_smol_cache import provision


def sha(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def bundle(root, *, compressed=False, defect=None, volumes=True):
    layer_output = io.BytesIO()
    with tarfile.open(fileobj=layer_output, mode="w", format=tarfile.USTAR_FORMAT) as output:
        info = tarfile.TarInfo("usr/bin/checker")
        info.size = len(b"verified filesystem layer")
        output.addfile(info, io.BytesIO(b"verified filesystem layer"))
    layer = layer_output.getvalue()
    blob = gzip.compress(layer, mtime=0) if compressed else layer
    descriptor = {"mediaType": "application/vnd.oci.image.layer.v1.tar" + ("+gzip" if compressed else ""),
                  "digest": sha(blob), "size": len(blob)}
    config = json.dumps({"os": "linux", "architecture": "amd64",
                         "rootfs": {"type": "layers", "diff_ids": [sha(layer)]},
                         "config": {"Entrypoint": ["/checker"], "Volumes": {"/busybox": {}} if volumes else {}}}).encode()
    manifest = {"schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "config": {"digest": sha(config), "size": len(config),
                           "mediaType": "application/vnd.oci.image.config.v1+json"},
                "layers": [descriptor]}
    if defect == "wrong_schema":
        manifest["schemaVersion"] = 1
    if defect == "index":
        manifest["manifests"] = []
    if defect == "missing_approved_layer":
        descriptor["digest"] = sha(b"other layer")
    if defect == "wrong_size":
        descriptor["size"] += 1
    if defect == "missing_layers":
        del manifest["layers"]
    raw_manifest = json.dumps(manifest).encode()
    config_name = "blobs/sha256/" + sha(config)[7:]
    selected = b"substitution" if defect == "changed_rootfs" else blob
    entries = {config_name: config, "blobs/sha256/" + sha(raw_manifest)[7:]: raw_manifest,
               "manifest.json": json.dumps([{"Config": config_name, "Layers": ["selected-layer"],
                                             "RepoTags": None, "LayerSources": {"selected-layer": {}}}]).encode(),
               "index.json": b'{"compatibility":"ignored"}', "oci-layout": b'{}',
               "legacy-v1.json": b'{"id":"old","parent":"old","container_config":{}}',
               "selected-layer": selected, "blobs/sha256/" + sha(blob)[7:]: blob}
    path = root / "image.tar"
    with tarfile.open(path, "w", format=tarfile.USTAR_FORMAT) as output:
        for name in ("blobs", "blobs/sha256"):
            info = tarfile.TarInfo(name)
            info.type = tarfile.DIRTYPE
            output.addfile(info)
        for name, content in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            output.addfile(info, io.BytesIO(content))
    return path, sha(raw_manifest), sha(config)


@pytest.mark.parametrize("compressed", [False, True])
def test_plain_and_compressed_layers_bind_the_approved_graph(tmp_path, compressed):
    archive, manifest, config = bundle(tmp_path, compressed=compressed)
    before, permissions = archive.read_bytes(), archive.stat().st_mode
    receipt = provision(archive, "test/checker", manifest,
                        archive_output=tmp_path / "cache.tar", config_output=tmp_path / "config.json")
    assert receipt["config_image_id"] == config
    assert receipt["platform_manifest_digest"] == manifest
    assert receipt["smol"]["archive"] == str(tmp_path / "cache.tar")
    assert receipt["smol"]["archive_sha256"] == sha((tmp_path / "cache.tar").read_bytes())
    assert archive.read_bytes() == before and archive.stat().st_mode == permissions
    assert (tmp_path / "cache.tar").stat().st_mode & 0o777 == 0o400
    assert (tmp_path / "config.json").stat().st_mode & 0o777 == 0o400
    with tarfile.open(tmp_path / "cache.tar", "r:") as output:
        members = output.getmembers()
        wrapper = json.load(output.extractfile("manifest.json"))
        assert set(wrapper[0]) == {"Config", "RepoTags", "Layers"}
        assert wrapper[0]["RepoTags"] == []
        assert {item.name for item in members} == {
            "manifest.json", "blobs/sha256/" + manifest[7:],
            "blobs/sha256/" + config[7:], "selected-layer",
            "blobs/sha256/" + json.loads(output.extractfile("blobs/sha256/" + manifest[7:]).read())["layers"][0]["digest"][7:],
        }
        assert all(item.type == tarfile.REGTYPE and item.mode == 0o400
                   and item.uid == item.gid == item.mtime == 0
                   and item.uname == item.gname == "" for item in members)
        config_bytes = output.extractfile("blobs/sha256/" + config[7:]).read()
        assert (tmp_path / "config.json").read_bytes() == config_bytes
        assert json.loads(config_bytes)["config"]["Volumes"] == {"/busybox": {}}


@pytest.mark.parametrize("defect", ["wrong_schema", "index", "missing_layers",
                                    "missing_approved_layer", "wrong_size", "changed_rootfs"])
def test_manifest_and_rootfs_substitution_never_publish_a_cache_entry(tmp_path, defect):
    archive, manifest, _ = bundle(tmp_path, defect=defect)
    with pytest.raises(ImageError):
        provision(archive, "test/checker", manifest,
                  archive_output=tmp_path / "cache.tar", config_output=tmp_path / "config.json")
    assert not (tmp_path / "config.json").exists()
    assert not (tmp_path / "cache.tar").exists()


def prepare(archive, manifest, root):
    return provision(archive, "test/checker", manifest,
                     archive_output=root / "cache.tar", config_output=root / "config.json")


def append_members(archive, specifications):
    with tarfile.open(archive, "a", format=tarfile.USTAR_FORMAT) as output:
        for name, kind, body in specifications:
            info = tarfile.TarInfo(name)
            info.type, info.size = kind, len(body)
            if kind in {tarfile.SYMTYPE, tarfile.LNKTYPE}:
                info.linkname = "selected-layer"
            output.addfile(info, io.BytesIO(body))


@pytest.mark.parametrize("members", [
    [("blobs/", tarfile.DIRTYPE, b"")],
    [("a//b", tarfile.REGTYPE, b"")],
    [("./alias", tarfile.REGTYPE, b"")],
    [("../escape", tarfile.REGTYPE, b"")],
    [("/absolute", tarfile.REGTYPE, b"")],
    [("directory", tarfile.DIRTYPE, b"payload")],
    [("link", tarfile.SYMTYPE, b"")],
    [("link", tarfile.LNKTYPE, b"")],
    [("extension", tarfile.XHDTYPE, b"metadata")],
    [("extension", tarfile.GNUTYPE_LONGNAME, b"metadata")],
    [("extension", tarfile.GNUTYPE_SPARSE, b"metadata")],
    [("a", tarfile.REGTYPE, b""), ("a/b", tarfile.REGTYPE, b"")],
    [("a/b", tarfile.REGTYPE, b""), ("a", tarfile.REGTYPE, b"")],
    [("a", tarfile.REGTYPE, b""), ("a/b", tarfile.DIRTYPE, b"")],
    [("a/b", tarfile.DIRTYPE, b""), ("a", tarfile.REGTYPE, b"")],
])
def test_raw_preflight_refuses_unsafe_members_before_publishing(tmp_path, members):
    archive, manifest, _ = bundle(tmp_path)
    append_members(archive, members)
    with pytest.raises(ImageError):
        prepare(archive, manifest, tmp_path)
    assert not (tmp_path / "cache.tar").exists()
    assert not (tmp_path / "config.json").exists()


def test_header_ceiling_and_nonzero_trailer_are_not_ignored(tmp_path):
    archive, manifest, _ = bundle(tmp_path)
    original = archive.read_bytes()
    append_members(archive, [(f"directory-{index}", tarfile.DIRTYPE, b"") for index in range(4097)])
    with pytest.raises(ImageError, match="header limit"):
        prepare(archive, manifest, tmp_path)
    archive.write_bytes(original + b"x" * 512)
    with pytest.raises(ImageError, match="trailer"):
        prepare(archive, manifest, tmp_path)


@pytest.mark.parametrize("existing", ["cache.tar", "config.json"])
def test_exclusive_output_collisions_preserve_existing_files_and_source(tmp_path, existing):
    archive, manifest, _ = bundle(tmp_path)
    archive.chmod(0o640)
    original = archive.read_bytes(), archive.stat().st_mode
    (tmp_path / existing).write_bytes(b"foreign output")
    with pytest.raises(ImageError):
        prepare(archive, manifest, tmp_path)
    assert (tmp_path / existing).read_bytes() == b"foreign output"
    other = "config.json" if existing == "cache.tar" else "cache.tar"
    assert not (tmp_path / other).exists()
    assert (archive.read_bytes(), archive.stat().st_mode) == original


def test_output_aliases_and_symlinks_cannot_replace_source_or_foreign_data(tmp_path):
    archive, manifest, _ = bundle(tmp_path)
    alias = tmp_path / "alias"
    alias.symlink_to(tmp_path, target_is_directory=True)
    for archive_output, config_output in [
        (archive, tmp_path / "config.json"),
        (tmp_path / "cache.tar", archive),
        (tmp_path / "same", alias / "same"),
    ]:
        with pytest.raises(ImageError):
            provision(archive, "test/checker", manifest,
                      archive_output=archive_output, config_output=config_output)
    foreign = tmp_path / "foreign"
    foreign.write_bytes(b"preserved")
    (tmp_path / "cache.tar").symlink_to(foreign)
    with pytest.raises(ImageError):
        prepare(archive, manifest, tmp_path)
    assert (tmp_path / "cache.tar").is_symlink()
    assert foreign.read_bytes() == b"preserved"


def test_canonical_bytes_are_reproducible_and_source_permissions_are_unchanged(tmp_path):
    archive, manifest, _ = bundle(tmp_path, compressed=True)
    archive.chmod(0o640)
    original = archive.read_bytes(), archive.stat().st_mode
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    one = prepare(archive, manifest, first)
    two = prepare(archive, manifest, second)
    assert one["smol"]["archive_sha256"] == two["smol"]["archive_sha256"]
    assert (first / "cache.tar").read_bytes() == (second / "cache.tar").read_bytes()
    assert (first / "config.json").read_bytes() == (second / "config.json").read_bytes()
    assert (archive.read_bytes(), archive.stat().st_mode) == original


def test_mid_copy_failure_removes_both_owned_partials(tmp_path, monkeypatch):
    archive, manifest, _ = bundle(tmp_path)
    original = archive.read_bytes(), archive.stat().st_mode
    copy = cache._copy_member
    def fail(*args):
        copy(*args)
        raise ImageError("injected copy failure")
    monkeypatch.setattr(cache, "_copy_member", fail)
    with pytest.raises(ImageError, match="injected"):
        prepare(archive, manifest, tmp_path)
    assert not (tmp_path / "cache.tar").exists()
    assert not (tmp_path / "config.json").exists()
    assert (archive.read_bytes(), archive.stat().st_mode) == original


def test_copy_rehash_rejects_source_mutation_after_validation(tmp_path, monkeypatch):
    archive, manifest, _ = bundle(tmp_path)
    copy = cache._copy_member
    changed = False
    def substitute(bundle, source, name, member, expected, deadline=None):
        nonlocal changed
        if not changed:
            with archive.open("r+b") as attacker:
                attacker.seek(member.offset)
                original = attacker.read(1)
                attacker.seek(member.offset)
                attacker.write(bytes([original[0] ^ 1]))
            changed = True
        copy(bundle, source, name, member, expected, deadline)
    monkeypatch.setattr(cache, "_copy_member", substitute)
    with pytest.raises(ImageError, match="changed during copy"):
        prepare(archive, manifest, tmp_path)
    assert changed
    assert not (tmp_path / "cache.tar").exists()
    assert not (tmp_path / "config.json").exists()


def test_partial_cleanup_preserves_a_replaced_output_inode(tmp_path, monkeypatch):
    archive, manifest, _ = bundle(tmp_path)
    def replace(*_args):
        (tmp_path / "cache.tar").rename(tmp_path / "owned-away")
        (tmp_path / "cache.tar").write_bytes(b"foreign replacement")
        raise ImageError("replaced during copy")
    monkeypatch.setattr(cache, "_copy_member", replace)
    with pytest.raises(ImageError):
        prepare(archive, manifest, tmp_path)
    assert (tmp_path / "cache.tar").read_bytes() == b"foreign replacement"
    assert not (tmp_path / "config.json").exists()


def test_cli_requires_a_distinct_archive_output(tmp_path, monkeypatch, capsys):
    archive, manifest, _ = bundle(tmp_path)
    monkeypatch.setattr("sys.argv", ["checker_smol_cache", "--archive", str(archive),
                                   "--repository", "test/checker", "--manifest", manifest,
                                   "--config-output", str(tmp_path / "config.json")])
    with pytest.raises(SystemExit) as error:
        cache.main()
    assert error.value.code == 2
    assert "--archive-output" in capsys.readouterr().err
    assert not (tmp_path / "config.json").exists()


def root_layer(entries):
    """Construct a layer without extracting any image path on the host."""
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        for name, kind, content in entries:
            item = tarfile.TarInfo(name)
            item.type = kind
            if kind == tarfile.REGTYPE:
                item.size, item.mode = len(content), 0o4755
                archive.addfile(item, io.BytesIO(content))
            else:
                if kind in {tarfile.SYMTYPE, tarfile.LNKTYPE}:
                    item.linkname = content
                archive.addfile(item)
    output.seek(0)
    return output


def layered_root(layers, *, maximum_entries=100):
    import time
    from scripts.checker_root_layers import apply_layer

    spool, tree, consumed = io.BytesIO(), {}, 0
    for layer in layers:
        consumed += apply_layer(root_layer(layer), spool, tree, maximum_entries=maximum_entries,
                                remaining_entries=maximum_entries - consumed, deadline=time.monotonic() + 5)
    return spool, tree


def root_contents(spool, tree):
    result = {}
    for path, entry in tree.items():
        if entry.kind == "file":
            spool.seek(entry.offset)
            result[path] = spool.read(entry.size)
    return result


def test_layered_root_replacements_preserve_existing_hardlink_content():
    spool, tree = layered_root([
        [("a", tarfile.REGTYPE, b"old"), ("alias", tarfile.LNKTYPE, "a")],
        [("a", tarfile.REGTYPE, b"new")],
    ])
    assert root_contents(spool, tree) == {"a": b"new", "alias": b"old"}


@pytest.mark.parametrize("marker_first", [False, True])
def test_whiteouts_apply_only_to_lower_layers_regardless_of_tar_order(marker_first):
    addition = [("d/new", tarfile.REGTYPE, b"new")]
    markers = [("d/.wh..wh..opq", tarfile.REGTYPE, b""), (".wh.old", tarfile.REGTYPE, b"")]
    spool, tree = layered_root([
        [("d/old", tarfile.REGTYPE, b"old"), ("old", tarfile.REGTYPE, b"old"),
         ("keep", tarfile.REGTYPE, b"keep")],
        markers + addition if marker_first else addition + markers,
    ])
    assert root_contents(spool, tree) == {"d/new": b"new", "keep": b"keep"}
    assert not any(".wh." in name for name in tree)


def test_directory_replacement_removes_old_descendants_and_directory_merge_keeps_them():
    spool, tree = layered_root([
        [("d/old", tarfile.REGTYPE, b"old"), ("kept/file", tarfile.REGTYPE, b"keep")],
        [("d", tarfile.REGTYPE, b"file"), ("kept", tarfile.DIRTYPE, "")],
    ])
    assert root_contents(spool, tree) == {"d": b"file", "kept/file": b"keep"}


@pytest.mark.parametrize("entries", [
    [("../escape", tarfile.REGTYPE, b"x")],
    [("/escape", tarfile.REGTYPE, b"x")],
    [("x", tarfile.REGTYPE, b"x"), ("x", tarfile.REGTYPE, b"y")],
    [("a", tarfile.SYMTYPE, "/outside"), ("a/b", tarfile.REGTYPE, b"x")],
    [("a", tarfile.LNKTYPE, "b"), ("b", tarfile.LNKTYPE, "a")],
    [("a", tarfile.SYMTYPE, "b"), ("b", tarfile.LNKTYPE, "a")],
    [("device", tarfile.CHRTYPE, "")],
    [("safe/escape", tarfile.SYMTYPE, "../../outside")],
    [("escape", tarfile.SYMTYPE, "/../outside")],
    [(".wh.", tarfile.REGTYPE, b"")],
    [(".wh...", tarfile.REGTYPE, b"")],
    [(".wh.x", tarfile.REGTYPE, b"not empty")],
    [(".wh.x", tarfile.SYMTYPE, "x")],
])
def test_trusted_layers_refuse_paths_links_whiteouts_and_special_entries(entries):
    with pytest.raises(ImageError):
        layered_root([entries])


def test_trusted_root_charges_implicit_directories_and_replaced_entries():
    with pytest.raises(ImageError, match="implicit directory"):
        layered_root([[("a/b/c", tarfile.REGTYPE, b"x")]], maximum_entries=2)
    with pytest.raises(ImageError, match="aggregate entry"):
        layered_root([[("a", tarfile.REGTYPE, b"old")], [("a", tarfile.REGTYPE, b"new")]], maximum_entries=1)


def test_root_bundle_rehashes_spool_and_charges_hardlink_expansion():
    import time
    from scripts.checker_trusted_root import pack_root

    spool, tree = layered_root([[("a", tarfile.REGTYPE, b"good"), ("b", tarfile.LNKTYPE, "a")]])
    kwargs = dict(tree=tree, identity={}, deadline=time.monotonic() + 5)
    with pytest.raises(ImageError, match="expanded byte"):
        pack_root(spool, io.BytesIO(), maximum_bytes=7, **kwargs)
    spool.seek(0)
    spool.write(b"evil")
    with pytest.raises(ImageError, match="retained file identity"):
        pack_root(spool, io.BytesIO(), maximum_bytes=8, **kwargs)


@pytest.mark.parametrize("failure", [False, True])
def test_root_publication_uses_only_approved_layers_and_removes_partial_bundle(tmp_path, monkeypatch, failure):
    import subprocess
    from scripts.checker_trusted_root import provision_root

    archive, manifest, config_id = bundle(tmp_path, volumes=False)
    def no_process(*args, **kwargs):
        pytest.fail("verified-layer provisioning invoked a filesystem materializer")
    monkeypatch.setattr(subprocess, "Popen", no_process)
    kwargs = dict(archive_output=tmp_path / "cache.tar", config_output=tmp_path / "config.json",
                  bundle_output=tmp_path / "root.bundle", descriptor_output=tmp_path / "root.json",
                  default_behavior_sha256=sha(b"behavior"), maximum_archive_bytes=1000000, maximum_layer_bytes=100000,
                  maximum_root_bytes=1 if failure else 100, maximum_entries=10, timeout_seconds=5)
    if failure:
        with pytest.raises(ImageError, match="expanded byte limit"):
            provision_root(archive, "trusted/intake", manifest, **kwargs)
        assert not kwargs["bundle_output"].exists()
        assert not kwargs["descriptor_output"].exists()
    else:
        receipt = provision_root(archive, "trusted/intake", manifest, **kwargs)
        assert receipt["config_image_id"] == config_id
        assert receipt["platform_manifest_digest"] == manifest
        assert receipt["bundle_sha256"] == sha(kwargs["bundle_output"].read_bytes())
        assert b"verified filesystem layer" in kwargs["bundle_output"].read_bytes()
        assert json.loads(kwargs["descriptor_output"].read_bytes()) == receipt
        assert kwargs["bundle_output"].stat().st_mode & 0o777 == 0o400


def test_layer_deadline_applies_before_parsing():
    import time
    from scripts.checker_root_layers import apply_layer

    with pytest.raises(ImageError, match="deadline"):
        apply_layer(root_layer([("python", tarfile.REGTYPE, b"trusted")]), io.BytesIO(), {},
                    maximum_entries=10, remaining_entries=10, deadline=time.monotonic() - 1)


@pytest.mark.parametrize("compressed", [False, True])
def test_verified_root_is_deterministic_and_layer_expansion_is_bounded(tmp_path, compressed):
    from scripts.checker_trusted_root import provision_root

    archive, manifest, _ = bundle(tmp_path, compressed=compressed, volumes=False)
    def build(prefix, maximum=100000):
        return provision_root(archive, "trusted/intake", manifest,
                              archive_output=tmp_path / (prefix + ".tar"), config_output=tmp_path / (prefix + ".config"),
                              bundle_output=tmp_path / (prefix + ".bundle"), descriptor_output=tmp_path / (prefix + ".json"),
                              default_behavior_sha256=sha(b"behavior"), maximum_archive_bytes=1000000, maximum_layer_bytes=maximum,
                              maximum_root_bytes=100, maximum_entries=10, timeout_seconds=5)
    first, second = build("one"), build("two")
    assert first == second
    assert (tmp_path / "one.bundle").read_bytes() == (tmp_path / "two.bundle").read_bytes()
    with pytest.raises(ImageError, match="verification byte limit"):
        build("limited", maximum=1024)
    assert not (tmp_path / "limited.bundle").exists()
    assert not (tmp_path / "limited.tar").exists()


def test_trusted_layer_rejects_content_hidden_after_tar_end_and_missing_trailer():
    import time
    from scripts.checker_root_layers import apply_layer

    raw = root_layer([("a", tarfile.REGTYPE, b"data")]).getvalue()
    for changed in [raw + b"hidden", raw[:1024]]:
        with pytest.raises(ImageError, match="length|trai|unexpected end"):
            apply_layer(io.BytesIO(changed), io.BytesIO(), {}, maximum_entries=10,
                        remaining_entries=10, deadline=time.monotonic() + 5)


@pytest.mark.parametrize("mutation", ["layer_spool", "serialized_file"])
def test_changed_materialization_cannot_be_published_under_the_same_image_identity(tmp_path, monkeypatch, mutation):
    """The real daemon mismatch must not recur at an intermediate local boundary."""
    from scripts import checker_root_layers as layers
    from scripts import checker_trusted_root as root

    archive, manifest, _ = bundle(tmp_path, volumes=False)
    if mutation == "layer_spool":
        original = layers.apply_layer
        def changed(layer, *args, **kwargs):
            result = original(layer, *args, **kwargs)
            layer.seek(512)
            layer.write(b"X")
            return result
        monkeypatch.setattr(layers, "apply_layer", changed)
        reason = "layer spool identity"
    else:
        original = root.pack_root
        def changed(spool, writer, **kwargs):
            result = original(spool, writer, **kwargs)
            writer.output.flush()
            writer.output.seek(0)
            data = writer.output.read()
            offset = data.index(b"verified filesystem layer")
            writer.output.seek(offset)
            writer.output.write(b"X")
            writer.output.seek(len(data))
            return result
        monkeypatch.setattr(root, "pack_root", changed)
        reason = "serialized output identity"
    with pytest.raises(ImageError, match=reason):
        root.provision_root(archive, "trusted/intake", manifest,
                            archive_output=tmp_path / "cache.tar", config_output=tmp_path / "config.json",
                            bundle_output=tmp_path / "root.bundle", descriptor_output=tmp_path / "root.json",
                            default_behavior_sha256=sha(b"behavior"), maximum_archive_bytes=1000000, maximum_layer_bytes=100000,
                            maximum_root_bytes=100, maximum_entries=10, timeout_seconds=5)
    assert not (tmp_path / "root.bundle").exists()
    assert not (tmp_path / "root.json").exists()


def test_outer_archive_bound_and_deadline_apply_before_zero_trailer_reads(tmp_path):
    import time

    class Unreadable(io.BytesIO):
        def read(self, *args):
            pytest.fail("preflight read beyond its admitted size/deadline")
    with pytest.raises(ImageError, match="archive byte limit"):
        cache._preflight(Unreadable(), 1024 * 1024 * 1024, maximum_bytes=1024)
    with pytest.raises(ImageError, match="preflight deadline"):
        cache._preflight(Unreadable(), 1024, maximum_bytes=1024, deadline=time.monotonic() - 1)
    class ExpiringTrailer(io.BytesIO):
        def read(self, size=-1):
            result = super().read(size)
            time.sleep(0.01)
            return result
    with pytest.raises(ImageError, match="preflight deadline"):
        cache._preflight(ExpiringTrailer(b"\0" * 2048), 2048,
                         maximum_bytes=2048, deadline=time.monotonic() + 0.005)


def test_root_outer_bound_rejects_padding_before_any_cache_publication(tmp_path):
    from scripts.checker_trusted_root import provision_root

    archive, manifest, _ = bundle(tmp_path)
    original_size = archive.stat().st_size
    with archive.open("ab") as output:
        output.write(b"\0" * 10240)
    with pytest.raises(ImageError, match="archive byte limit"):
        provision_root(archive, "trusted/intake", manifest,
                       archive_output=tmp_path / "cache.tar", config_output=tmp_path / "config.json",
                       bundle_output=tmp_path / "root.bundle", descriptor_output=tmp_path / "root.json",
                       default_behavior_sha256=sha(b"behavior"), maximum_archive_bytes=original_size,
                       maximum_layer_bytes=100000, maximum_root_bytes=100, maximum_entries=10, timeout_seconds=5)
    assert not (tmp_path / "cache.tar").exists()
    assert not (tmp_path / "root.bundle").exists()


def pax_layer(attributes):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.PAX_FORMAT) as archive:
        item = tarfile.TarInfo("placeholder")
        item.pax_headers, item.size = attributes, 4
        archive.addfile(item, io.BytesIO(b"code"))
    output.seek(0)
    return output


def test_pax_path_override_is_supported_and_each_physical_header_is_charged():
    import time
    from scripts.checker_root_layers import apply_layer

    spool, tree = io.BytesIO(), {}
    count = apply_layer(pax_layer({"path": "usr/é.py"}), spool, tree, maximum_entries=2,
                        remaining_entries=2, deadline=time.monotonic() + 5)
    assert count == 2
    assert root_contents(spool, tree) == {"usr/é.py": b"code"}
    with pytest.raises(ImageError, match="aggregate entry limit"):
        apply_layer(pax_layer({"path": "usr/é.py"}), io.BytesIO(), {}, maximum_entries=2,
                    remaining_entries=1, deadline=time.monotonic() + 5)


@pytest.mark.parametrize("attributes", [
    {"comment": "surprise"}, {"size": "4"}, {"GNU.sparse.name": "a"},
    {"path": "a" * 17000},
])
def test_unsupported_or_oversized_pax_is_refused_before_tarfile_interpretation(monkeypatch, attributes):
    import time
    from scripts.checker_root_layers import apply_layer

    source = pax_layer(attributes)
    def forbidden(*args, **kwargs):
        pytest.fail("tarfile interpreted unsupported extension metadata")
    monkeypatch.setattr(tarfile, "open", forbidden)
    with pytest.raises(ImageError, match="PAX"):
        apply_layer(source, io.BytesIO(), {}, maximum_entries=10,
                    remaining_entries=10, deadline=time.monotonic() + 5)


@pytest.mark.parametrize("kind", ["stacked", "global", "dangling"])
def test_pax_envelopes_cannot_stack_or_escape_the_next_entry(monkeypatch, kind):
    import time
    from scripts.checker_root_layers import apply_layer

    raw = pax_layer({"path": "renamed"}).getvalue()
    if kind == "stacked":
        raw = raw[:1024] + raw
    elif kind == "dangling":
        raw = raw[:1024] + b"\0" * 1024
    else:
        header = tarfile.TarInfo.frombuf(raw[:512], "utf-8", "strict")
        header.type = tarfile.XGLTYPE
        raw = header.tobuf(format=tarfile.USTAR_FORMAT) + raw[512:]
    def forbidden(*args, **kwargs):
        pytest.fail("tarfile interpreted an invalid extension envelope")
    monkeypatch.setattr(tarfile, "open", forbidden)
    with pytest.raises(ImageError, match="PAX|trailer|header type"):
        apply_layer(io.BytesIO(raw), io.BytesIO(), {}, maximum_entries=10,
                    remaining_entries=10, deadline=time.monotonic() + 5)
