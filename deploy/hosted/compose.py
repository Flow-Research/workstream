#!/usr/bin/env python3
"""Run the bounded hosted Compose file without ambient interpolation."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from preflight import (
    PreflightError,
    parse_environment,
    render_compose,
    run_compose,
    run_shutdown,
    validate_compose,
    validate_environment,
    validate_private_host_inputs,
    validate_identity_host_inputs,
    validate_local_data_host_inputs,
    validate_typed_submission_profiles,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("compose_arguments", nargs=argparse.REMAINDER)
    return parser.parse_args()


def resume_release(environment_path: Path, values: dict[str, str]) -> int:
    """Reconcile an installed release after reboot, without pulling or migrating."""
    validate_private_host_inputs(values, require_node=False)
    validate_typed_submission_profiles(
        environment_path, values, cached_images=True
    )
    phases: list[list[str]] = []
    if values.get("WORKSTREAM_POSTGRES_IMAGE"):
        phases.append(["start", "local-data"])
    if values.get("FLOW_IDENTITY_IMAGE"):
        phases.append(["start", "identity"])
    if values["WORKSTREAM_MODEL_PROXY_ENABLED"] == "true":
        phases.append(["up", "--detach", "--no-deps", "--wait",
                       "--wait-timeout", "60", "model-proxy"])
    for phase in phases:
        result = run_compose(environment_path, values, phase, cached_images=True)
        if result:
            return result
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
        if args.compose_arguments == ["start", "identity"]:
            if not values.get("FLOW_IDENTITY_IMAGE"):
                raise PreflightError(
                    "identity startup requires the Keycloak overlay"
                )
            validate_identity_host_inputs(values)
            return run_compose(args.env_file, values, args.compose_arguments)
        worker_start = args.compose_arguments == ["start", "worker"]
        launch = worker_start or (
            args.compose_arguments and args.compose_arguments[0] == "up"
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
        if proxy_bootstrap and values["WORKSTREAM_MODEL_PROXY_ENABLED"] != "true":
            raise PreflightError("model proxy bootstrap requires an enabled proxy")
        if launch or migration or points:
            if proxy_bootstrap or migration or points:
                # No API, worker or producer is released in these fixed stages.
                validate_private_host_inputs(values, require_node=False)
            else:
                validate_private_host_inputs(values)
            if launch:
                validate_typed_submission_profiles(args.env_file, values)
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
