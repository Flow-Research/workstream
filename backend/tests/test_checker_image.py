"""Publishing must bind the tested image, fail before side effects, and retain uncertain evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import time

import pytest

from app.modules.checkers.api.external import (
    ExternalCheckerExecutionRequest,
    ExternalCheckerRegistrySpec,
    make_external_checker_execution_result,
)
from scripts import checker_image as cli
from scripts.checker_image_process import ExecutionBudget, ImageError, run
from scripts.checker_image_samples import load_descriptor, snapshot_sample

IMAGE = "sha256:" + "a" * 64
URI = "123456789012.dkr.ecr.eu-north-1.amazonaws.com/workstream-checker-pre-example"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Two local samples with different expected semantic outcomes."""
    context = tmp_path / "project"
    context.mkdir()
    (context / "Dockerfile").write_text("FROM scratch\n")
    for name in ("good", "bad"):
        (context / name).mkdir()
        (context / name / "answer.txt").write_text(name)
    descriptor = {
        "project": "example",
        "capability_id": "example.answer",
        "capability_version": "v1",
        "phase": "pre_submit",
        "configuration_schema": {"type": "object"},
        "input_schema": {"type": "object"},
        "resources": {
            "cpu_millis": 500,
            "memory_bytes": 134217728,
            "deadline_ms": 1000,
            "maximum_output_bytes": 32768,
        },
        "samples": [
            {
                "name": "good",
                "directory": "good",
                "expected": "passed",
                "input": {"sample": "good"},
                "configuration": {},
            },
            {
                "name": "bad",
                "directory": "bad",
                "expected": "failed",
                "expected_codes": ["example.bad"],
                "input": {"sample": "bad"},
                "configuration": {},
            },
        ],
    }
    (context / "checker.json").write_text(json.dumps(descriptor))
    return context


class FakeDocker:
    """Transport double; real public models still validate every request and result."""

    def __init__(self):
        self.calls = []
        self.failure = None
        self.pulled = False
        self.removed = False
        self.manifest = json.dumps(
            {
                "schemaVersion": 2,
                "mediaType": cli.MANIFEST_TYPES[0],
                "config": {"digest": IMAGE, "size": 1,
                           "mediaType": "application/vnd.oci.image.config.v1+json"},
                "layers": [],
            }
        )
        self.digest = "sha256:" + hashlib.sha256(self.manifest.encode()).hexdigest()
        self.reference = URI + "@" + self.digest

    def inspect(self, image, **kwargs):
        if self.removed:
            raise ImageError("published image identity was removed")
        return json.loads(self.call("image", "inspect", image, step="inspect image", **kwargs))

    def image(self):
        return {
            "Id": IMAGE,
            "Os": "linux",
            "Architecture": "amd64",
            "Config": {},
            "RepoDigests": [self.reference],
        }

    def call(self, *args, step, **kwargs):
        self.calls.append((args, kwargs))
        budget = kwargs.get("budget")
        if budget and time.monotonic() >= budget.deadline:
            raise ImageError("sample deadline exceeded")
        output = self.response(*args, step=step, **kwargs)
        if budget:
            budget.charge(len(output))
        return output

    def response(self, *args, step, **kwargs):
        if args[:2] == ("image", "rm"):
            self.removed = True
        if "pull" in args:
            self.pulled = True
        if args[:2] == ("image", "inspect"):
            return json.dumps(self.image()).encode()
        if args[0] == "info":
            return b'{"runc":{}}'
        if args[0] == "build":
            Path(args[args.index("--iidfile") + 1]).write_text(IMAGE)
        if args[0] == "create":
            assert args[-1] == IMAGE
            mount = args[args.index("--mount") + 1]
            assert mount.endswith(",dst=/work/input,readonly")
            directory = Path(mount.split("src=")[1].split(",dst=")[0])
            assert (directory / "answer.txt").stat().st_mode & 0o222 == 0
            return b"c" * 64 + b"\n"
        if args[0] == "start":
            if self.failure == "timeout":
                raise ImageError("execute sample: deadline exceeded")
            if self.failure == "invalid":
                return b'{"outcome":"completed"}'
            request = ExternalCheckerExecutionRequest.model_validate_json(kwargs["data"])
            if request.registry.image_digest != IMAGE:
                assert self.pulled and not self.removed
            bad = request.input["sample"] == "bad"
            if self.failure == "digest_branch" and request.registry.image_digest != IMAGE:
                bad = not bad
            findings = (
                [
                    {
                        "check_id": "example.answer",
                        "code": "example.bad",
                        "level": "error",
                        "message": "sample rejected",
                        "path": "answer.txt",
                        "line": None,
                    }
                ]
                if bad
                else []
            )
            if self.failure == "wrong_code" and bad:
                findings[0]["code"] = "example.unexpected"
            result = make_external_checker_execution_result(
                request_digest=request.request_digest,
                registry_entry_id=request.registry.registry_entry_id,
                registry_entry_digest=request.registry.entry_digest,
                phase=request.identity.phase,
                outcome="completed",
                verdict="failed" if bad else "passed",
                findings=tuple(findings),
                infrastructure_failure_code=None,
            )
            return result.model_dump_json().encode()
        if args[0] == "inspect":
            return b'{"Running":false,"OOMKilled":false,"ExitCode":0}'
        if args[0:2] == ("container", "ls") and self.failure == "cleanup":
            return b"owned-container-still-exists\n"
        if "push" in args:
            if self.failure == "push":
                raise ImageError("push tested image: deadline exceeded")
            return f"checked: digest: {self.digest} size: 200\n".encode()
        return b""


