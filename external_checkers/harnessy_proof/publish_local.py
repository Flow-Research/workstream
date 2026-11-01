#!/usr/bin/env python3
"""Publish the proof checker to a loopback registry and write its local configs.

Run on the Docker host from the repository root. The script builds this
directory's image, pushes it to the loopback registry, resolves the exact
platform manifest, pulls that digest so the daemon records it, and writes:

- ``checker-service.json``: the Rust checker-service configuration;
- ``registry-post.json``: the ``ExternalCheckerRegistrySpec`` body for
  ``POST /api/v1/operations/external-checker-registry``. The checker is
  post-submission only: it needs forge facts, which PRE never has.

It uses only the Python standard library and the Docker CLI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
MANIFEST_TYPES = (
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
)
CAPABILITY_ID = "harnessy.work_proof"
PHASE = "post_submit"
INPUT_SCHEMA_ID = "external_checker_post_submit_input"
# The socket stays on a named volume: Docker Desktop host-shared paths refuse
# chmod on Unix sockets, and AF_UNIX paths must stay within 107 bytes.
SOCKET_PATH = "/run/ws-checker/checker.sock"
MODEL_PROXY_SOCKET = "/run/ws-model-proxy/model-proxy.sock"


def material_root(compose_project: str) -> str:
    """The Docker-VM path of the named material volume, identical in every container."""
    return f"/var/lib/docker/volumes/{compose_project}-checker-material/_data"


def model_relay_root(compose_project: str) -> str:
    """Daemon-visible private root for invocation-local model sockets."""
    return f"/var/lib/docker/volumes/{compose_project}-checker-relay/_data"


def _hash(value: object) -> str:
    """Canonical JSON digest for the string/integer/object schema documents used here."""
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


# One fail-closed mode: the forge facts version, forge, forge instance origin,
# repository and base branch are required. Integrity options are optional and
# default to the safe values. GitHub is the only supported forge today. The
# repository uses the forge-neutral path grammar: two or more "/"-joined
# segments, none "." or ".." (GitLab subgroups allowed).
CONFIGURATION_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "workstream_forge_facts_version",
        "forge",
        "forge_origin",
        "repository",
        "base_branch",
    ],
    "properties": {
        "workstream_forge_facts_version": {"const": "v1"},
        "forge": {"enum": ["github"]},
        "forge_origin": {
            "type": "string",
            "pattern": "^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?$",
        },
        "repository": {
            "type": "string",
            "maxLength": 255,
            "pattern": r"^(?!(?:.*/)?\.{1,2}(?:/|$))[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)+$",
        },
        "base_branch": {"type": "string", "minLength": 1, "maxLength": 255},
        "allow_unbound_required_checks": {"type": "boolean"},
        "protected_paths": {
            "type": "array",
            "maxItems": 100,
            "items": {"type": "string", "minLength": 1, "maxLength": 1000},
        },
        "required_independent_approvals": {"type": "integer", "minimum": 1, "maximum": 10},
        "operator_logins": {
            "type": "array",
            "maxItems": 100,
            "items": {"type": "string", "minLength": 1, "maxLength": 100},
        },
    },
}
# WorkStream adds forge facts to the normalized POST input. A missing facts
# object reaches the checker, which reports forge.facts_missing.
INPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "forge_facts": {
            "type": "object",
            "required": ["schema_version"],
            "properties": {"schema_version": {"const": "workstream.forge_change_facts.v1"}},
        }
    },
}


def _schema(schema_id: str, document: dict[str, object] | None = None) -> dict[str, object]:
    document = {"type": "object"} if document is None else document
    return {
        "schema_id": schema_id,
        "schema_version": "v1",
        "document": document,
        "schema_sha256": _hash(document),
    }


def registry_spec(image_digest: str, capability_version: str) -> dict[str, object]:
    """The immutable post-submission registry body."""
    return {
        "capability_id": CAPABILITY_ID,
        "capability_version": capability_version,
        "phase": PHASE,
        "image_digest": image_digest,
        "configuration_schema": _schema(
            "harnessy.work_proof.configuration", CONFIGURATION_SCHEMA
        ),
        "input_schema": _schema(INPUT_SCHEMA_ID, INPUT_SCHEMA),
        "output_schema": _schema("external_checker_result"),
        "resources": {
            "cpu_millis": 500,
            "memory_bytes": 134_217_728,
            "deadline_ms": 30_000,
            "maximum_output_bytes": 32_768,
        },
    }


def service_config(
    image: dict[str, object],
    *,
    compose_project: str,
    sandbox_uid: int,
    sandbox_gid: int,
    enable_model_proxy: bool = False,
) -> dict[str, object]:
    config = {
        "socket_path": SOCKET_PATH,
        "material_root": material_root(compose_project),
        "docker_binary": "/usr/local/bin/docker",
        "runtime": "runc",
        "isolation_mode": "docker-dev",
        "operating_system": image["operating_system"],
        "architecture": image["architecture"],
        "sandbox_uid": sandbox_uid,
        "sandbox_gid": sandbox_gid,
        "cache": [image],
    }
    if enable_model_proxy:
        relay_root = model_relay_root(compose_project)
        maximum_socket = f"{relay_root}/.model-{'0' * 16}/model.sock"
        if len(maximum_socket.encode()) >= 108:
            raise ValueError(
                "compose project makes the model relay socket path too long"
            )
        config.update(
            {
                "model_proxy_socket": MODEL_PROXY_SOCKET,
                "model_relay_root": relay_root,
            }
        )
    return config


def _docker(*arguments: str) -> str:
    return subprocess.run(["docker", *arguments], check=True, capture_output=True, text=True).stdout


def publish(registry: str, repository: str) -> dict[str, object]:
    """Build, push and resolve one single-platform manifest by digest."""
    if re.fullmatch(r"(localhost|127\.0\.0\.1):[0-9]{1,5}", registry) is None:
        raise SystemExit("the proof checker publishes only to a loopback registry")
    tagged = f"{registry}/{repository}:local"
    # Docker progress goes to stderr so stdout carries only the final JSON summary.
    subprocess.run(
        ["docker", "build", "--provenance=false", "--sbom=false", "--tag", tagged, str(HERE)],
        check=True,
        stdout=sys.stderr,
    )
    subprocess.run(["docker", "push", tagged], check=True, stdout=sys.stderr)
    request = Request(
        f"http://{registry}/v2/{repository}/manifests/local",
        method="HEAD",
        headers={"Accept": ",".join(MANIFEST_TYPES)},
    )
    with urlopen(request, timeout=10) as response:
        media_type = response.headers["Content-Type"]
        byte_count = int(response.headers["Content-Length"])
        digest = response.headers["Docker-Content-Digest"]
    if media_type not in MANIFEST_TYPES:
        raise SystemExit(f"registry returned {media_type}, not a platform manifest")
    reference = f"{registry}/{repository}@{digest}"
    subprocess.run(["docker", "pull", "--quiet", reference], check=True, stdout=subprocess.DEVNULL)
    inspected = json.loads(_docker("image", "inspect", "--format", "{{json .}}", reference))
    if reference not in inspected.get("RepoDigests", []):
        raise SystemExit("the daemon did not record the platform-manifest digest")
    return {
        "repository": f"{registry}/{repository}",
        "platform_manifest_digest": digest,
        "platform_manifest_media_type": media_type,
        "platform_manifest_byte_count": byte_count,
        "operating_system": inspected["Os"],
        "architecture": inspected["Architecture"],
        "config_image_id": inspected["Id"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--registry", required=True, help="loopback host:port")
    parser.add_argument("--repository", default="harnessy-proof")
    parser.add_argument("--compose-project", required=True)
    parser.add_argument("--sandbox-uid", type=int, required=True)
    parser.add_argument("--sandbox-gid", type=int, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--enable-model-proxy",
        action="store_true",
        help="emit fixed local proxy and daemon-visible relay paths",
    )
    # The registry holds one immutable entry per phase, capability and version,
    # so a rebuilt image (new digest) needs a new version. v2 compares the
    # proof with forge facts and is post-submission only.
    parser.add_argument("--capability-version", default="v2")
    args = parser.parse_args(argv)
    image = publish(args.registry, args.repository)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "checker-service.json": service_config(
            image,
            compose_project=args.compose_project,
            sandbox_uid=args.sandbox_uid,
            sandbox_gid=args.sandbox_gid,
            enable_model_proxy=args.enable_model_proxy,
        ),
        "registry-post.json": registry_spec(
            image["platform_manifest_digest"], args.capability_version
        ),
    }
    for name, value in outputs.items():
        (args.out_dir / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "image": f"{image['repository']}@{image['platform_manifest_digest']}",
                "architecture": image["architecture"],
                "written": sorted(outputs),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
