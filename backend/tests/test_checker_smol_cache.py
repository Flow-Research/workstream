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
    def substitute(bundle, source, name, member, expected):
        nonlocal changed
        if not changed:
            with archive.open("r+b") as attacker:
                attacker.seek(member.offset)
                original = attacker.read(1)
                attacker.seek(member.offset)
                attacker.write(bytes([original[0] ^ 1]))
            changed = True
        copy(bundle, source, name, member, expected)
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


def root_export(entries):
    """A flattened image export, independent of contributor ZIP handling."""
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        for name, kind, content in entries:
            item = tarfile.TarInfo(name)
            item.type = kind
            if kind == tarfile.REGTYPE:
                item.size = len(content)
                item.mode = 0o4755
                archive.addfile(item, io.BytesIO(content))
            else:
                if kind in {tarfile.SYMTYPE, tarfile.LNKTYPE}:
                    item.linkname = content
                archive.addfile(item)
    output.seek(0)
    return output


def test_trusted_root_bundle_normalizes_links_and_keeps_bytes():
    """Flattened hardlinks retain content; symlinks follow all file records."""
    import struct
    from scripts.checker_trusted_root import MAGIC, pack_root

    source = root_export([
        ("usr/bin/python", tarfile.REGTYPE, b"trusted interpreter"),
        ("usr/bin/python3", tarfile.LNKTYPE, "usr/bin/python"),
        ("bin", tarfile.SYMTYPE, "usr/bin"),
    ])
    output = io.BytesIO()
    facts = pack_root(source, output, identity={"test": "identity"},
                      maximum_entries=10, maximum_bytes=100)
    output.seek(0)
    assert output.read(len(MAGIC)) == MAGIC
    records, files = [], {}
    while raw := output.read(4):
        value = json.loads(output.read(struct.unpack(">I", raw)[0]))
        records.append(value)
        if value["kind"] == "file":
            files[value["path"]] = output.read(value["byte_count"])
    assert files == {"usr/bin/python": b"trusted interpreter", "usr/bin/python3": b"trusted interpreter"}
    assert [item["kind"] for item in records] == ["identity", "directory", "directory", "file", "file", "symlink", "end"]
    assert all(set(item) == {"kind", "path", "byte_count", "executable"}
               for item in records if item["kind"] == "file")
    assert facts == {"expanded_bytes": 38, "entries": 5}


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
])
def test_trusted_root_refuses_paths_special_files_and_link_ancestry(entries):
    from scripts.checker_trusted_root import pack_root

    with pytest.raises(ImageError):
        pack_root(root_export(entries), io.BytesIO(), identity={}, maximum_entries=20, maximum_bytes=100)


def test_trusted_root_charges_hardlink_expansion_and_implicit_directories():
    from scripts.checker_trusted_root import pack_root

    source = [("a/b/c", tarfile.REGTYPE, b"12345"), ("copy", tarfile.LNKTYPE, "a/b/c")]
    with pytest.raises(ImageError, match="hardlink expansion"):
        pack_root(root_export(source), io.BytesIO(), identity={}, maximum_entries=10, maximum_bytes=9)
    with pytest.raises(ImageError, match="implicit directory"):
        pack_root(root_export(source), io.BytesIO(), identity={}, maximum_entries=3, maximum_bytes=20)


@pytest.mark.parametrize("defect", [None, "image", "container", "container_id", "started", "export"])
def test_root_export_requires_exact_never_started_container_and_cleans_owned_id(monkeypatch, defect):
    import time
    from scripts import checker_trusted_root as root

    config_id, container_id = "sha256:" + "1" * 64, "2" * 64
    config = {"rootfs": {"diff_ids": ["sha256:" + "3" * 64]}}
    calls, state = [], {}

    def command(argv, **kwargs):
        calls.append(argv)
        if argv[1:3] == ["image", "inspect"]:
            return json.dumps([{"Id": "other" if defect == "image" else config_id,
                                "Os": "linux", "Architecture": "amd64",
                                "RootFS": {"Layers": config["rootfs"]["diff_ids"]}, "Config": {}}]).encode()
        if argv[1] == "create":
            assert "--pull=never" in argv and argv[-1] == config_id
            state["token"] = argv[argv.index("--label") + 1].split("=", 1)[1]
            return container_id.encode()
        if argv[1:3] == ["container", "inspect"]:
            return json.dumps([{"Id": "f" * 64 if defect == "container_id" else container_id,
                                "Image": "other" if defect == "container" else config_id,
                                "Config": {"Labels": {"workstream.root-provision": state["token"]}},
                                "State": {"Status": "running" if defect == "started" else "created", "Running": defect == "started"}}]).encode()
        if argv[1] == "export":
            assert 0 < kwargs["timeout"] <= 10
            if defect == "export":
                raise ImageError("export failed")
            kwargs["stdout_sink"].write(b"root bytes")
        elif argv[1] == "rm":
            assert argv == ["docker", "rm", container_id]
        else:
            pytest.fail(f"unexpected Docker command {argv}")
        return b""

    monkeypatch.setattr(root, "run", command)
    output = io.BytesIO()
    if defect:
        with pytest.raises(ImageError):
            root.export_root("docker", config_id, config, output, maximum_bytes=1000, deadline=time.monotonic() + 10)
    else:
        root.export_root("docker", config_id, config, output, maximum_bytes=1000, deadline=time.monotonic() + 10)
        assert output.getvalue() == b"root bytes"
    assert not any("start" in item or "pull" in item for item in calls)
    assert any(item[1] == "rm" for item in calls) == (defect in {None, "export"})
    assert any(item[1] == "export" for item in calls) == (defect in {None, "export"})


