"""Build exact PRE and POST registration inputs for the incident-summary image."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

from app.modules.checkers.api.external import (  # noqa: E402
    ExternalCheckerRegistrySpec,
    ExternalCheckerResourceLimits,
    ExternalCheckerSchema,
    external_checker_json_hash,
)

CHECKS = {
    "pre": ("pre_submit", "incident_summary_layout"),
    "post": ("post_submit", "incident_summary_counts"),
}


def _schema(identifier: str, document: dict) -> ExternalCheckerSchema:
    return ExternalCheckerSchema(
        schema_id=identifier,
        schema_version="v1",
        document=document,
        schema_sha256=external_checker_json_hash(document),
    )


def registry_spec(phase: str, image_digest: str) -> ExternalCheckerRegistrySpec:
    stage, check = CHECKS[phase]
    return ExternalCheckerRegistrySpec(
        capability_id="terminal.incident_summary",
        capability_version="v1",
        phase=stage,
        image_digest=image_digest,
        configuration_schema=_schema(
            "checker.configuration",
            {
                "type": "object",
                "properties": {"check": {"const": check}},
                "required": ["check"],
                "additionalProperties": False,
            },
        ),
        input_schema=_schema(f"external_checker_{stage}_input", {"type": "object"}),
        output_schema=_schema("external_checker_result", {"type": "object"}),
        resources=ExternalCheckerResourceLimits(
            cpu_millis=500,
            memory_bytes=128 * 1024 * 1024,
            deadline_ms=30_000,
            maximum_output_bytes=32_768,
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-digest", required=True)
    parser.add_argument("--pre", type=Path, required=True)
    parser.add_argument("--post", type=Path, required=True)
    arguments = parser.parse_args()
    if re.fullmatch(r"sha256:[0-9a-f]{64}", arguments.image_digest) is None:
        parser.error("image digest must be canonical sha256")
    if arguments.pre == arguments.post:
        parser.error("PRE and POST registry files must differ")
    for phase in CHECKS:
        path = getattr(arguments, phase)
        spec = registry_spec(phase, arguments.image_digest)
        with path.open("x", encoding="utf-8") as stream:
            path.chmod(0o600)
            json.dump(spec.model_dump(mode="json"), stream, indent=2, sort_keys=True)
            stream.write("\n")


if __name__ == "__main__":
    main()
