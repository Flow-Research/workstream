#!/usr/bin/env python3
"""Run the bounded hosted Compose file without ambient interpolation."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from uuid import UUID

from preflight import (
    PreflightError,
    load_checker_config,
    parse_environment,
    render_compose,
    run_compose,
    run_shutdown,
    validate_checker_config,
    validate_compose,
    validate_docker_runtime,
    validate_trusted_intake,
    validate_environment,
    validate_private_host_inputs,
    run_proof_group,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("compose_arguments", nargs=argparse.REMAINDER)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        values = parse_environment(args.env_file)
        validate_environment(values)
        validate_compose(render_compose(args.env_file, values), values)
        launch = args.compose_arguments and args.compose_arguments[0] in {"up", "proof"}
        if launch:
            checker_config = load_checker_config(
                Path(values["WORKSTREAM_CHECKER_CONFIG_FILE"])
            )
            validate_checker_config(checker_config, values)
            validate_private_host_inputs(values)
            validate_docker_runtime(checker_config, values)
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
            if args.compose_arguments != ["stop"]:
                raise PreflightError(
                    "stop uses the fixed producer, worker, parser/checker sequence"
                )
            return run_shutdown(args.env_file, values)
        return run_compose(args.env_file, values, args.compose_arguments)
    except PreflightError as exc:
        print(f"hosted Compose command failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
