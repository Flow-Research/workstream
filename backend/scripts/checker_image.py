#!/usr/bin/env python3
"""Build and test a project checker; optionally publish the tested image to ECR."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import signal
import sys
import tempfile
import time
from uuid import uuid4

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import ValidationError

from app.modules.checkers.api.external import ExternalCheckerExecutionResult
from scripts.checker_image_process import ExecutionBudget, ImageError, run
from scripts.checker_image_manifest import DIGEST, MANIFEST_TYPES, verify_platform_manifest
from scripts.checker_image_samples import (
    Descriptor,
    load_descriptor,
    sample_directory,
    sample_request,
    snapshot_sample,
)



def decode(raw: bytes):
    """Decode command JSON without reflecting credentials or arbitrary output."""
    try:
        return json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise ImageError("command returned invalid JSON") from exc


class Docker:
    """One explicit local daemon for build, compatibility tests and publication."""

    def __init__(self, config: Path) -> None:
        host = os.environ.get("DOCKER_HOST")
        if not host:
            host = decode(
                run(
                    ["docker", "context", "inspect", "--format", "{{json .Endpoints.docker.Host}}"],
                    step="resolve Docker daemon",
                )
            )
        if not isinstance(host, str) or not host.startswith("unix:///"):
            raise ImageError("use a local Docker Unix socket so sample mounts name local files")
        original = Path(os.environ.get("DOCKER_CONFIG") or Path.home() / ".docker")
        original_file = original / "config.json"
        settings = decode(original_file.read_bytes()) if original_file.is_file() else {}
        if not isinstance(settings, dict):
            raise ImageError("Docker client configuration must be an object")
        extra = settings.get("cliPluginsExtraDirs") or []
        if not isinstance(extra, list) or not all(isinstance(path, str) for path in extra):
            raise ImageError("Docker plugin search paths must be a list of directories")
        # Keep the operator's plugin discovery order, never proxy or login settings.
        plugin_dirs = [
            str(Path(path).resolve())
            for path in [*extra, str(original / "cli-plugins")]
            if Path(path).is_dir()
        ]
        config.mkdir(mode=0o700)
        (config / "config.json").write_text(json.dumps({"cliPluginsExtraDirs": plugin_dirs}) + "\n")
        self.prefix = ["docker", "--host", host, "--config", str(config)]
        self.env = {
            k: v
            for k, v in os.environ.items()
            if k not in {"DOCKER_CONTEXT", "DOCKER_CONFIG"} and not k.lower().endswith("_proxy")
        }

    def call(self, *arguments: str, step: str, **kwargs) -> bytes:
        """Use the selected daemon without shell interpolation or automatic retries."""
        return run([*self.prefix, *arguments], step=step, env=self.env, **kwargs)

    def inspect(self, image: str, **kwargs) -> dict:
        """Read the exact local image identity and configuration."""
        value = decode(
            self.call(
                "image", "inspect", "--format", "{{json .}}", image, step="inspect image", **kwargs
            )
        )
        if not isinstance(value, dict) or not DIGEST.fullmatch(value.get("Id", "")):
            raise ImageError("Docker returned an invalid image identity")
        if value.get("Os") != "linux" or value.get("Architecture") not in {"amd64", "arm64"}:
            raise ImageError("checker image must target linux/amd64 or linux/arm64")
        if value.get("Config", {}).get("Volumes"):
            raise ImageError("checker images cannot declare writable VOLUME mounts")
        healthcheck = value.get("Config", {}).get("Healthcheck", {}).get("Test", [])
        if healthcheck and healthcheck != ["NONE"]:
            raise ImageError("checker images cannot declare an active HEALTHCHECK")
        return value


def test_sample(docker: Docker, image_id: str, request, directory: Path, runtime: str,
                evidence: dict, checkpoint) -> bytes:
    """Exercise image compatibility under the closed sandbox profile, then confirm cleanup."""
    limits = request.registry.resources
    name = "workstream-image-test-" + uuid4().hex
    uid = os.getuid() or 1000
    gid = os.getgid() or 1000
    budget = ExecutionBudget(
        time.monotonic() + limits.deadline_ms / 1000, limits.maximum_output_bytes
    )
    cleaned = False
    created = False
    cleanup = {"container_name": name, "image_id": image_id, "state": "create_pending"}
    try:
        docker.inspect(image_id, budget=budget)
        evidence["sample_cleanup"] = cleanup
        checkpoint()
        docker.call(
            "create",
            "--name",
            name,
            "--label",
            "workstream.image-test=true",
            "--runtime",
            runtime,
            "--network",
            "none",
            "--read-only",
            "--user",
            f"{uid}:{gid}",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            str(min(256, max(16, limits.memory_bytes // (16 * 1024 * 1024)))),
            "--memory",
            str(limits.memory_bytes),
            "--cpus",
            str(limits.cpu_millis / 1000),
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,nodev,size=16777216",
            "--mount",
            f"type=bind,src={directory},dst=/work/input,readonly",
            "-i",
            image_id,
            step="create sample container",
            budget=budget,
            timeout=limits.deadline_ms / 1000,
        )
        created = True
        cleanup["state"] = "removal_pending"
        checkpoint()
        raw = docker.call(
            "start",
            "--attach",
            "--interactive",
            name,
            step="execute sample",
            data=request.model_dump_json().encode(),
            timeout=limits.deadline_ms / 1000,
            budget=budget,
        )
        state = decode(
            docker.call(
                "inspect",
                "--format",
                "{{json .State}}",
                name,
                step="inspect sample",
                timeout=limits.deadline_ms / 1000,
                budget=budget,
            )
        )
        if state.get("Running") or state.get("OOMKilled") or state.get("ExitCode") != 0:
            raise ImageError("sample did not exit cleanly")
        remove_sample(docker, name, budget)
        cleaned = True
        cleanup["state"] = "confirmed"
        checkpoint()
        return raw
    finally:
        if not cleaned:
            # Emergency cleanup cannot turn an over-budget sample into a passing one.
            remove_sample(docker, name, ExecutionBudget(time.monotonic() + 30, 65536))
            if created:
                cleanup["state"] = "confirmed"
                checkpoint()
            # Without a create acknowledgement, absence is only a snapshot. The
            # daemon may still publish this name; preserve its durable obligation.


def remove_sample(docker: Docker, name: str, budget: ExecutionBudget) -> None:
    """Charge normal cleanup to the sample; confirm absence even if removal fails."""
    removal_error = None
    try:
        docker.call("rm", "--force", name, step="remove sample container", budget=budget)
    except ImageError as exc:
        removal_error = exc
    remaining = docker.call(
        "container",
        "ls",
        "--all",
        "--quiet",
        "--no-trunc",
        "--filter",
        f"name=^/{name}$",
        step="confirm sample cleanup",
        budget=budget,
    )
    if remaining.strip():
        raise ImageError(
            f"sample cleanup incomplete; remove owned container {name} before retrying"
        )
    if removal_error:
        raise removal_error


def run_samples(
    docker: Docker,
    descriptor: Descriptor,
    samples: list,
    image_id: str,
    request_image_digest: str,
    runtime: str,
    evidence: dict,
    checkpoint,
) -> list[dict]:
    """Check expected work outcomes and exact findings using canonical CHECKERS validation."""
    observations = []
    for sample, path, digest in samples:
        print(f"Testing {sample.name} ({sample.expected})…", file=sys.stderr)
        request = sample_request(descriptor, sample, request_image_digest, digest)
        raw = test_sample(docker, image_id, request, path, runtime, evidence, checkpoint)
        result = ExternalCheckerExecutionResult.model_validate_json(raw)
        result.validate_request(request)
        if (
            result.outcome != "completed"
            or result.verdict != sample.expected
            or {f.code for f in result.findings} != set(sample.expected_codes)
            or any(f.level == "coverage_incomplete" for f in result.findings)
        ):
            raise ImageError(f"sample {sample.name}: expected verdict/findings were not produced")
        observations.append(
            {
                "name": sample.name,
                "verdict": result.verdict,
                "finding_codes": sorted({f.code for f in result.findings}),
                "sample_digest": digest,
                "request_digest": request.request_digest,
                "result_digest": result.result_digest,
            }
        )
    return observations


def aws(region: str, *arguments: str) -> bytes:
    """Use the engineer's configured AWS identity; do not retry uncertain writes."""
    return run(
        ["aws", "--region", region, "--no-cli-pager", *arguments],
        step="AWS " + arguments[0],
        env={**os.environ, "AWS_MAX_ATTEMPTS": "1", "AWS_PAGER": ""},
    )