@pytest.fixture
def transport(monkeypatch):
    docker = FakeDocker()
    monkeypatch.setattr(cli, "Docker", lambda config: docker)
    calls = []

    def aws(region, *args):
        calls.append((region, args))
        assert len([c for c, _ in docker.calls if c[0] == "start"]) == 2
        if args[0] == "sts":
            return b'{"Account":"123456789012"}'
        if args[1] == "describe-repositories":
            return json.dumps({"repositories": [{"repositoryUri": URI}]}).encode()
        if args[1] == "get-login-password":
            return b"private-fixture-password\n"
        if args[1] == "batch-get-image":
            return json.dumps(
                {
                    "images": [
                        {
                            "imageManifest": docker.manifest,
                            "imageManifestMediaType": cli.MANIFEST_TYPES[0],
                            "imageId": {"imageDigest": docker.digest},
                        }
                    ]
                }
            ).encode()
        raise AssertionError(args)

    monkeypatch.setattr(cli, "aws", aws)
    return docker, calls


@pytest.mark.parametrize("phase", ["pre_submit", "post_submit"])
def test_dry_run_validates_both_phases_without_any_aws(project, transport, tmp_path, phase):
    path = project / "checker.json"
    value = json.loads(path.read_text())
    value["phase"] = phase
    path.write_text(json.dumps(value))
    output = tmp_path / "release"
    assert cli.main([str(project), "--out", str(output)]) == 0
    docker, aws_calls = transport
    assert not aws_calls
    assert len([c for c, _ in docker.calls if c[0] == "build"]) == 1
    assert [
        item["verdict"] for item in json.loads((output / "receipt.json").read_text())["samples"]
    ] == ["passed", "failed"]
    assert sorted(p.name for p in output.iterdir()) == ["receipt.json"]


def test_publish_verifies_exact_image_and_rechecks_digest_before_outputs(
    project, transport, tmp_path, capsys
):
    output = tmp_path / "release"
    assert (
        cli.main([str(project), "--publish", "--account-id", "123456789012", "--out", str(output)])
        == 0
    )
    docker, _ = transport
    calls = [c for c, _ in docker.calls]
    assert len([c for c in calls if c[0] == "build"]) == 1
    assert len([c for c in calls if c[0] == "start"]) == 4
    assert next(c for c in calls if c[0] == "tag")[1] == IMAGE
    push = next(c for c in calls if "push" in c)
    assert push[push.index("--platform") + 1] == "linux/amd64"
    login_args, login_options = next(c for c in docker.calls if "login" in c[0])
    assert "private-fixture-password" not in str(login_args)
    assert login_options["data"] == b"private-fixture-password\n"
    auth_path = Path(login_args[1])
    assert not auth_path.exists()
    assert "private-fixture-password" not in capsys.readouterr().out
    spec = ExternalCheckerRegistrySpec.model_validate_json((output / "registry.json").read_bytes())
    cache = json.loads((output / "cache-entry.json").read_text())
    receipt = json.loads((output / "receipt.json").read_text())
    assert spec.image_digest == cache["platform_manifest_digest"] == docker.digest
    assert cache["config_image_id"] == IMAGE
    assert receipt["publication"] == "verified"
    assert docker.pulled and not docker.removed
    assert not any(c[:2] == ("image", "rm") for c in calls)


@pytest.mark.parametrize("failure", ["invalid", "wrong_code", "timeout", "cleanup"])
def test_failed_sample_or_cleanup_prevents_all_aws_calls(project, transport, tmp_path, failure):
    docker, aws_calls = transport
    docker.failure = failure
    output = tmp_path / "release"
    assert (
        cli.main([str(project), "--publish", "--account-id", "123456789012", "--out", str(output)])
        == 1
    )
    assert not aws_calls
    assert any(c[0:2] == ("rm", "--force") for c, _ in docker.calls)
    assert not (output / "registry.json").exists()