@pytest.mark.parametrize("failure", [False, True])
def test_trusted_root_publication_binds_verified_graph_and_removes_partial_bundle(tmp_path, monkeypatch, failure):
    from scripts import checker_trusted_root as root

    archive, manifest, config_id = bundle(tmp_path, volumes=False)
    def export(docker, selected_id, config, sink, **kwargs):
        assert selected_id == config_id
        assert config["rootfs"]["diff_ids"]
        sink.write(root_export([("python", tarfile.REGTYPE, b"trusted")]).read())
    monkeypatch.setattr(root, "export_root", export)
    kwargs = dict(archive_output=tmp_path / "cache.tar", config_output=tmp_path / "config.json",
                  bundle_output=tmp_path / "root.bundle", descriptor_output=tmp_path / "root.json",
                  docker="docker", default_behavior_sha256=sha(b"behavior"),
                  maximum_export_bytes=100000, maximum_root_bytes=1 if failure else 100,
                  maximum_entries=10, timeout_seconds=5)
    if failure:
        with pytest.raises(ImageError, match="expanded byte limit"):
            root.provision_root(archive, "trusted/intake", manifest, **kwargs)
        assert not kwargs["bundle_output"].exists()
        assert not kwargs["descriptor_output"].exists()
    else:
        receipt = root.provision_root(archive, "trusted/intake", manifest, **kwargs)
        assert receipt["config_image_id"] == config_id
        assert receipt["platform_manifest_digest"] == manifest
        assert receipt["bundle_sha256"] == sha(kwargs["bundle_output"].read_bytes())
        assert receipt["bundle_byte_count"] == kwargs["bundle_output"].stat().st_size
        assert json.loads(kwargs["descriptor_output"].read_bytes()) == receipt
        assert kwargs["bundle_output"].stat().st_mode & 0o777 == 0o400


def test_uncertain_root_container_creation_discovers_exact_owned_id_for_cleanup(monkeypatch):
    import time
    from scripts import checker_trusted_root as root

    image_id, container_id = sha(b"image"), "a" * 64
    diff_ids = [sha(b"layer")]
    state, calls = {}, []
    def command(argv, **kwargs):
        calls.append(argv)
        if argv[1:3] == ["image", "inspect"]:
            return json.dumps([{"Id": image_id, "Os": "linux", "Architecture": "amd64",
                                "RootFS": {"Layers": diff_ids}, "Config": {}}]).encode()
        if argv[1] == "create":
            state["token"] = argv[argv.index("--label") + 1].split("=", 1)[1]
            state["name"] = argv[argv.index("--name") + 1]
            raise ImageError("create acknowledgement lost")
        if argv[1] == "ps":
            assert "name=^/" + state["name"] + "$" in argv
            assert "label=workstream.root-provision=" + state["token"] in argv
            return container_id.encode()
        if argv[1:3] == ["container", "inspect"]:
            assert argv[-1] == container_id
            return json.dumps([{"Id": container_id, "Image": image_id, "State": {"Status": "created", "Running": False},
                                "Config": {"Labels": {"workstream.root-provision": state["token"]}}}]).encode()
        assert argv == ["docker", "rm", container_id]
        return b""
    monkeypatch.setattr(root, "run", command)
    with pytest.raises(ImageError, match="acknowledgement lost"):
        root.export_root("docker", image_id, {"rootfs": {"diff_ids": diff_ids}}, io.BytesIO(),
                         maximum_bytes=100, deadline=time.monotonic() + 10)
    assert calls[-1] == ["docker", "rm", container_id]
    assert not any(item[1] == "export" for item in calls)


def test_root_pack_cannot_publish_after_deadline():
    import time
    from scripts.checker_trusted_root import pack_root

    with pytest.raises(ImageError, match="deadline"):
        pack_root(root_export([("python", tarfile.REGTYPE, b"trusted")]), io.BytesIO(),
                  identity={}, maximum_entries=10, maximum_bytes=100, deadline=time.monotonic() - 1)