def verify_manifest(response: dict, digest: str, image_id: str) -> tuple[str, int]:
    """Bind raw registry manifest bytes to the tested configuration, rejecting indexes."""
    images = response.get("images", [])
    if response.get("failures") or not images:
        raise ImageError("ECR did not return the exact published manifest")
    item = images[0]
    # ECR can return one row per tag for a digest shared by several releases.
    if any(
        other.get("imageManifest") != item.get("imageManifest")
        or other.get("imageManifestMediaType") != item.get("imageManifestMediaType")
        or other.get("imageId", {}).get("imageDigest") != digest
        for other in images
    ):
        raise ImageError("ECR returned conflicting identities for the published digest")
    raw = item["imageManifest"].encode("utf-8")
    manifest = verify_platform_manifest(raw, digest)
    media = item.get("imageManifestMediaType")
    if (manifest["mediaType"] != media or item["imageId"]["imageDigest"] != digest
            or manifest["config"]["digest"] != image_id):
        raise ImageError("published manifest does not match the tested image")
    return media, len(raw)


def publish(
    docker: Docker,
    descriptor: Descriptor,
    image: dict,
    region: str,
    expected_account: str,
    evidence: dict,
    checkpoint,
) -> dict:
    """Push one tested immutable image, then independently resolve and verify its digest."""
    account = decode(aws(region, "sts", "get-caller-identity", "--output", "json"))["Account"]
    if not isinstance(account, str) or not re.fullmatch(r"[0-9]{12}", account):
        raise ImageError("AWS returned an invalid account identity")
    if account != expected_account:
        raise ImageError(
            "AWS credentials do not match the requested account; nothing was published"
        )
    stage = "pre" if descriptor.phase == "pre_submit" else "post"
    repository = f"workstream-checker-{stage}-{descriptor.project}"
    expected_uri = f"{account}.dkr.ecr.{region}.amazonaws.com/{repository}"
    response = decode(
        aws(
            region,
            "ecr",
            "describe-repositories",
            "--registry-id",
            account,
            "--repository-names",
            repository,
            "--output",
            "json",
        )
    )
    repos = response.get("repositories", [])
    if len(repos) != 1 or repos[0].get("repositoryUri") != expected_uri:
        raise ImageError("the selected ECR repository is unavailable")
    tag = "checked-" + uuid4().hex
    reference = f"{expected_uri}:{tag}"
    evidence.update(repository=expected_uri, publication_tag=tag)
    with tempfile.TemporaryDirectory(prefix="workstream-ecr-auth-") as auth:
        password = aws(region, "ecr", "get-login-password")
        docker.call(
            "--config",
            auth,
            "login",
            "--username",
            "AWS",
            "--password-stdin",
            expected_uri.split("/")[0],
            data=password,
            step="ECR login",
        )
        del password
        docker.call("tag", image["Id"], reference, step="tag tested image")
        # After this point a failure may have published bytes. Never auto-retry.
        evidence["publication"] = "uncertain"
        checkpoint()
        output = docker.call(
            "--config",
            auth,
            "push",
            "--platform",
            f"{image['Os']}/{image['Architecture']}",
            reference,
            step="push tested image",
            timeout=600,
        )
        digests = re.findall(rb"digest: (sha256:[0-9a-f]{64})", output)
        if len(set(digests)) != 1:
            raise ImageError("push completed without one unambiguous digest")
        digest = digests[0].decode("ascii")
        evidence.update(publication="published_unverified", image=f"{expected_uri}@{digest}")
        checkpoint()
        response = decode(
            aws(
                region,
                "ecr",
                "batch-get-image",
                "--registry-id",
                account,
                "--repository-name",
                repository,
                "--image-ids",
                f"imageDigest={digest}",
                "--accepted-media-types",
                *MANIFEST_TYPES,
                "--output",
                "json",
            )
        )
        media, size = verify_manifest(response, digest, image["Id"])
        docker.call(
            "--config",
            auth,
            "pull",
            "--quiet",
            evidence["image"],
            step="pull exact digest",
            timeout=600,
        )
        pulled = docker.inspect(evidence["image"])
        if any(pulled.get(k) != image.get(k) for k in ("Id", "Os", "Architecture")) or evidence[
            "image"
        ] not in pulled.get("RepoDigests", []):
            raise ImageError("pulled image differs from the tested image")
        return {
            "repository": expected_uri,
            "platform_manifest_digest": digest,
            "platform_manifest_media_type": media,
            "platform_manifest_byte_count": size,
            "operating_system": image["Os"],
            "architecture": image["Architecture"],
            "config_image_id": image["Id"],
        }