@pytest.mark.parametrize("failure", ["push", "digest_branch"])
def test_uncertain_or_unqualified_publication_retains_identity_without_registry_output(
    project, transport, tmp_path, failure
):
    docker, _ = transport
    docker.failure = failure
    output = tmp_path / "release"
    assert (
        cli.main([str(project), "--publish", "--account-id", "123456789012", "--out", str(output)])
        == 1
    )
    receipt = json.loads((output / "receipt.json").read_text())
    assert receipt["status"] == "failed"
    assert receipt["publication"] in {"uncertain", "published_unverified"}
    assert receipt["repository"] == URI
    assert receipt["publication_tag"].startswith("checked-")
    assert not (output / "registry.json").exists()
    assert not (output / "cache-entry.json").exists()
    assert len([c for c, _ in docker.calls if "push" in c]) == 1


@pytest.mark.parametrize("mutation", ["index", "config", "digest"])
def test_manifest_identity_rejects_substitution(mutation):
    docker = FakeDocker()
    manifest = json.loads(docker.manifest)
    if mutation == "index":
        manifest.update(mediaType="application/vnd.oci.image.index.v1+json", manifests=[])
    elif mutation == "config":
        manifest["config"]["digest"] = "sha256:" + "b" * 64
    raw = json.dumps(manifest)
    digest = "sha256:" + hashlib.sha256(raw.encode()).hexdigest()
    if mutation == "digest":
        digest = "sha256:" + "c" * 64
    response = {
        "images": [
            {
                "imageManifest": raw,
                "imageManifestMediaType": manifest["mediaType"],
                "imageId": {"imageDigest": digest},
            }
        ]
    }
    with pytest.raises(ImageError):
        cli.verify_manifest(response, digest, IMAGE)


@pytest.mark.parametrize("conflicting", [False, True])
def test_ecr_multiple_tags_preserve_one_exact_manifest_identity(conflicting):
    """ECR can return multiple tag rows for a single digest, but never different bytes."""
    docker = FakeDocker()
    rows = [
        {
            "imageManifest": docker.manifest,
            "imageManifestMediaType": cli.MANIFEST_TYPES[0],
            "imageId": {"imageDigest": docker.digest, "imageTag": tag},
        }
        for tag in ("checked-first", "checked-second")
    ]
    if conflicting:
        rows[1]["imageManifest"] += " "
        with pytest.raises(ImageError, match="conflicting"):
            cli.verify_manifest({"images": rows}, docker.digest, IMAGE)
    else:
        assert cli.verify_manifest({"images": rows}, docker.digest, IMAGE) == (
            cli.MANIFEST_TYPES[0],
            len(docker.manifest.encode()),
        )


