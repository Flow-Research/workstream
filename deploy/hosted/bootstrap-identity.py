#!/usr/bin/env python3
"""Create Keycloak's temporary administrator while its single hosted node is stopped."""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
from uuid import uuid4

from preflight import (
    IDENTITY_FILE_KEYS, PreflightError, _private_metadata, compose_environment,
    parse_environment, render_compose, validate_compose, validate_environment,
    validate_identity_host_inputs,
)


def bootstrap(environment_path: Path, password_path: Path) -> None:
    values = parse_environment(environment_path)
    validate_environment(values)
    if not values.get("FLOW_IDENTITY_IMAGE"):
        raise PreflightError("Keycloak bootstrap requires its hosted overlay")
    config = render_compose(environment_path, values)
    validate_compose(config, values)
    validate_identity_host_inputs(values)
    if (not password_path.is_absolute() or password_path != password_path.resolve(strict=True)
            or any(char.isspace() or char in ":," for char in str(password_path))):
        raise PreflightError("bootstrap password must have a canonical private file path")
    _private_metadata(password_path, kind="file", uid=1000, gid=1000, mode=0o400)
    metadata = password_path.stat()
    if metadata.st_size > 4096 or metadata.st_nlink != 1:
        raise PreflightError("bootstrap password must be a bounded, independently owned file")
    if any(os.path.samestat(metadata, Path(values[key]).stat()) for key in IDENTITY_FILE_KEYS):
        raise PreflightError("bootstrap password must not reuse identity runtime credentials")
    environment = compose_environment(values)
    project = config.get("name")
    if not isinstance(project, str) or not project:
        raise PreflightError("hosted Compose project identity is missing")
    running = subprocess.run([
        "docker", "ps", "--quiet", "--filter", f"label=com.docker.compose.project={project}",
        "--filter", "label=com.docker.compose.service=identity",
    ], check=True, capture_output=True, text=True, timeout=30, env=environment)
    if running.stdout.strip():
        raise PreflightError("stop the hosted identity service before offline bootstrap")
    # Reuse the validated image, database, network and resource restrictions.
    # This one-off container has no listener or restart policy. The ordinary
    # Compose file never receives its bootstrap environment or secret mount.
    temporary = copy.deepcopy(config)
    # Compose validates dependencies even for services not selected by `run`.
    # This offline operation needs only identity and its existing network;
    # unrelated profiled runtime services must not participate in bootstrap.
    temporary["services"] = {"identity": temporary["services"]["identity"]}
    service = temporary["services"]["identity"]
    service["ports"] = []
    service["restart"] = "no"
    service["healthcheck"] = {"disable": True}
    service["environment"]["KC_BOOTSTRAP_ADMIN_PASSWORD_FILE"] = "/run/identity/bootstrap-password"
    service["volumes"].append({
        "type": "bind", "source": str(password_path),
        "target": "/run/identity/bootstrap-password", "read_only": True,
    })
    with tempfile.TemporaryDirectory(prefix="workstream-identity-bootstrap-") as directory:
        path = Path(directory) / "compose.json"
        path.write_text(json.dumps(temporary))
        path.chmod(0o600)
        container = "workstream-identity-bootstrap-" + uuid4().hex
        try:
            result = subprocess.run([
                "docker", "compose", "--project-name", project, "--file", str(path),
                "run", "--rm", "--no-deps", "--name", container,
                "identity", "bootstrap-admin", "user", "--optimized",
                "--username", "workstream-bootstrap", "--password:env", "KC_BOOTSTRAP_ADMIN_PASSWORD",
                "--no-prompt",
            ], check=False, capture_output=True, timeout=390, env=environment)
        finally:
            # Killing a timed-out Docker client does not kill its container.
            subprocess.run(["docker", "rm", "-fv", container], check=False,
                           capture_output=True, timeout=30, env=environment)
        if result.returncode:
            raise PreflightError("Keycloak offline bootstrap failed; no credentials were printed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--password-file", required=True, type=Path)
    args = parser.parse_args()
    try:
        bootstrap(args.env_file, args.password_file)
    except (PreflightError, OSError, subprocess.SubprocessError):
        print("Identity bootstrap failed. Check the private file, stopped node and backing database.")
        return 1
    print("Temporary administrator workstream-bootstrap created. Establish named administration, then remove it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