def execute(args, evidence: dict, checkpoint) -> dict:
    """Build once, freeze samples, qualify locally, optionally publish and recheck exact digest."""
    context = args.context.resolve(strict=True)
    descriptor = load_descriptor(context)
    if not (context / "Dockerfile").is_file():
        raise ImageError("build context must contain Dockerfile")
    runtime = "runsc" if args.isolation == "gvisor" else "runc"
    evidence.update(isolation=args.isolation, samples=[])
    with tempfile.TemporaryDirectory(prefix="workstream-image-test-") as scratch:
        root = Path(scratch)
        docker = Docker(root / "docker-config")
        available = decode(
            docker.call("info", "--format", "{{json .Runtimes}}", step="check runtime")
        )
        if runtime not in available:
            raise ImageError(f"required Docker runtime {runtime} is unavailable")
        if "," in str(root):
            raise ImageError("temporary directory cannot contain a comma")
        samples = []
        for index, sample in enumerate(descriptor.samples):
            path = root / f"sample-{index}"
            digest = snapshot_sample(sample_directory(context, sample.directory), path)
            samples.append((sample, path, digest))
        print("Building checker image…", file=sys.stderr)
        iid = root / "image-id"
        docker.call(
            "build",
            "--platform",
            args.platform,
            "--provenance=false",
            "--sbom=false",
            "--iidfile",
            str(iid),
            str(context),
            step="build checker",
            timeout=1800,
        )
        image_id = iid.read_text().strip()
        if not DIGEST.fullmatch(image_id):
            raise ImageError("build did not return an immutable image ID")
        image = docker.inspect(image_id)
        if f"{image['Os']}/{image['Architecture']}" != args.platform or image["Id"] != image_id:
            raise ImageError("built image platform/identity differs")
        evidence["tested_image_id"] = image_id
        evidence["samples"] = run_samples(
            docker, descriptor, samples, image_id, image_id, runtime, evidence, checkpoint,
        )
        if not args.publish:
            return {}
        print("Publishing tested image to ECR…", file=sys.stderr)
        evidence["publication"] = "preflight"
        checkpoint()
        cache = publish(
            docker, descriptor, image, args.region, args.account_id, evidence, checkpoint
        )
        evidence["published_samples"] = run_samples(
            docker,
            descriptor,
            samples,
            image_id,
            cache["platform_manifest_digest"],
            runtime,
            evidence,
            checkpoint,
        )
        evidence["publication"] = "verified"
        return {
            "cache-entry.json": cache,
            "registry.json": descriptor.spec(cache["platform_manifest_digest"]).model_dump(
                mode="json"
            ),
        }


