"""Run one fixed AWS artifact proof mode or coordinate one exact proof group."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from uuid import UUID

from app.adapters.artifacts.aws_live_proof import AwsArtifactLiveProof
from app.adapters.artifacts.s3_compatible import aws_s3_namespace_fingerprint
from app.core.config import get_settings
from app.db.session import dispose_engine, get_session_factory
from app.modules.artifacts.provider_activation import (
    artifact_provider_database_time,
    coordinate_artifact_provider_activation,
    record_artifact_provider_probe_result,
)

_PROBE_MODES = ("readiness", "runtime_immutability", "negative_access")


async def run(mode: str, group_nonce: UUID) -> dict[str, object]:
    """Persist actual observations; coordinate without constructing an AWS transport."""
    settings = get_settings()
    namespace_fingerprint = aws_s3_namespace_fingerprint(settings)
    sessions = get_session_factory()
    try:
        if mode == "coordinate":
            async with sessions() as session, session.begin():
                activation_id = await coordinate_artifact_provider_activation(
                    session,
                    settings,
                    namespace_fingerprint=namespace_fingerprint,
                    group_nonce=group_nonce,
                )
            return {
                "result": "activated",
                "activation_id": str(activation_id),
                "group_nonce": str(group_nonce),
            }

        async with sessions() as session, session.begin():
            started_at = await artifact_provider_database_time(session)
        proof = AwsArtifactLiveProof(settings)
        observation = await proof.run(mode, group_nonce=group_nonce)  # type: ignore[arg-type]
        async with sessions() as session, session.begin():
            result_id = await record_artifact_provider_probe_result(
                session,
                settings,
                probe_type=observation.probe_type,
                namespace_fingerprint=namespace_fingerprint,
                group_nonce=group_nonce,
                expected_principal_arn=observation.expected_principal_arn,
                observed_principal_arn=observation.observed_principal_arn,
                passed=observation.passed,
                evidence=observation.evidence,
                error_code=observation.error_code,
                started_at=started_at,
            )
        return {
            "result": "passed" if observation.passed else "failed",
            "probe_type": mode,
            "probe_result_id": str(result_id),
            "group_nonce": str(group_nonce),
            "error_code": observation.error_code,
        }
    finally:
        await dispose_engine()


def main() -> int:
    """Parse one non-secret group identity and print only bounded result metadata."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=(*_PROBE_MODES, "coordinate"))
    parser.add_argument("--group-nonce", type=UUID, required=True)
    args = parser.parse_args()
    try:
        result = asyncio.run(run(args.mode, args.group_nonce))
    except Exception:
        print(
            json.dumps({"result": "infrastructure_failure", "error_code": "proof_command_failed"}),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0 if result["result"] in {"passed", "activated"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
