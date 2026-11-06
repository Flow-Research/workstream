#!/usr/bin/env python3
"""Publish the Garden proof image locally and emit separate PRE/POST registrations."""

from __future__ import annotations

import argparse
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "harnessy_publish", HERE.parent / "harnessy_proof/publish_local.py"
)
assert _spec is not None and _spec.loader is not None
shared = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(shared)

PRE_CONFIGURATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["repository", "forge_origin"],
    "properties": {
        "repository": {"const": "Flow-Research/garden"},
        "forge_origin": {"const": "https://github.com"},
    },
}


def registry_spec(image_digest: str, capability_version: str, phase: str) -> dict:
    if phase not in {"pre_submit", "post_submit"}:
        raise ValueError("Garden proof supports PRE and POST only")
    spec = shared.registry_spec(image_digest, capability_version)
    spec["capability_id"] = "garden.work_proof"
    spec["phase"] = phase
    configuration = deepcopy(shared.CONFIGURATION_SCHEMA)
    configuration["properties"]["repository"] = {"const": "Flow-Research/garden"}
    configuration["properties"]["forge_origin"] = {"const": "https://github.com"}
    configuration["properties"]["required_independent_approvals"]["minimum"] = 0
    if phase == "pre_submit":
        configuration = PRE_CONFIGURATION_SCHEMA
        spec["input_schema"] = shared._schema("external_checker_pre_submit_input")
        output = deepcopy(shared.OUTPUT_SCHEMA["oneOf"][1])
        output["properties"]["phase"] = {"const": phase}
        spec["output_schema"] = shared._schema("external_checker_result", output)
    spec["configuration_schema"] = shared._schema(
        "garden.work_proof.configuration", configuration
    )
    return spec


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--repository", default="garden-proof")
    parser.add_argument("--compose-project", required=True)
    parser.add_argument("--sandbox-uid", type=int, required=True)
    parser.add_argument("--sandbox-gid", type=int, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--capability-version", default="v3")
    args = parser.parse_args()
    image = shared.publish(
        args.registry,
        args.repository,
        build_context=HERE.parent,
        dockerfile=HERE / "Dockerfile",
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "checker-service.json": shared.service_config(
            image,
            compose_project=args.compose_project,
            sandbox_uid=args.sandbox_uid,
            sandbox_gid=args.sandbox_gid,
        )
    }
    outputs.update(
        {
            "registry-" + short + ".json": registry_spec(
                image["platform_manifest_digest"], args.capability_version, phase
            )
            for short, phase in (("pre", "pre_submit"), ("post", "post_submit"))
        }
    )
    for name, value in outputs.items():
        (args.out_dir / name).write_text(
            json.dumps(value, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps({"image": image, "written": sorted(outputs)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
