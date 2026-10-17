"""ART-owned custody and runtime checks for native AWS artifact activation."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import (
    ARTIFACT_AWS_ACTIVATION_VALIDITY_SECONDS,
    ARTIFACT_AWS_CLOCK_SAFETY_MARGIN_SECONDS,
    Settings,
)
from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.interfaces.artifacts import (
    ArtifactProviderActivationGuard,
    ArtifactProviderActivationLease,
    ArtifactProviderLiveProofRequiredError,
)
from app.modules.artifacts.models import (
    ArtifactProviderActivation,
    ArtifactProviderProbeResult,
)

AWS_ARTIFACT_PROOF_VERSION = "aws-s3-live-v1"
_REQUIRED_PROBE_TYPES = (
    "readiness",
    "runtime_immutability",
    "negative_access",
)
ArtifactProviderProbeType = Literal[
    "readiness",
    "runtime_immutability",
    "negative_access",
]


def _required(value: str | None, name: str) -> str:
    """Reject an absent member of the exact activation binding tuple."""
    if value is None:
        raise ArtifactProviderLiveProofRequiredError(
            f"AWS artifact activation {name} is unavailable"
        )
    return value


def expected_artifact_probe_principal(
    settings: Settings,
    probe_type: ArtifactProviderProbeType,
) -> str:
    """Return the only configured role allowed to execute one proof mode."""
    values = {
        "readiness": settings.artifact_s3_readiness_role_arn,
        "runtime_immutability": settings.artifact_s3_runtime_role_arn,
        "negative_access": settings.artifact_s3_negative_role_arn,
    }
    try:
        value = values[probe_type]
    except KeyError as exc:
        raise ArtifactProviderLiveProofRequiredError(
            "AWS artifact probe identity is invalid"
        ) from exc
    return _required(value, f"{probe_type} role")


def _activation_filters(
    settings: Settings,
    *,
    namespace_fingerprint: str,
) -> tuple[object, ...]:
    """Return the exact non-secret deployment tuple used by every activation read."""
    return (
        ArtifactProviderActivation.proof_version == AWS_ARTIFACT_PROOF_VERSION,
        ArtifactProviderActivation.release_id == _required(settings.release_id, "release"),
        ArtifactProviderActivation.namespace_fingerprint == namespace_fingerprint,
        ArtifactProviderActivation.region == _required(settings.artifact_s3_region, "region"),
        ArtifactProviderActivation.runtime_role_arn
        == _required(settings.artifact_s3_runtime_role_arn, "runtime role"),
        ArtifactProviderActivation.runtime_trust_policy_sha256
        == _required(
            settings.artifact_s3_runtime_trust_policy_sha256,
            "runtime trust policy",
        ),
        ArtifactProviderActivation.runtime_policy_arn
        == _required(settings.artifact_s3_runtime_policy_arn, "runtime policy"),
        ArtifactProviderActivation.readiness_role_arn
        == _required(settings.artifact_s3_readiness_role_arn, "readiness role"),
        ArtifactProviderActivation.readiness_trust_policy_sha256
        == _required(
            settings.artifact_s3_readiness_trust_policy_sha256,
            "readiness trust policy",
        ),
        ArtifactProviderActivation.readiness_policy_arn
        == _required(settings.artifact_s3_readiness_policy_arn, "readiness policy"),
        ArtifactProviderActivation.negative_role_arn
        == _required(settings.artifact_s3_negative_role_arn, "negative role"),
        ArtifactProviderActivation.negative_trust_policy_sha256
        == _required(
            settings.artifact_s3_negative_trust_policy_sha256,
            "negative trust policy",
        ),
        ArtifactProviderActivation.bootstrap_principal_arn
        == _required(settings.artifact_s3_bootstrap_principal_arn, "bootstrap principal"),
        ArtifactProviderActivation.bucket_policy_sha256
        == _required(settings.artifact_s3_bucket_policy_sha256, "bucket policy digest"),
    )


def _minimum_remaining_seconds(settings: Settings) -> float:
    """Return the fixed AWS operation, persistence and clock-safety bound."""
    return (
        max(
            settings.artifact_s3_operation_total_timeout_seconds,
            settings.artifact_complete_read_deadline_seconds,
        )
        + settings.artifact_terminal_persistence_margin_seconds
        + ARTIFACT_AWS_CLOCK_SAFETY_MARGIN_SECONDS
    )


async def artifact_provider_database_time(session: AsyncSession) -> datetime:
    """Read authoritative PostgreSQL time for a probe boundary."""
    observed = await session.scalar(select(func.clock_timestamp()))
    if not isinstance(observed, datetime):
        raise ArtifactProviderLiveProofRequiredError("database time is unavailable")
    return observed


async def record_artifact_provider_probe_result(
    session: AsyncSession,
    settings: Settings,
    *,
    probe_type: ArtifactProviderProbeType,
    namespace_fingerprint: str,
    group_nonce: UUID,
    expected_principal_arn: str,
    observed_principal_arn: str | None,
    passed: bool,
    evidence: dict[str, object],
    error_code: str | None,
    started_at: datetime,
) -> UUID:
    """Persist only bounded observations produced by one completed proof call set."""
    if probe_type not in _REQUIRED_PROBE_TYPES or type(group_nonce) is not UUID:
        raise ArtifactProviderLiveProofRequiredError("AWS artifact probe identity is invalid")
    if expected_principal_arn != expected_artifact_probe_principal(settings, probe_type):
        raise ArtifactProviderLiveProofRequiredError(
            "AWS artifact probe principal does not match its proof mode"
        )
    if (
        passed and (error_code is not None or observed_principal_arn != expected_principal_arn)
    ) or (not passed and error_code is None):
        raise ArtifactProviderLiveProofRequiredError("AWS artifact probe result is inconsistent")
    completed_at = await artifact_provider_database_time(session)
    if completed_at < started_at:
        raise ArtifactProviderLiveProofRequiredError("AWS artifact probe time is invalid")
    arn_parts = expected_principal_arn.split(":", 5)
    if len(arn_parts) != 6 or arn_parts[0] != "arn" or not arn_parts[4].isdigit():
        raise ArtifactProviderLiveProofRequiredError("AWS artifact probe principal is invalid")
    result = ArtifactProviderProbeResult(
        id=str(new_record_id()),
        probe_type=probe_type,
        proof_version=AWS_ARTIFACT_PROOF_VERSION,
        result="pass" if passed else "fail",
        release_id=_required(settings.release_id, "release"),
        namespace_fingerprint=namespace_fingerprint,
        aws_partition=arn_parts[1],
        aws_account_id=arn_parts[4],
        region=_required(settings.artifact_s3_region, "region"),
        runtime_role_arn=_required(settings.artifact_s3_runtime_role_arn, "runtime role"),
        runtime_trust_policy_sha256=_required(
            settings.artifact_s3_runtime_trust_policy_sha256,
            "runtime trust policy",
        ),
        runtime_policy_arn=_required(
            settings.artifact_s3_runtime_policy_arn,
            "runtime policy",
        ),
        readiness_role_arn=_required(
            settings.artifact_s3_readiness_role_arn,
            "readiness role",
        ),
        readiness_trust_policy_sha256=_required(
            settings.artifact_s3_readiness_trust_policy_sha256,
            "readiness trust policy",
        ),
        readiness_policy_arn=_required(
            settings.artifact_s3_readiness_policy_arn,
            "readiness policy",
        ),
        negative_role_arn=_required(settings.artifact_s3_negative_role_arn, "negative role"),
        negative_trust_policy_sha256=_required(
            settings.artifact_s3_negative_trust_policy_sha256,
            "negative trust policy",
        ),
        bootstrap_principal_arn=_required(
            settings.artifact_s3_bootstrap_principal_arn,
            "bootstrap principal",
        ),
        bucket_policy_sha256=_required(
            settings.artifact_s3_bucket_policy_sha256,
            "bucket policy digest",
        ),
        expected_principal_arn=expected_principal_arn,
        observed_principal_arn=observed_principal_arn,
        group_nonce=str(group_nonce),
        evidence_sha256=canonical_json_hash(evidence),
        error_code=error_code,
        started_at=started_at,
        completed_at=completed_at,
        expires_at=started_at + timedelta(seconds=ARTIFACT_AWS_ACTIVATION_VALIDITY_SECONDS),
    )
    session.add(result)
    await session.flush()
    return UUID(result.id)


class SqlAlchemyArtifactProviderActivationGuard(ArtifactProviderActivationGuard):
    """Resolve exact live AWS activation through isolated short database sessions."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        """Bind activation reads to isolated sessions and native AWS settings."""
        if settings.artifact_s3_provider_profile != "aws_s3":
            raise ValueError("AWS artifact activation guard requires native AWS settings")
        self._sessions = sessions
        self._settings = settings

    async def select_for_call(
        self,
        *,
        namespace_fingerprint: str,
    ) -> ArtifactProviderActivationLease:
        """Select the deterministic eligible activation for a new AWS call."""
        statement = (
            self._eligible(namespace_fingerprint)
            .order_by(
                ArtifactProviderActivation.expires_at.desc(),
                ArtifactProviderActivation.activated_at.desc(),
                ArtifactProviderActivation.id.desc(),
            )
            .limit(1)
        )
        return await self._load(statement)

    async def require_for_call(
        self,
        activation_id: UUID,
        *,
        namespace_fingerprint: str,
    ) -> ArtifactProviderActivationLease:
        """Reload the same eligible activation immediately before an AWS call."""
        if type(activation_id) is not UUID:
            raise ArtifactProviderLiveProofRequiredError(
                "AWS artifact activation identity is invalid"
            )
        return await self._load(
            self._eligible(namespace_fingerprint).where(
                ArtifactProviderActivation.id == str(activation_id)
            )
        )

    def _eligible(self, namespace_fingerprint: str) -> Select[tuple[ArtifactProviderActivation]]:
        """Build the exact deployment-binding and remaining-validity query."""
        remaining = timedelta(seconds=_minimum_remaining_seconds(self._settings))
        return select(ArtifactProviderActivation).where(
            *_activation_filters(
                self._settings,
                namespace_fingerprint=namespace_fingerprint,
            ),
            ArtifactProviderActivation.expires_at >= func.clock_timestamp() + remaining,
        )

    async def _load(
        self,
        statement: Select[tuple[ArtifactProviderActivation]],
    ) -> ArtifactProviderActivationLease:
        """Resolve one activation in its own short database transaction."""
        async with self._sessions() as session, session.begin():
            activation = await session.scalar(statement)
        if activation is None:
            raise ArtifactProviderLiveProofRequiredError(
                "AWS artifact provider requires fresh exact live proof"
            )
        return ArtifactProviderActivationLease(UUID(activation.id))


async def require_provider_activation_for_terminal(
    session: AsyncSession,
    settings: Settings,
    *,
    namespace_fingerprint: str,
    activation_id: UUID | None,
) -> ArtifactProviderActivation:
    """Reload the exact operation activation before a provider-derived terminal fact."""
    if settings.artifact_s3_provider_profile != "aws_s3":
        raise ValueError("terminal activation checks apply only to native AWS")
    if type(activation_id) is not UUID:
        raise ArtifactProviderLiveProofRequiredError(
            "AWS artifact operation lacks an activation identity"
        )
    activation = await session.scalar(
        select(ArtifactProviderActivation)
        .where(
            ArtifactProviderActivation.id == str(activation_id),
            *_activation_filters(settings, namespace_fingerprint=namespace_fingerprint),
            ArtifactProviderActivation.expires_at > func.clock_timestamp(),
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if activation is None:
        raise ArtifactProviderLiveProofRequiredError(
            "AWS artifact operation activation expired before terminal evidence"
        )
    return activation


async def coordinate_artifact_provider_activation(
    session: AsyncSession,
    settings: Settings,
    *,
    namespace_fingerprint: str,
    group_nonce: UUID,
) -> UUID:
    """Create one immutable activation from an exact unexpired three-probe group."""
    if settings.artifact_s3_provider_profile != "aws_s3" or type(group_nonce) is not UUID:
        raise ArtifactProviderLiveProofRequiredError("AWS artifact proof group is invalid")
    rows = tuple(
        (
            await session.scalars(
                select(ArtifactProviderProbeResult)
                .where(
                    ArtifactProviderProbeResult.group_nonce == str(group_nonce),
                    ArtifactProviderProbeResult.proof_version == AWS_ARTIFACT_PROOF_VERSION,
                    ArtifactProviderProbeResult.result == "pass",
                    ArtifactProviderProbeResult.release_id
                    == _required(settings.release_id, "release"),
                    ArtifactProviderProbeResult.namespace_fingerprint == namespace_fingerprint,
                    ArtifactProviderProbeResult.region
                    == _required(settings.artifact_s3_region, "region"),
                    ArtifactProviderProbeResult.runtime_role_arn
                    == _required(settings.artifact_s3_runtime_role_arn, "runtime role"),
                    ArtifactProviderProbeResult.runtime_trust_policy_sha256
                    == _required(
                        settings.artifact_s3_runtime_trust_policy_sha256,
                        "runtime trust policy",
                    ),
                    ArtifactProviderProbeResult.runtime_policy_arn
                    == _required(settings.artifact_s3_runtime_policy_arn, "runtime policy"),
                    ArtifactProviderProbeResult.readiness_role_arn
                    == _required(settings.artifact_s3_readiness_role_arn, "readiness role"),
                    ArtifactProviderProbeResult.readiness_trust_policy_sha256
                    == _required(
                        settings.artifact_s3_readiness_trust_policy_sha256,
                        "readiness trust policy",
                    ),
                    ArtifactProviderProbeResult.readiness_policy_arn
                    == _required(settings.artifact_s3_readiness_policy_arn, "readiness policy"),
                    ArtifactProviderProbeResult.negative_role_arn
                    == _required(settings.artifact_s3_negative_role_arn, "negative role"),
                    ArtifactProviderProbeResult.negative_trust_policy_sha256
                    == _required(
                        settings.artifact_s3_negative_trust_policy_sha256,
                        "negative trust policy",
                    ),
                    ArtifactProviderProbeResult.bootstrap_principal_arn
                    == _required(
                        settings.artifact_s3_bootstrap_principal_arn,
                        "bootstrap principal",
                    ),
                    ArtifactProviderProbeResult.bucket_policy_sha256
                    == _required(
                        settings.artifact_s3_bucket_policy_sha256,
                        "bucket policy digest",
                    ),
                    ArtifactProviderProbeResult.expected_principal_arn
                    == ArtifactProviderProbeResult.observed_principal_arn,
                    ArtifactProviderProbeResult.expires_at > func.clock_timestamp(),
                )
                .order_by(ArtifactProviderProbeResult.probe_type)
                .with_for_update()
            )
        ).all()
    )
    by_type = {row.probe_type: row for row in rows}
    if len(rows) != 3 or set(by_type) != set(_REQUIRED_PROBE_TYPES):
        raise ArtifactProviderLiveProofRequiredError(
            "AWS artifact proof group is incomplete or mixed"
        )
    if any(
        row.expected_principal_arn != expected_artifact_probe_principal(settings, row.probe_type)
        for row in rows
    ):
        raise ArtifactProviderLiveProofRequiredError(
            "AWS artifact proof result principal does not match its proof mode"
        )
    canonical = by_type["readiness"]
    exact_fields = (
        "proof_version",
        "release_id",
        "namespace_fingerprint",
        "aws_partition",
        "aws_account_id",
        "region",
        "runtime_role_arn",
        "runtime_trust_policy_sha256",
        "runtime_policy_arn",
        "readiness_role_arn",
        "readiness_trust_policy_sha256",
        "readiness_policy_arn",
        "negative_role_arn",
        "negative_trust_policy_sha256",
        "bootstrap_principal_arn",
        "bucket_policy_sha256",
        "group_nonce",
    )
    if any(
        any(getattr(row, field) != getattr(canonical, field) for field in exact_fields)
        for row in rows
    ):
        raise ArtifactProviderLiveProofRequiredError("AWS artifact proof results do not match")
    runtime = by_type["runtime_immutability"]
    if (
        runtime.completed_at > by_type["readiness"].started_at
        or runtime.completed_at > by_type["negative_access"].started_at
    ):
        raise ArtifactProviderLiveProofRequiredError(
            "AWS artifact proof runtime challenge was not established first"
        )
    now = await session.scalar(select(func.clock_timestamp()))
    if now is None:
        raise ArtifactProviderLiveProofRequiredError("database time is unavailable")
    superseded = await session.scalar(
        select(ArtifactProviderActivation)
        .where(
            *_activation_filters(settings, namespace_fingerprint=namespace_fingerprint),
        )
        .order_by(
            ArtifactProviderActivation.activated_at.desc(),
            ArtifactProviderActivation.id.desc(),
        )
        .limit(1)
        .with_for_update()
    )
    activation = ArtifactProviderActivation(
        id=str(new_record_id()),
        readiness_result_id=by_type["readiness"].id,
        runtime_result_id=by_type["runtime_immutability"].id,
        negative_result_id=by_type["negative_access"].id,
        supersedes_activation_id=None if superseded is None else superseded.id,
        proof_version=canonical.proof_version,
        release_id=canonical.release_id,
        namespace_fingerprint=canonical.namespace_fingerprint,
        aws_partition=canonical.aws_partition,
        aws_account_id=canonical.aws_account_id,
        region=canonical.region,
        runtime_role_arn=canonical.runtime_role_arn,
        runtime_trust_policy_sha256=canonical.runtime_trust_policy_sha256,
        runtime_policy_arn=canonical.runtime_policy_arn,
        readiness_role_arn=canonical.readiness_role_arn,
        readiness_trust_policy_sha256=canonical.readiness_trust_policy_sha256,
        readiness_policy_arn=canonical.readiness_policy_arn,
        negative_role_arn=canonical.negative_role_arn,
        negative_trust_policy_sha256=canonical.negative_trust_policy_sha256,
        bootstrap_principal_arn=canonical.bootstrap_principal_arn,
        bucket_policy_sha256=canonical.bucket_policy_sha256,
        group_nonce=canonical.group_nonce,
        activated_at=now,
        expires_at=min(row.expires_at for row in rows),
    )
    session.add(activation)
    await session.flush()
    return UUID(activation.id)
