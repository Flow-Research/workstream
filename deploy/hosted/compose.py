#!/usr/bin/env python3
"""Run the bounded hosted Compose file without ambient interpolation."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from preflight import (
    PreflightError,
    load_checker_config,
    parse_environment,
    render_compose,
    run_compose,
    validate_checker_config,
    validate_compose,
    validate_docker_runtime,
    validate_environment,
    validate_private_host_inputs,
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
        validate_compose(render_compose(args.env_file, values))
        if args.compose_arguments and args.compose_arguments[0] == "up":
            checker_config = load_checker_config(Path(values["WORKSTREAM_CHECKER_CONFIG_FILE"]))
            validate_checker_config(checker_config, values)
            validate_private_host_inputs(values)
            validate_docker_runtime(checker_config, values)
        return run_compose(args.env_file, values, args.compose_arguments)
    except PreflightError as exc:
        print(f"hosted Compose command failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