def test_existing_output_is_never_overwritten(project, transport, tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    receipt = output / "receipt.json"
    receipt.write_text("retain this evidence")
    assert cli.main([str(project), "--out", str(output)]) == 1
    assert receipt.read_text() == "retain this evidence"
    assert not transport[0].calls


def test_sample_links_and_negative_without_expected_findings_are_rejected(project, tmp_path):
    (project / "good" / "link").symlink_to(project / "bad" / "answer.txt")
    with pytest.raises(ImageError, match="symlink"):
        snapshot_sample(project / "good", tmp_path / "snapshot")
    descriptor = json.loads((project / "checker.json").read_text())
    descriptor["samples"][1]["expected_codes"] = []
    (project / "checker.json").write_text(json.dumps(descriptor))
    with pytest.raises(ImageError, match="finding codes"):
        load_descriptor(project)


def test_sandbox_profile_matches_existing_service_restrictions(project, transport, tmp_path):
    assert cli.main([str(project), "--out", str(tmp_path / "out")]) == 0
    args = next(c for c, _ in transport[0].calls if c[0] == "create")
    pairs = {
        "--network": "none",
        "--cap-drop": "ALL",
        "--security-opt": "no-new-privileges",
        "--tmpfs": "/tmp:rw,noexec,nosuid,nodev,size=16777216",
    }
    service = (
        Path(__file__).parents[2] / "external_checkers/workstream-checker-service/src/main.rs"
    ).read_text()
    for flag, value in pairs.items():
        assert args[args.index(flag) + 1] == value
        assert json.dumps(flag) in service and json.dumps(value) in service
    for flag in ("--read-only", "--user", "--pids-limit", "--memory", "--cpus", "--mount"):
        assert flag in args and json.dumps(flag) in service
    assert args[args.index("--user") + 1].split(":")[0] != "0"
    assert not any("docker.sock" in item for item in args)


@pytest.mark.parametrize(
    "program,limit,timeout",
    [
        ("import time; time.sleep(30)", 1000, 0.2),
        ("import os; os.write(2,b'x'*20000)", 1000, 5),
    ],
)
def test_child_deadline_and_combined_output_are_bounded(program, limit, timeout):
    start = time.monotonic()
    with pytest.raises(ImageError):
        run([sys.executable, "-c", program], step="bounded probe", limit=limit, timeout=timeout)
    assert time.monotonic() - start < 10


@pytest.mark.parametrize("failure", ["identity", "preflight"])
def test_account_mismatch_and_aws_preflight_failure_never_login_or_push(
    project, transport, tmp_path, monkeypatch, failure
):
    """Wrong credentials cannot select a destination or conceal an attempted publication."""

    def aws(region, *args):
        if failure == "preflight":
            raise ImageError("AWS sts: command exited 1")
        return b'{"Account":"999999999999"}'

    monkeypatch.setattr(cli, "aws", aws)
    output = tmp_path / "release"
    assert (
        cli.main([str(project), "--publish", "--account-id", "123456789012", "--out", str(output)])
        == 1
    )
    assert not any("login" in c or "push" in c or c[0] == "tag" for c, _ in transport[0].calls)
    receipt = json.loads((output / "receipt.json").read_text())
    assert receipt["publication"] == "preflight"
    assert receipt["expected_account_id"] == "123456789012"
    assert not (output / "registry.json").exists()


def test_image_inspection_and_cleanup_share_the_sample_output_budget(project, transport, tmp_path):
    """Control output alone can exhaust a valid registry limit before execution."""
    path = project / "checker.json"
    value = json.loads(path.read_text())
    value["resources"]["maximum_output_bytes"] = 256
    path.write_text(json.dumps(value))
    output = tmp_path / "release"
    assert (
        cli.main([str(project), "--publish", "--account-id", "123456789012", "--out", str(output)])
        == 1
    )
    docker, aws_calls = transport
    assert not aws_calls
    assert not any(c[0] == "start" for c, _ in docker.calls)
    assert "aggregate output" in json.loads((output / "receipt.json").read_text())["error"]


def test_combined_stderr_is_charged_across_processes():
    """Individually small commands cannot each reuse the full request allowance."""
    budget = ExecutionBudget(time.monotonic() + 5, 150)
    command = [sys.executable, "-c", "import os; os.write(2,b'x'*100)"]
    run(command, step="inspect", budget=budget)
    with pytest.raises(ImageError, match="aggregate output"):
        run(command, step="create", budget=budget)


def test_active_healthcheck_is_rejected_without_disabling_it(monkeypatch, tmp_path):
    """Qualification cannot silently remove image behavior present in production."""
    monkeypatch.setenv("DOCKER_HOST", "unix:///var/run/docker.sock")
    docker = cli.Docker(tmp_path / "config")
    image = FakeDocker().image()
    image["Config"] = {"Healthcheck": {"Test": ["CMD", "false"]}}
    monkeypatch.setattr(docker, "call", lambda *a, **kw: json.dumps(image).encode())
    with pytest.raises(ImageError, match="HEALTHCHECK"):
        docker.inspect(IMAGE)


def test_build_and_samples_do_not_inherit_docker_proxy_configuration(monkeypatch, tmp_path):
    """A user's Docker config and proxy environment never enter build or sample calls."""
    host_config = tmp_path / "host-config"
    host_config.mkdir()
    user_plugins = host_config / "cli-plugins"
    user_plugins.mkdir()
    extra_plugins = tmp_path / "extra-plugins"
    extra_plugins.mkdir()
    marker = "https://user:private-marker@proxy.example"
    (host_config / "config.json").write_text(
        json.dumps(
            {
                "proxies": {"default": {"httpsProxy": marker}},
                "auths": {"registry.example": {"auth": "private-login-marker"}},
                "credsStore": "host-helper",
                "cliPluginsExtraDirs": [str(extra_plugins)],
            }
        )
    )
    monkeypatch.setenv("DOCKER_HOST", "unix:///var/run/docker.sock")
    monkeypatch.setenv("DOCKER_CONFIG", str(host_config))
    monkeypatch.setenv("HTTPS_PROXY", marker)
    calls = []
    monkeypatch.setattr(cli, "run", lambda argv, **kw: calls.append((argv, kw)) or b"")
    config = tmp_path / "private-config"
    docker = cli.Docker(config)
    docker.call("build", ".", step="build")
    docker.call("create", IMAGE, step="sample")
    assert json.loads((config / "config.json").read_text()) == {
        "cliPluginsExtraDirs": [str(extra_plugins), str(user_plugins)]
    }
    for argv, options in calls:
        assert argv[argv.index("--config") + 1] == str(config)
        assert marker not in str(options["env"])
        assert "DOCKER_CONFIG" not in options["env"]
