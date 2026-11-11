#!/usr/bin/env python3
"""Run the bounded hosted Compose file without ambient interpolation."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import time
from uuid import UUID

from preflight import (
    PreflightError,
    compose_environment,
    load_checker_config,
    parse_environment,
    render_compose,
    run_compose,
    run_shutdown,
    validate_checker_config,
    validate_compose,
    validate_smol_runtime,
    validate_trusted_intake,
    validate_environment,
    validate_private_host_inputs,
    validate_demo_identity_host_inputs,
    validate_local_data_host_inputs,
    run_proof_group,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("compose_arguments", nargs=argparse.REMAINDER)
    return parser.parse_args()


def resume_release(environment_path: Path, values: dict[str, str]) -> int:
    """Reconcile an installed release after reboot, without pulling or migrating."""
    checker_config = load_checker_config(Path(values["WORKSTREAM_CHECKER_CONFIG_FILE"]))
    validate_checker_config(checker_config, values)
    validate_private_host_inputs(values, require_node=False)
    phases: list[list[str]] = []
    if values.get("WORKSTREAM_POSTGRES_IMAGE"):
        phases.append(["start", "local-data"])
    if values.get("DEMO_IDENTITY_IMAGE"):
        phases.append(["start", "demo-identity"])
    if values["WORKSTREAM_MODEL_PROXY_ENABLED"] == "true":
        phases.append(["up", "--detach", "--no-deps", "--wait",
                       "--wait-timeout", "60", "model-proxy"])
    for phase in phases:
        result = run_compose(environment_path, values, phase, cached_images=True)
        if result:
            return result
    try:
        for operation in ("reset-failed", "start"):
            result = subprocess.run(
                ["systemctl", operation, "workstream-checker.service"],
                check=False, timeout=60, env=compose_environment(values),
            )
            if result.returncode:
                return result.returncode
    except (OSError, subprocess.SubprocessError) as exc:
        raise PreflightError("native checker startup did not complete") from exc
    deadline = time.monotonic() + 120
    while True:
        try:
            validate_private_host_inputs(values)
            validate_smol_runtime(checker_config, values)
            validate_trusted_intake(values)
            break
        except PreflightError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(2)
    return run_compose(
        environment_path, values,
        ["up", "--detach", "--wait", "--wait-timeout", "120"],
        cached_images=True,
    )


def main() -> int:
    args = parse_args()
    try:
        values = parse_environment(args.env_file)
        validate_environment(values)
        validate_compose(render_compose(args.env_file, values), values)
        if args.compose_arguments == ["resume"]:
            return resume_release(args.env_file, values)
        if args.compose_arguments == ["start", "local-data"]:
            if not values.get("WORKSTREAM_POSTGRES_IMAGE"):
                raise PreflightError("local data bootstrap requires its overlay")
            validate_local_data_host_inputs(values)
            return run_compose(args.env_file, values, args.compose_arguments)
        if args.compose_arguments == ["start", "demo-identity"]:
            if not values.get("DEMO_IDENTITY_IMAGE"):
                raise PreflightError(
                    "demo identity bootstrap requires the issuer overlay"
                )
            validate_demo_identity_host_inputs(values)
            return run_compose(args.env_file, values, args.compose_arguments)
        worker_start = args.compose_arguments == ["start", "worker"]
        launch = worker_start or (
            args.compose_arguments and args.compose_arguments[0] in {"up", "proof"}
        )
        proxy_bootstrap = args.compose_arguments in (
            ["up", "-d", "model-proxy"],
            ["up", "--detach", "model-proxy"],
        )
        migration = args.compose_arguments == ["migrate"]
        points = bool(
            args.compose_arguments
            and args.compose_arguments[0] == "provision-project-points"
        )
        proof_bootstrap = bool(
            args.compose_arguments and args.compose_arguments[0] == "proof"
        )
        if proxy_bootstrap and values["WORKSTREAM_MODEL_PROXY_ENABLED"] != "true":
            raise PreflightError("model proxy bootstrap requires an enabled proxy")
        if launch or migration or points:
            checker_config = load_checker_config(
                Path(values["WORKSTREAM_CHECKER_CONFIG_FILE"])
            )
            validate_checker_config(checker_config, values)
            if proxy_bootstrap or migration or proof_bootstrap or points:
                # No API, worker or producer is released in these fixed stages.
                validate_private_host_inputs(values, require_node=False)
            else:
                validate_private_host_inputs(values)
                validate_smol_runtime(checker_config, values)
                validate_trusted_intake(values)
        if args.compose_arguments and args.compose_arguments[0] == "proof":
            if (
                len(args.compose_arguments) != 3
                or args.compose_arguments[1] != "--group-nonce"
            ):
                raise PreflightError("proof requires one explicit group nonce")
            try:
                group_nonce = UUID(args.compose_arguments[2])
            except ValueError as exc:
                raise PreflightError("proof group nonce is invalid") from exc
            return run_proof_group(args.env_file, values, group_nonce)
        if args.compose_arguments and args.compose_arguments[0] == "stop":
            if args.compose_arguments == ["stop", "worker"]:
                return run_compose(args.env_file, values, args.compose_arguments)
            if args.compose_arguments != ["stop"]:
                raise PreflightError(
                    "stop requires the fixed shutdown sequence or exactly one worker"
                )
            return run_shutdown(args.env_file, values)
        return run_compose(args.env_file, values, args.compose_arguments)
    except PreflightError as exc:
        print(f"hosted Compose command failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
