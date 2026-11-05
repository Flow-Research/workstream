"""Qualify the real offline Harnessy image's locator and evaluation via service main.

Run with the backend Python environment, a current built checker image, and the
compiled native service. Facts are controlled fixture data: this proves image,
wire, grant and sandbox composition, not a GitHub read or durable ART custody.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen

from model_relay_docker import (
    canonical,
    digest,
    extract_registry_binary,
    inspect_container,
    read_frame,
    run,
    start_registry,
    wait_for_service,
    write_frame,
)
from terminal_systems_post_composition import request_and_manifest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
from app.core.identifiers import new_record_id  # noqa: E402
from app.modules.checkers.api.external import (  # noqa: E402
    ExternalCheckerExecutionRequest,
    ExternalCheckerExecutionResult,
    ExternalCheckerRegistryEntry,
    PostSubmitExternalCheckerIdentity,
    PostSubmitExternalCheckerMaterial,
    make_external_checker_execution_request,
)
from app.modules.checkers.api.forge_locator import ExternalCheckerForgeLocator  # noqa: E402

SPEC = importlib.util.spec_from_file_location(
    "harnessy_publish", ROOT / "external_checkers/harnessy_proof/publish_local.py"
)
assert SPEC is not None and SPEC.loader is not None
PUBLISH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PUBLISH)

REGISTRY_ID = str(new_record_id())
URL = "https://github.com/acme/widgets/pull/12"
RUN_URL = "https://github.com/acme/widgets/actions/runs/345"
HEAD, MERGE = "e" * 40, "d" * 40
PROOF = {
    "schema": "harnessy.work.proof.v1",
    "pr_url": URL,
    "commit_sha": MERGE,
    "ci_run_url": RUN_URL,
    "ci_conclusion": "success",
    "merged": True,
}
FACTS = {
    "schema_version": "workstream.forge_change_facts.v1",
    "forge": "github",
    "forge_origin": "https://github.com",
    "repository": "acme/widgets",
    "change_number": 12,
    "change_url": URL,
    "state": "closed",
    "merged": True,
    "landed_commit_sha": MERGE,
    "base_ref": "main",
    "head_sha": HEAD,
    "author": {"login": "agent-bot", "id": 501, "kind": "bot"},
    "reviews": [
        {
            "id": "61",
            "reviewer": {"login": "reviewer", "id": 7, "kind": "user"},
            "reviewer_write_access": True,
            "state": "approved",
            "commit_id": HEAD,
            "submitted_at": "2026-10-24T11:00:00Z",
        }
    ],
    "changed_files_count": 1,
    "changed_files": [
        {"path": "src/app.py", "previous_path": None, "status": "modified"}
    ],
    "required_checks": [
        {
            "name": "backend",
            "conclusion": "success",
            "required_producer": "github_app:15368",
            "judged": [{"producer": "github_app:15368", "sha": HEAD}],
            "run_url": RUN_URL,
        }
    ],
    "fetched_at": "2026-10-24T12:00:00Z",
    "responses": [{"request": "pull_request", "sha256": "sha256:" + "f" * 64}],
}
CONFIGURATION = {
    "workstream_forge_facts_version": "v1",
    "forge": "github",
    "forge_origin": "https://github.com",
    "repository": "acme/widgets",
    "base_branch": "main",
}


def invocation(material_root, image_digest, *, locate):
    """Give each pass its own exact request-bound grant over the same proof bytes."""
    grant_id = "extract_" + os.urandom(16).hex()
    grant_root = material_root / "workspaces" / grant_id
    workspace = grant_root / "materials/submission_archive"
    workspace.mkdir(parents=True, mode=0o700)
    proof_path = workspace / "proof.json"
    proof_path.write_bytes(canonical(PROOF))
    proof_path.chmod(0o400)
    request, manifest = request_and_manifest(image_digest, workspace)
    metadata = {
        key: request["registry"][key]
        for key in (
            "registry_entry_id",
            "registration_operation_id",
            "registered_by_actor_profile_id",
            "authorization_decision_event_id",
            "created_at",
        )
    }
    metadata["registry_entry_id"] = REGISTRY_ID
    spec = PUBLISH.registry_spec(image_digest, "v3")
    request["registry"] = {**spec, **metadata, "entry_digest": digest(spec)}
    request["configuration"] = CONFIGURATION
    request["configuration_sha256"] = digest(CONFIGURATION)
    request["input"] = (
        {"workstream_forge_facts_stage": "locate"} if locate else {"forge_facts": FACTS}
    )
    request["input_sha256"] = digest(request["input"])
    request = make_external_checker_execution_request(
        registry=ExternalCheckerRegistryEntry.model_validate_json(
            canonical(request["registry"])
        ),
        identity=PostSubmitExternalCheckerIdentity.model_validate_json(
            canonical(request["identity"])
        ),
        configuration=request["configuration"],
        configuration_sha256=request["configuration_sha256"],
        input=request["input"],
        input_sha256=request["input_sha256"],
        materials=tuple(
            PostSubmitExternalCheckerMaterial.model_validate_json(canonical(item))
            for item in request["materials"]
        ),
    ).model_dump(mode="json")
    manifest["identity"] = request["identity"]
    manifest.update(grant_id=grant_id, request_digest=request["request_digest"])
    manifest.pop("binding_digest")
    manifest["binding_digest"] = digest(manifest)
    manifest_path = grant_root / ".external-checker-grant.json"
    manifest_path.write_bytes(canonical(manifest))
    manifest_path.chmod(0o400)
    workspace.chmod(0o500)
    workspace.parent.chmod(0o500)
    grant_root.chmod(0o700)
    return request, {"grant_id": grant_id, "binding_digest": manifest["binding_digest"]}


def invoke(address, request, grant, operation):
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(45)
        connection.connect(str(address))
        write_frame(
            connection,
            canonical(
                {
                    "protocol_version": "external_checker_service.v1",
                    "operation": operation,
                    "request": request,
                    "grant": grant,
                    "model_grant": None,
                }
            ),
        )
        response = json.loads(read_frame(connection, 96 * 1024))
    if response["protocol_version"] != "external_checker_service.v1":
        raise RuntimeError("service protocol differs")
    return response


def read_inspections(path):
    if not path.exists():
        return []
    decoder, remaining, inspections = json.JSONDecoder(), path.read_text(), []
    while remaining.strip():
        item, end = decoder.raw_decode(remaining.lstrip())
        inspections.append(item[0])
        remaining = remaining.lstrip()[end:]
    return inspections


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", required=True, type=Path)
    parser.add_argument("--checker-image", default="ws-harnessy-forge:qualification")
    parser.add_argument("--registry-image", default="registry:2")
    args = parser.parse_args()
    service = args.service.resolve(strict=True)
    docker = str(Path(shutil.which("docker") or "/usr/bin/docker").resolve(strict=True))
    uid, gid = os.geteuid(), os.getegid()
    if uid == 0 or gid == 0:
        raise RuntimeError("qualification requires a non-root service UID/GID")
    for image_name in (args.checker_image, args.registry_image):
        run(docker, "image", "inspect", image_name)
    registry_process = service_process = None
    registry_tag = None
    checker_ids = []
    with tempfile.TemporaryDirectory(prefix="ws-forge-") as temporary:
        root = Path(temporary).resolve()
        inspection = root / "inspections.jsonl"
        try:
            registry = extract_registry_binary(docker, args.registry_image, root)
            registry_process, port = start_registry(registry, root)
            repository = f"127.0.0.1:{port}/harnessy-forge"
            registry_tag = f"{repository}:{os.urandom(8).hex()}"
            run(docker, "tag", args.checker_image, registry_tag)
            run(docker, "push", registry_tag, timeout=120)
            image = json.loads(run(docker, "image", "inspect", registry_tag))[0]
            reference = next(
                item
                for item in image["RepoDigests"]
                if item.startswith(repository + "@")
            )
            image_digest = reference.split("@", 1)[1]
            manifest_request = Request(
                f"http://127.0.0.1:{port}/v2/harnessy-forge/manifests/{image_digest}",
                method="HEAD",
                headers={"Accept": ",".join(PUBLISH.MANIFEST_TYPES)},
            )
            with urlopen(manifest_request, timeout=10) as manifest_response:
                manifest_type = manifest_response.headers["Content-Type"]
                manifest_bytes = int(manifest_response.headers["Content-Length"])
            socket_root, material_root = root / "service", root / "material"
            socket_root.mkdir(mode=0o700)
            material_root.mkdir(mode=0o700)
            inspection = root / "inspections.jsonl"
            wrapper = root / "docker-wrapper.py"
            wrapper.write_text(
                "#!/usr/bin/python3\nimport pathlib,subprocess,sys\n"
                f"docker={docker!r}\nproof=pathlib.Path({str(inspection)!r})\n"
                "r=subprocess.run([docker,*sys.argv[1:]],stdin=sys.stdin.buffer,stdout=subprocess.PIPE,stderr=subprocess.PIPE)\n"
                "if r.returncode==0 and len(sys.argv)>1 and sys.argv[1]=='create':\n"
                " i=r.stdout.decode().strip()\n"
                " with proof.open('ab') as f: f.write(subprocess.check_output([docker,'container','inspect',i]).strip()+b'\\n')\n"
                "sys.stdout.buffer.write(r.stdout);sys.stderr.buffer.write(r.stderr);raise SystemExit(r.returncode)\n"
            )
            wrapper.chmod(0o700)
            address = socket_root / "checker.sock"
            config = dict(
                socket_path=str(address),
                material_root=str(material_root),
                docker_binary=str(wrapper),
                runtime="runc",
                isolation_mode="docker-dev",
                operating_system=image["Os"],
                architecture=image["Architecture"],
                sandbox_uid=uid,
                sandbox_gid=gid,
                cache=[
                    dict(
                        repository=repository,
                        platform_manifest_digest=image_digest,
                        platform_manifest_media_type=manifest_type,
                        platform_manifest_byte_count=manifest_bytes,
                        operating_system=image["Os"],
                        architecture=image["Architecture"],
                        config_image_id=image["Id"],
                    )
                ],
            )
            config_path = root / "service.json"
            config_path.write_bytes(canonical(config))
            service_process = subprocess.Popen(
                [str(service), str(config_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            wait_for_service(service_process, address)
            locate_request, locate_grant = invocation(
                material_root, image_digest, locate=True
            )
            located = invoke(
                address, locate_request, locate_grant, "locate_forge_change"
            )
            locator = ExternalCheckerForgeLocator.model_validate_json(
                canonical(located["result"])
            )
            locator.validate_request(
                ExternalCheckerExecutionRequest.model_validate_json(
                    canonical(locate_request)
                )
            )
            if locator.change_url != URL or located["isolation"] is None:
                raise RuntimeError(f"image locator failed: {located}")
            final_request, final_grant = invocation(
                material_root, image_digest, locate=False
            )
            replay = invoke(address, final_request, locate_grant, "execute")
            if (
                replay["result"].get("infrastructure_failure_code")
                != "material_unavailable"
            ):
                raise RuntimeError("locator grant replay reached final evaluation")
            evaluated = invoke(address, final_request, final_grant, "execute")
            result = ExternalCheckerExecutionResult.model_validate_json(
                canonical(evaluated["result"])
            )
            result.validate_request(
                ExternalCheckerExecutionRequest.model_validate_json(
                    canonical(final_request)
                )
            )
            if (result.outcome, result.verdict) != ("completed", "passed") or evaluated[
                "isolation"
            ] is None:
                raise RuntimeError(f"image evaluation failed: {evaluated}")
            inspections = read_inspections(inspection)
            if len(inspections) != 2:
                raise RuntimeError("unexpected sandbox invocation count")
            for inspected in inspections:
                checker_ids.append(inspected["Id"])
                mounts = {item["Destination"]: item for item in inspected["Mounts"]}
                host = inspected["HostConfig"]
                if (
                    inspected["Config"]["Image"] != reference
                    or host["NetworkMode"] != "none"
                    or not host["ReadonlyRootfs"]
                    or host["CapDrop"] != ["ALL"]
                    or not any(
                        item.startswith("no-new-privileges")
                        for item in host["SecurityOpt"]
                    )
                    or mounts["/work/input"]["RW"]
                    or any("sock" in destination for destination in mounts)
                ):
                    raise RuntimeError(
                        "image pin, isolation, material or callback mounts differ"
                    )
                if inspect_container(docker, inspected["Id"]) is not None:
                    raise RuntimeError("checker container cleanup unsettled")
            print(
                json.dumps(
                    dict(
                        status="PASS",
                        boundary="production-service-main/docker-dev/controlled-forge-facts",
                        platform_manifest_digest=image_digest,
                        locator_digest=locator.locator_digest,
                        result_digest=result.result_digest,
                        invocation_count=2,
                        grant_replay_rejected=True,
                        network_none=True,
                        material_read_only=True,
                        callback_sockets_absent=True,
                        containers_removed=True,
                        live_github_proven=False,
                        durable_art_proven=False,
                    ),
                    sort_keys=True,
                )
            )
        finally:
            if service_process is not None:
                if service_process.poll() is None:
                    service_process.terminate()
                    try:
                        service_process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        service_process.kill()
                        service_process.wait(timeout=10)
                service_process.stderr.close()
            if registry_process is not None and registry_process.poll() is None:
                registry_process.terminate()
                registry_process.wait(timeout=10)
            checker_ids.extend(item["Id"] for item in read_inspections(inspection))
            for checker_id in set(checker_ids):
                if inspect_container(docker, checker_id) is not None:
                    run(docker, "rm", "--force", checker_id)
            if registry_tag is not None:
                subprocess.run(
                    [docker, "image", "rm", registry_tag],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=30,
                )
            for directory, _, _ in os.walk(root):
                Path(directory).chmod(0o700)


if __name__ == "__main__":
    main()
