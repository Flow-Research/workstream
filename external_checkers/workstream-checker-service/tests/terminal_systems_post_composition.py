"""Explicit Docker-dev qualification of service main with the real project image.

This uses a controlled local v2 proxy and proves the production Rust process,
image identity, verified material mount and invocation-local model socket.  It
does not claim ART custody, trial execution, runsc, or a live provider call.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading

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


PROTOCOL = "external_checker_service.v1"
GRANT_PROTOCOL = "workstream.external_checker_material_grant.v2"
MODEL_PROTOCOL = "workstream.model_session.v2"
MODEL_GRANT_ID = "model_0123456789abcdef0123456789abcdef"
MATERIAL_GRANT_ID = "extract_0123456789abcdef0123456789abcdef"
CHECK = "solver_brief_and_extension_disclosure"


def identifier(byte: str) -> str:
    return f"{byte * 8}-0000-4000-8000-000000000000"


def sha(byte: str) -> str:
    return "sha256:" + byte * 64


def inventory(root: Path) -> tuple[list[dict], str]:
    files = []
    for path in sorted(item for item in root.iterdir() if item.is_file()):
        body = path.read_bytes()
        files.append(
            {
                "normalized_path": path.name,
                "byte_count": len(body),
                "sha256": "sha256:" + hashlib.sha256(body).hexdigest(),
                "executable": False,
            }
        )
    entries = [
        {
            "normalized_path": item["normalized_path"],
            "entry_type": "file",
            "sha256": item["sha256"],
            "byte_count": item["byte_count"],
            "executable": item["executable"],
        }
        for item in files
    ]
    semantic = digest(
        {
            "schema_version": "workstream.submission_bundle_manifest.v1",
            "entries": entries,
        }
    )
    return files, semantic


def schema(schema_id: str, document: dict) -> dict:
    return {
        "schema_id": schema_id,
        "schema_version": "v1",
        "document": document,
        "schema_sha256": digest(document),
    }


def request_and_manifest(image_digest: str, workspace: Path) -> tuple[dict, dict]:
    files, semantic = inventory(workspace)
    configuration = {"check": CHECK}
    config_document = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"check": {"type": "string"}},
        "required": ["check"],
    }
    input_document = {"type": "object"}
    output_document = {"type": "object"}
    registry = {
        "capability_id": "terminal_systems.post.model",
        "capability_version": "v1",
        "phase": "post_submit",
        "image_digest": image_digest,
        "configuration_schema": schema("terminal_systems.post.configuration", config_document),
        "input_schema": schema("external_checker_post_submit_input", input_document),
        "output_schema": schema("external_checker_result", output_document),
        "resources": {
            "cpu_millis": 500,
            "memory_bytes": 128 * 1024 * 1024,
            "deadline_ms": 30_000,
            "maximum_output_bytes": 32_768,
        },
        "registry_entry_id": identifier("f"),
        "entry_digest": sha("0"),
        "registration_operation_id": identifier("a"),
        "registered_by_actor_profile_id": identifier("b"),
        "authorization_decision_event_id": identifier("c"),
        "created_at": "2026-10-23T00:00:00Z",
    }
    entry = dict(registry)
    for field in (
        "registry_entry_id",
        "entry_digest",
        "registration_operation_id",
        "registered_by_actor_profile_id",
        "authorization_decision_event_id",
        "created_at",
    ):
        entry.pop(field)
    registry["entry_digest"] = digest(entry)
    identity = {
        "phase": "post_submit",
        "project_id": identifier("1"),
        "task_id": identifier("2"),
        "assignment_id": identifier("3"),
        "submission_id": identifier("4"),
        "submission_version": 2,
        "evaluation_request_id": identifier("5"),
        "evaluation_request_digest": sha("5"),
        "evaluation_generation": 3,
        "attempt_id": identifier("6"),
        "result_id": identifier("7"),
        "lease_id": identifier("8"),
        "lease_generation": 4,
        "lease_expires_at": "2026-10-23T23:00:00+00:00",
    }
    material = {
        "phase": "post_submit",
        "role": "submission_archive",
        "submission_id": identity["submission_id"],
        "submission_version": identity["submission_version"],
        "binding_id": identifier("9"),
        "content_id": identifier("a"),
        "replica_id": identifier("b"),
        "content_sha256": sha("c"),
        "byte_count": sum(item["byte_count"] for item in files),
        "media_type": "application/zip",
        "evidence_id": identifier("c"),
        "verification_receipt_id": identifier("d"),
        "verification_job_id": identifier("e"),
        "verification_generation": 5,
        "namespace_fingerprint": sha("d"),
        "semantic_manifest_sha256": semantic,
    }
    request = {
        "schema_version": "external_checker_request.v1",
        "registry": registry,
        "identity": identity,
        "configuration": configuration,
        "configuration_sha256": digest(configuration),
        "input": {"requirement_id": CHECK},
        "materials": [material],
    }
    request["input_sha256"] = digest(request["input"])
    request["request_digest"] = digest(request)
    manifest = {
        "protocol_version": GRANT_PROTOCOL,
        "grant_id": MATERIAL_GRANT_ID,
        "request_digest": request["request_digest"],
        "phase": "post_submit",
        "identity": identity,
        "evaluation_context_sha256": None,
        "materials": [{"material": material, "directories": [], "files": files}],
        "visible_roles": ["submission_archive"],
    }
    manifest["binding_digest"] = digest(manifest)
    return request, manifest


def controlled_proxy(address: Path, expected_digest: str, observed: dict, ready: threading.Event) -> None:
    try:
        with socket.socket(socket.AF_UNIX) as listener:
            listener.bind(str(address))
            address.chmod(0o600)
            listener.listen(1)
            ready.set()
            connection, _ = listener.accept()
            with connection:
                request = json.loads(read_frame(connection))
                if request != {
                    "protocol_version": MODEL_PROTOCOL,
                    "grant_id": MODEL_GRANT_ID,
                    "request_digest": expected_digest,
                    "call_index": 0,
                    "prompt": request.get("prompt"),
                    "resolved_receipts": [],
                }:
                    raise RuntimeError("proxy received a non-closed v2 request")
                prompt = json.loads(request["prompt"])
                evidence = prompt["untrusted_evidence_data"]["evidence"][0]["evidence_id"]
                assessment = {
                    "schema_version": "terminal_systems.model_assessment.v1",
                    "requirement_id": prompt["rubric"]["requirement_id"],
                    "material_digest": prompt["untrusted_evidence_data"]["material_digest"],
                    "conditions": [
                        {
                            "condition_number": item["condition_number"],
                            "status": "satisfied",
                            "evidence_ids": [evidence],
                            "finding_numbers": [],
                        }
                        for item in prompt["rubric"]["pass_conditions"]
                    ],
                    "findings": [],
                }
                response = {
                    "protocol_version": MODEL_PROTOCOL,
                    "outcome": "completed",
                    "output": json.dumps(assessment, sort_keys=True, separators=(",", ":")),
                    "receipt_digest": sha("e"),
                    "failure_code": None,
                    "call_index": 0,
                    "session_exhausted": True,
                }
                observed["request"] = request
                write_frame(connection, canonical(response))
    except BaseException as error:
        observed["error"] = error
        ready.set()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", required=True, type=Path)
    parser.add_argument("--checker-image", default="ws-terminal-systems-post:qualification")
    parser.add_argument("--registry-image", default="registry:2")
    args = parser.parse_args()
    service = args.service.resolve(strict=True)
    docker = str(Path(shutil.which("docker") or "/usr/bin/docker").resolve(strict=True))
    uid, gid = os.geteuid(), os.getegid()
    if uid == 0 or gid == 0:
        raise RuntimeError("qualification requires the service non-root UID/GID")
    run(docker, "image", "inspect", args.checker_image)
    run(docker, "image", "inspect", args.registry_image)

    nonce = os.urandom(8).hex()
    registry_tag = None
    service_process = None
    registry_process = None
    checker_id = None
    with tempfile.TemporaryDirectory(prefix="ws-ts-post-composition-") as temporary:
        root = Path(temporary).resolve()
        inspection = root / "container-inspection.json"
        try:
            print("phase=registry_prepare", flush=True)
            registry = extract_registry_binary(docker, args.registry_image, root)
            registry_process, port = start_registry(registry, root)
            repository = f"127.0.0.1:{port}/terminal-systems-post"
            registry_tag = f"{repository}:{nonce}"
            run(docker, "tag", args.checker_image, registry_tag)
            run(docker, "push", registry_tag, timeout=120)
            image = json.loads(run(docker, "image", "inspect", registry_tag))[0]
            reference = next(item for item in image["RepoDigests"] if item.startswith(repository + "@"))
            platform_digest = reference.split("@", 1)[1]

            print("phase=material_grant_prepare", flush=True)
            socket_root, material_root, proxy_root, relay_root = (
                root / "service", root / "material", root / "proxy", root / "relay"
            )
            for directory in (socket_root, material_root, proxy_root, relay_root):
                directory.mkdir(mode=0o700)
            workspace = material_root / "workspaces" / MATERIAL_GRANT_ID / "materials" / "submission_archive"
            workspace.mkdir(parents=True, mode=0o700)
            for name, body in {
                "instruction.md": b"Build the documented extension and explain it clearly.\n",
                "task.toml": b"format_version = 1\n",
                "AUTHOR_NOTES.md": b"The extension is documented in the submission.\n",
            }.items():
                path = workspace / name
                path.write_bytes(body)
                path.chmod(0o400)
            workspace.chmod(0o500)
            materials = workspace.parent
            materials.chmod(0o500)
            grant_root = materials.parent
            grant_root.chmod(0o700)
            request, manifest = request_and_manifest(platform_digest, workspace)
            manifest_path = grant_root / ".external-checker-grant.json"
            manifest_path.write_bytes(canonical(manifest))
            manifest_path.chmod(0o400)

            proxy_result: dict[str, object] = {}
            ready = threading.Event()
            proxy_address = proxy_root / "model-proxy.sock"
            proxy_thread = threading.Thread(
                target=controlled_proxy,
                args=(proxy_address, request["request_digest"], proxy_result, ready),
                daemon=True,
            )
            proxy_thread.start()
            if not ready.wait(5) or "error" in proxy_result:
                raise RuntimeError(f"proxy startup failed: {proxy_result.get('error')}")

            print("phase=service_start", flush=True)
            wrapper = root / "docker-wrapper.py"
            wrapper.write_text(
                "#!/usr/bin/python3\nimport json,pathlib,subprocess,sys\n"
                f"docker={docker!r}\nproof=pathlib.Path({str(inspection)!r})\n"
                "r=subprocess.run([docker,*sys.argv[1:]],stdin=sys.stdin.buffer,stdout=subprocess.PIPE,stderr=subprocess.PIPE)\n"
                "if r.returncode==0 and len(sys.argv)>1 and sys.argv[1]=='create':\n"
                " i=r.stdout.decode().strip(); proof.write_bytes(subprocess.check_output([docker,'container','inspect',i]))\n"
                "sys.stdout.buffer.write(r.stdout);sys.stderr.buffer.write(r.stderr);raise SystemExit(r.returncode)\n",
                encoding="utf-8",
            )
            wrapper.chmod(0o700)
            config = {
                "socket_path": str(socket_root / "checker.sock"),
                "model_proxy_socket": str(proxy_address),
                "model_relay_root": str(relay_root),
                "material_root": str(material_root),
                "docker_binary": str(wrapper),
                "runtime": "runc",
                "isolation_mode": "docker-dev",
                "operating_system": image["Os"],
                "architecture": image["Architecture"],
                "sandbox_uid": uid,
                "sandbox_gid": gid,
                "cache": [{
                    "repository": repository,
                    "platform_manifest_digest": platform_digest,
                    "platform_manifest_media_type": "application/vnd.docker.distribution.manifest.v2+json",
                    "platform_manifest_byte_count": 1,
                    "operating_system": image["Os"],
                    "architecture": image["Architecture"],
                    "config_image_id": image["Id"],
                }],
            }
            config_path = root / "service.json"
            config_path.write_bytes(canonical(config))
            service_process = subprocess.Popen(
                [str(service), str(config_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            wait_for_service(service_process, socket_root / "checker.sock")
            print("phase=execute", flush=True)
            envelope = {
                "protocol_version": PROTOCOL,
                "operation": "execute",
                "request": request,
                "grant": {"grant_id": MATERIAL_GRANT_ID, "binding_digest": manifest["binding_digest"]},
                "model_grant": {"grant_id": MODEL_GRANT_ID, "binding_digest": request["request_digest"]},
            }
            with socket.socket(socket.AF_UNIX) as connection:
                connection.settimeout(45)
                connection.connect(str(socket_root / "checker.sock"))
                write_frame(connection, canonical(envelope))
                response = json.loads(read_frame(connection, 96 * 1024))
            proxy_thread.join(timeout=5)
            if proxy_thread.is_alive() or "error" in proxy_result:
                raise RuntimeError(f"proxy exchange failed: {proxy_result.get('error')}")
            if (response["result"]["outcome"], response["result"]["verdict"]) != ("completed", "passed"):
                raise RuntimeError(f"checker result failed: {response['result']}")
            inspected = json.loads(inspection.read_text())[0]
            checker_id = inspected["Id"]
            mounts = {item["Destination"]: item for item in inspected["Mounts"]}
            if inspected["Config"]["Image"] != f"{repository}@{platform_digest}":
                raise RuntimeError("service did not execute the selected immutable image")
            if inspected["HostConfig"]["NetworkMode"] != "none" or not inspected["HostConfig"]["ReadonlyRootfs"]:
                raise RuntimeError("checker isolation flags differ")
            if inspected["HostConfig"]["CapDrop"] != ["ALL"] or not any(
                item.startswith("no-new-privileges")
                for item in inspected["HostConfig"]["SecurityOpt"]
            ):
                raise RuntimeError("checker privilege restrictions differ")
            if mounts["/work/input"]["RW"] or mounts["/work/model.sock"]["RW"]:
                raise RuntimeError("checker mounts were writable")
            if inspect_container(docker, checker_id) is not None or any(relay_root.iterdir()):
                raise RuntimeError("checker or invocation relay cleanup was unsettled")
            print("phase=verified", flush=True)
            print(json.dumps({
                "status": "PASS",
                "boundary": "production-service-main/docker-dev/controlled-provider",
                "image_id": image["Id"],
                "platform_manifest_digest": platform_digest,
                "result_digest": response["result"]["result_digest"],
                "network_none": True,
                "rootfs_read_only": True,
                "capabilities_dropped": True,
                "no_new_privileges": True,
                "material_read_only": True,
                "model_socket_read_only": True,
                "container_removed": True,
                "relay_removed": True,
                "durable_art_proven": False,
                "trial_proven": False,
                "runsc_proven": False,
            }, sort_keys=True))
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
            if checker_id is not None and inspect_container(docker, checker_id) is not None:
                run(docker, "rm", "--force", checker_id)
            if registry_tag is not None:
                subprocess.run([docker, "image", "rm", registry_tag], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)


if __name__ == "__main__":
    main()