def sync_directory(path: Path) -> None:
    """Persist directory entries before relying on a published cleanup receipt."""
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_json(path: Path, value: dict) -> None:
    """Replace one owned receipt atomically; no credentials or raw checker text are stored."""
    temporary = path.with_suffix(".tmp")
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)
    sync_directory(path.parent)


def main(argv: list[str] | None = None) -> int:
    """Expose a dry-run-first command and a private receipt even after uncertain publication."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "context",
        type=Path,
        help="project checker directory containing Dockerfile and checker.json",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="publish after tests pass; default only builds and tests",
    )
    parser.add_argument("--region", default="eu-north-1")
    parser.add_argument(
        "--account-id", help="expected 12-digit AWS account; required with --publish"
    )
    parser.add_argument("--platform", choices=("linux/amd64", "linux/arm64"), default="linux/amd64")
    parser.add_argument("--isolation", choices=("docker-dev", "gvisor"), default="docker-dev")
    parser.add_argument(
        "--out", type=Path, help="new output directory; defaults to .checker-images/<unique-id>"
    )
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[a-z]{2}-[a-z]+-[0-9]", args.region):
        parser.error("region must be an AWS region name")
    if args.publish and (not args.account_id or not re.fullmatch(r"[0-9]{12}", args.account_id)):
        parser.error("--publish requires --account-id with the intended 12-digit AWS account")
    output = args.out or Path.cwd() / ".checker-images" / uuid4().hex
    evidence = {
        "kind": "checker_image_compatibility",
        "status": "failed",
        "publication": "not_started" if args.publish else "not_requested",
        "expected_account_id": args.account_id,
    }
    owned_output = False
    try:
        output.mkdir(mode=0o700, parents=True, exist_ok=False)
        owned_output = True
        # Persist newly created ancestors too, including the default receipt root.
        for directory in (output, *output.parents):
            sync_directory(directory)
        outputs = execute(args, evidence, lambda: write_json(output / "receipt.json", evidence))
        for name, value in outputs.items():
            write_json(output / name, value)
        evidence["status"] = "passed"
        code = 0
    except (ImageError, ValidationError, OSError, ValueError, KeyError, TypeError) as exc:
        message = (
            str(exc)
            if isinstance(exc, ImageError)
            else "invalid descriptor, response or filesystem operation"
        )
        evidence["error"] = message
        print(message, file=sys.stderr)
        code = 1
    except KeyboardInterrupt:
        evidence["error"] = "interrupted; inspect publication state before retrying"
        code = 130
    if owned_output:
        if code:
            for name in ("cache-entry.json", "registry.json"):
                (output / name).unlink(missing_ok=True)
        try:
            write_json(output / "receipt.json", evidence)
        except OSError:
            print("could not persist the receipt; retain the JSON printed below", file=sys.stderr)
            evidence["status"] = "failed"
            evidence["error"] = "receipt could not be persisted"
            code = 1
    print(json.dumps({**evidence, "output_directory": str(output.resolve())}, indent=2))
    return code


if __name__ == "__main__":

    def interrupt(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)
    raise SystemExit(main())
