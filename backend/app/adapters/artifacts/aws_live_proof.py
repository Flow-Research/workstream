"""Proof-only native AWS calls for artifact-provider activation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Literal
from urllib.parse import unquote
from uuid import UUID

from aiobotocore.config import AioConfig
from aiobotocore.session import AioSession
from botocore import UNSIGNED
from botocore.exceptions import BotoCoreError, ClientError

from app.adapters.artifacts.s3_compatible import (
    create_isolated_aws_workload_identity_session,
)
from app.core.config import Settings
from app.core.hashing import canonical_json_hash
from app.interfaces.artifacts import ArtifactConfigurationError

AwsArtifactProbeType = Literal[
    "readiness",
    "runtime_immutability",
    "negative_access",
]

_BUCKET_ACTIONS = frozenset(
    {
        "s3:GetBucketPolicy",
        "s3:GetBucketPolicyStatus",
        "s3:GetBucketAcl",
        "s3:GetBucketPublicAccessBlock",
        "s3:GetBucketOwnershipControls",
        "s3:GetBucketVersioning",
        "s3:GetLifecycleConfiguration",
        "s3:GetEncryptionConfiguration",
    }
)
_ROLE_INSPECTION_ACTIONS = frozenset(
    {"iam:GetRole", "iam:ListRolePolicies", "iam:ListAttachedRolePolicies"}
)
_POLICY_INSPECTION_ACTIONS = frozenset({"iam:GetPolicy", "iam:GetPolicyVersion"})
_ANALYZER_ACTIONS = frozenset(
    {
        "access-analyzer:ValidatePolicy",
        "access-analyzer:CheckAccessNotGranted",
        "access-analyzer:CheckNoPublicAccess",
    }
)


@dataclass(frozen=True, slots=True)
class AwsArtifactProbeObservation:
    """Secret-free bounded facts returned by one fixed live proof mode."""

    probe_type: AwsArtifactProbeType
    expected_principal_arn: str
    observed_principal_arn: str | None
    passed: bool
    error_code: str | None
    evidence: dict[str, object]


class AwsArtifactLiveProof:
    """Run one identity-bound proof mode without production-store injection."""

    def __init__(self, settings: Settings, session: AioSession | None = None) -> None:
        if settings.artifact_s3_provider_profile != "aws_s3":
            raise ArtifactConfigurationError("AWS artifact proof requires native AWS settings")
        self._settings = settings
        self._session = session or create_isolated_aws_workload_identity_session(settings)
        self._config = AioConfig(
            connect_timeout=settings.artifact_s3_connect_timeout_seconds,
            read_timeout=settings.artifact_s3_read_timeout_seconds,
            retries={"max_attempts": 1, "mode": "standard"},
            proxies={},
            s3={"addressing_style": settings.artifact_s3_addressing_style},
        )

    async def run(
        self,
        probe_type: AwsArtifactProbeType,
        *,
        group_nonce: UUID,
    ) -> AwsArtifactProbeObservation:
        """Bind STS identity first, then execute only the selected fixed call set."""
        expected = self._expected_principal(probe_type)
        observed: str | None = None
        evidence: dict[str, object] = {"suite": "aws-s3-live-v1", "mode": probe_type}
        try:
            observed = await self._observe_principal(expected)
            if observed != expected:
                return self._failed(probe_type, expected, observed, "identity_mismatch", evidence)
            if probe_type == "readiness":
                evidence.update(await self._readiness(group_nonce))
            elif probe_type == "runtime_immutability":
                evidence.update(await self._runtime_immutability(group_nonce))
            elif probe_type == "negative_access":
                evidence.update(await self._negative_access(group_nonce))
            else:
                raise ArtifactConfigurationError("AWS artifact proof mode is invalid")
        except (
            ArtifactConfigurationError,
            BotoCoreError,
            ClientError,
            OSError,
            TimeoutError,
        ) as error:
            return self._failed(
                probe_type,
                expected,
                observed,
                _bounded_error_code(error),
                evidence,
            )
        except Exception:
            return self._failed(
                probe_type,
                expected,
                observed,
                "proof_transport_failed",
                evidence,
            )
        return AwsArtifactProbeObservation(
            probe_type=probe_type,
            expected_principal_arn=expected,
            observed_principal_arn=observed,
            passed=True,
            error_code=None,
            evidence=evidence,
        )

    async def _observe_principal(self, expected: str) -> str:
        async with self._session.create_client(
            "sts",
            region_name=self._required(self._settings.artifact_s3_region),
            config=self._config,
        ) as client:
            response = await client.get_caller_identity()
        arn = response.get("Arn")
        if not isinstance(arn, str):
            raise ArtifactConfigurationError("AWS proof identity response is invalid")
        return _canonical_observed_role_arn(arn, expected)

    async def _runtime_immutability(self, group_nonce: UUID) -> dict[str, object]:
        content, key, missing_key = self._challenge(group_nonce)
        bucket = self._required(self._settings.artifact_s3_bucket)
        async with self._session.create_client(
            "s3",
            region_name=self._required(self._settings.artifact_s3_region),
            config=self._config,
        ) as client:
            first_put_replayed = False
            try:
                await client.put_object(Bucket=bucket, Key=key, Body=content, IfNoneMatch="*")
            except ClientError as error:
                if _client_error_code(error) not in {"PreconditionFailed", "412"}:
                    raise
                first_put_replayed = True
            head = await client.head_object(Bucket=bucket, Key=key)
            response = await client.get_object(Bucket=bucket, Key=key)
            body = response.get("Body")
            if body is None:
                raise ArtifactConfigurationError("AWS proof object body is unavailable")
            async with body:
                received = await body.read()
            await _require_client_error(
                client.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=content,
                    IfNoneMatch="*",
                ),
                {"PreconditionFailed", "412"},
            )
            await _require_client_error(
                client.put_object(Bucket=bucket, Key=key, Body=b"forbidden-overwrite"),
                {"AccessDenied", "403"},
            )
            await _require_client_error(
                client.head_object(Bucket=bucket, Key=missing_key),
                {"404", "NoSuchKey", "NotFound"},
            )
            preserved = await client.get_object(Bucket=bucket, Key=key)
            preserved_body = preserved.get("Body")
            if preserved_body is None:
                raise ArtifactConfigurationError("AWS proof preserved body is unavailable")
            async with preserved_body:
                preserved_bytes = await preserved_body.read()
        if head.get("ContentLength") != len(content) or received != content:
            raise ArtifactConfigurationError("AWS proof object readback differs")
        if preserved_bytes != content:
            raise ArtifactConfigurationError("AWS proof overwrite changed retained bytes")
        return {
            "challenge_sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
            "byte_count": len(content),
            "conditional_put": True,
            "first_put_replayed": first_put_replayed,
            "exact_readback": True,
            "replay_precondition": True,
            "unconditional_overwrite_denied": True,
            "missing_head_404": True,
            "preserved_after_denial": True,
        }

    async def _negative_access(self, group_nonce: UUID) -> dict[str, object]:
        content, key, _ = self._challenge(group_nonce)
        await self._prove_object_denials(key, content)
        return {"known_object_get_denied": True, "put_denied": True, "delete_denied": True}

    async def _readiness(self, group_nonce: UUID) -> dict[str, object]:
        content, key, _ = self._challenge(group_nonce)
        bucket = self._required(self._settings.artifact_s3_bucket)
        region = self._required(self._settings.artifact_s3_region)
        async with self._session.create_client("s3", region_name=region, config=self._config) as s3:
            policy_response = await s3.get_bucket_policy(Bucket=bucket)
            policy_text = policy_response.get("Policy")
            if not isinstance(policy_text, str):
                raise ArtifactConfigurationError("AWS bucket policy response is invalid")
            bucket_policy = _load_policy(policy_text)
            if canonical_json_hash(bucket_policy) != self._required(
                self._settings.artifact_s3_bucket_policy_sha256
            ):
                raise ArtifactConfigurationError("AWS bucket policy digest differs")
            _validate_bucket_policy(bucket_policy, self._settings)
            status = await s3.get_bucket_policy_status(Bucket=bucket)
            if status.get("PolicyStatus", {}).get("IsPublic") is not False:
                raise ArtifactConfigurationError("AWS bucket policy is public")
            public = await s3.get_public_access_block(Bucket=bucket)
            public_config = public.get("PublicAccessBlockConfiguration", {})
            if any(
                public_config.get(name) is not True
                for name in (
                    "BlockPublicAcls",
                    "IgnorePublicAcls",
                    "BlockPublicPolicy",
                    "RestrictPublicBuckets",
                )
            ):
                raise ArtifactConfigurationError("AWS public access block is incomplete")
            ownership = await s3.get_bucket_ownership_controls(Bucket=bucket)
            rules = ownership.get("OwnershipControls", {}).get("Rules", [])
            if rules != [{"ObjectOwnership": "BucketOwnerEnforced"}]:
                raise ArtifactConfigurationError("AWS bucket ownership is invalid")
            versioning = await s3.get_bucket_versioning(Bucket=bucket)
            if versioning.get("Status") != "Enabled":
                raise ArtifactConfigurationError("AWS bucket versioning is not enabled")
            encryption = await s3.get_bucket_encryption(Bucket=bucket)
            encryption_rules = encryption.get("ServerSideEncryptionConfiguration", {}).get(
                "Rules", []
            )
            if not _has_only_sse_s3(encryption_rules):
                raise ArtifactConfigurationError("AWS bucket encryption is not exact SSE-S3")
            acl = await s3.get_bucket_acl(Bucket=bucket)
            owner_id = acl.get("Owner", {}).get("ID")
            grants = acl.get("Grants", [])
            if not isinstance(grants, list):
                raise ArtifactConfigurationError("AWS bucket ACL response is invalid")
            owner_grantee = grants[0].get("Grantee", {}) if len(grants) == 1 else {}
            if (
                not isinstance(owner_id, str)
                or len(grants) != 1
                or grants[0].get("Permission") != "FULL_CONTROL"
                or owner_grantee.get("Type") != "CanonicalUser"
                or owner_grantee.get("ID") != owner_id
                or set(owner_grantee) - {"Type", "ID", "DisplayName"}
            ):
                raise ArtifactConfigurationError("AWS bucket ACL grants non-owner access")
            try:
                lifecycle = await s3.get_bucket_lifecycle_configuration(Bucket=bucket)
            except ClientError as error:
                if _client_error_code(error) != "NoSuchLifecycleConfiguration":
                    raise
                lifecycle = {"Rules": []}
            _validate_lifecycle(
                lifecycle.get("Rules", []), self._settings.artifact_s3_private_prefix
            )
        await self._validate_iam()
        await self._validate_access_analyzer(policy_text)
        await self._prove_object_denials(key, content)
        await self._prove_anonymous_denials(key, content)
        return {
            "bucket_policy_exact": True,
            "bucket_not_public": True,
            "public_access_block": True,
            "owner_enforced": True,
            "versioning": True,
            "sse_s3": True,
            "owner_only_acl": True,
            "lifecycle_safe": True,
            "iam_exact": True,
            "access_analyzer": True,
            "readiness_object_access_denied": True,
            "anonymous_object_access_denied": True,
        }

    async def _validate_iam(self) -> None:
        runtime_role = self._required(self._settings.artifact_s3_runtime_role_arn)
        readiness_role = self._required(self._settings.artifact_s3_readiness_role_arn)
        negative_role = self._required(self._settings.artifact_s3_negative_role_arn)
        role_policies = {
            runtime_role: (
                self._required(self._settings.artifact_s3_runtime_policy_arn),
                self._required(self._settings.artifact_s3_runtime_trust_policy_sha256),
            ),
            readiness_role: (
                self._required(self._settings.artifact_s3_readiness_policy_arn),
                self._required(self._settings.artifact_s3_readiness_trust_policy_sha256),
            ),
            negative_role: (
                None,
                self._required(self._settings.artifact_s3_negative_trust_policy_sha256),
            ),
        }
        workload_roles = frozenset(role_policies)
        trust_subjects: dict[str, frozenset[tuple[str, str]]] = {}
        async with self._session.create_client("iam", config=self._config) as iam:
            for role_arn, (expected_policy, expected_trust_digest) in role_policies.items():
                role_name = role_arn.rsplit("/", 1)[-1]
                role = await iam.get_role(RoleName=role_name)
                role_data = role.get("Role", {})
                if role_data.get("Arn") != role_arn:
                    raise ArtifactConfigurationError("AWS IAM role identity differs")
                trust_policy = _load_policy(role_data.get("AssumeRolePolicyDocument"))
                if canonical_json_hash(trust_policy) != expected_trust_digest:
                    raise ArtifactConfigurationError("AWS IAM role trust policy digest differs")
                trust_subjects[role_arn] = _trust_policy_subjects(
                    trust_policy,
                    workload_roles=workload_roles,
                )
                if role_arn != runtime_role and any(
                    subject_kind == "service" for subject_kind, _subject in trust_subjects[role_arn]
                ):
                    raise ArtifactConfigurationError(
                        "AWS IAM service trust is supported only for the runtime role"
                    )
                inline = await iam.list_role_policies(RoleName=role_name)
                if inline.get("PolicyNames") or inline.get("IsTruncated"):
                    raise ArtifactConfigurationError("AWS IAM role has an inline policy")
                attached = await iam.list_attached_role_policies(RoleName=role_name)
                attached_arns = tuple(
                    sorted(item.get("PolicyArn") for item in attached.get("AttachedPolicies", []))
                )
                expected_policies = () if expected_policy is None else (expected_policy,)
                if attached.get("IsTruncated") or attached_arns != expected_policies:
                    raise ArtifactConfigurationError("AWS IAM role attachments differ")
            subject_sets = tuple(trust_subjects.values())
            if any(
                subject_sets[left] & subject_sets[right]
                for left in range(len(subject_sets))
                for right in range(left + 1, len(subject_sets))
            ):
                raise ArtifactConfigurationError("AWS IAM workload trust subjects are not distinct")
            for policy_arn in (
                self._required(self._settings.artifact_s3_runtime_policy_arn),
                self._required(self._settings.artifact_s3_readiness_policy_arn),
            ):
                policy = await iam.get_policy(PolicyArn=policy_arn)
                metadata = policy.get("Policy", {})
                if metadata.get("Arn") != policy_arn or not isinstance(
                    metadata.get("DefaultVersionId"), str
                ):
                    raise ArtifactConfigurationError("AWS IAM policy identity differs")
                version = await iam.get_policy_version(
                    PolicyArn=policy_arn,
                    VersionId=metadata["DefaultVersionId"],
                )
                document = version.get("PolicyVersion", {}).get("Document")
                parsed = _load_policy(document)
                if policy_arn == self._settings.artifact_s3_runtime_policy_arn:
                    _validate_runtime_policy(parsed, self._settings)
                else:
                    _validate_readiness_policy(parsed, self._settings)

    async def _validate_access_analyzer(self, bucket_policy_text: str) -> None:
        async with self._session.create_client("accessanalyzer", config=self._config) as analyzer:
            validation = await analyzer.validate_policy(
                policyDocument=bucket_policy_text,
                policyType="RESOURCE_POLICY",
            )
            if validation.get("findings"):
                raise ArtifactConfigurationError("AWS bucket policy has analyzer findings")
            public = await analyzer.check_no_public_access(
                policyDocument=bucket_policy_text,
                resourceType="AWS::S3::Bucket",
            )
            if public.get("result") != "PASS":
                raise ArtifactConfigurationError("AWS bucket policy permits public access")
            object_actions = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
            partition = self._required(self._settings.artifact_s3_runtime_role_arn).split(":", 2)[1]
            object_arn = (
                f"arn:{partition}:s3:::{self._settings.artifact_s3_bucket}/"
                f"{self._settings.artifact_s3_private_prefix}/sha256/*"
            )
            checked = await analyzer.check_access_not_granted(
                policyDocument=bucket_policy_text,
                policyType="RESOURCE_POLICY",
                access=[{"actions": object_actions, "resources": [object_arn]}],
            )
            if checked.get("result") != "PASS":
                raise ArtifactConfigurationError("AWS bucket policy grants forbidden access")

    async def _prove_object_denials(self, key: str, content: bytes) -> None:
        bucket = self._required(self._settings.artifact_s3_bucket)
        async with self._session.create_client(
            "s3",
            region_name=self._required(self._settings.artifact_s3_region),
            config=self._config,
        ) as client:
            await _require_client_error(
                client.get_object(Bucket=bucket, Key=key), {"AccessDenied", "403"}
            )
            await _require_client_error(
                client.put_object(Bucket=bucket, Key=key, Body=content, IfNoneMatch="*"),
                {"AccessDenied", "403"},
            )
            await _require_client_error(
                client.delete_object(Bucket=bucket, Key=key), {"AccessDenied", "403"}
            )

    async def _prove_anonymous_denials(self, key: str, content: bytes) -> None:
        unsigned = AioConfig(
            signature_version=UNSIGNED,
            connect_timeout=self._settings.artifact_s3_connect_timeout_seconds,
            read_timeout=self._settings.artifact_s3_read_timeout_seconds,
            retries={"max_attempts": 1},
            proxies={},
            s3={"addressing_style": self._settings.artifact_s3_addressing_style},
        )
        bucket = self._required(self._settings.artifact_s3_bucket)
        async with AioSession().create_client(
            "s3",
            region_name=self._required(self._settings.artifact_s3_region),
            config=unsigned,
        ) as client:
            await _require_client_error(
                client.get_object(Bucket=bucket, Key=key), {"AccessDenied", "403"}
            )
            await _require_client_error(
                client.put_object(Bucket=bucket, Key=key, Body=content),
                {"AccessDenied", "403"},
            )
            await _require_client_error(
                client.delete_object(Bucket=bucket, Key=key), {"AccessDenied", "403"}
            )

    def _challenge(self, group_nonce: UUID) -> tuple[bytes, str, str]:
        if type(group_nonce) is not UUID:
            raise ArtifactConfigurationError("AWS proof challenge nonce is invalid")
        content = b"workstream-aws-artifact-proof-v1:" + group_nonce.bytes
        digest = hashlib.sha256(content).hexdigest()
        missing = hashlib.sha256(content + b":missing").hexdigest()
        prefix = self._settings.artifact_s3_private_prefix
        return (
            content,
            f"{prefix}/sha256/{digest[:2]}/{digest[2:]}",
            f"{prefix}/sha256/{missing[:2]}/{missing[2:]}",
        )

    def _expected_principal(self, probe_type: AwsArtifactProbeType) -> str:
        values = {
            "readiness": self._settings.artifact_s3_readiness_role_arn,
            "runtime_immutability": self._settings.artifact_s3_runtime_role_arn,
            "negative_access": self._settings.artifact_s3_negative_role_arn,
        }
        return self._required(values.get(probe_type))

    @staticmethod
    def _required(value: str | None) -> str:
        if value is None:
            raise ArtifactConfigurationError("AWS proof configuration is incomplete")
        return value

    @staticmethod
    def _failed(
        probe_type: AwsArtifactProbeType,
        expected: str,
        observed: str | None,
        error_code: str,
        evidence: dict[str, object],
    ) -> AwsArtifactProbeObservation:
        return AwsArtifactProbeObservation(
            probe_type=probe_type,
            expected_principal_arn=expected,
            observed_principal_arn=observed,
            passed=False,
            error_code=error_code,
            evidence=evidence,
        )


def _canonical_observed_role_arn(observed: str, expected: str) -> str:
    """Normalize one STS assumed-role ARN only after exact account/name binding."""
    expected_parts = expected.split(":", 5)
    observed_parts = observed.split(":", 5)
    if observed == expected:
        return expected
    if (
        len(expected_parts) != 6
        or len(observed_parts) != 6
        or expected_parts[1] != observed_parts[1]
        or expected_parts[4] != observed_parts[4]
        or observed_parts[2] != "sts"
        or not expected_parts[5].startswith("role/")
        or not observed_parts[5].startswith("assumed-role/")
    ):
        return observed
    expected_name = expected_parts[5].rsplit("/", 1)[-1]
    assumed_parts = observed_parts[5].split("/")
    return expected if len(assumed_parts) == 3 and assumed_parts[1] == expected_name else observed


async def _require_client_error(call: Any, allowed_codes: set[str]) -> None:
    try:
        await call
    except ClientError as error:
        if _client_error_code(error) in allowed_codes:
            return
        raise
    raise ArtifactConfigurationError("AWS proof expected an explicit denial")


def _client_error_code(error: ClientError) -> str:
    return str(error.response.get("Error", {}).get("Code", "unknown"))


def _bounded_error_code(error: BaseException) -> str:
    if isinstance(error, ClientError):
        code = _client_error_code(error)
        return code[:80] if code else "aws_client_error"
    if isinstance(error, ArtifactConfigurationError):
        return "proof_validation_failed"
    if isinstance(error, TimeoutError):
        return "proof_timeout"
    return "proof_transport_failed"


def _load_policy(value: object) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            parsed = json.loads(unquote(value))
        except (json.JSONDecodeError, UnicodeError):
            raise ArtifactConfigurationError("AWS policy document is invalid") from None
    else:
        parsed = value
    if not isinstance(parsed, dict) or parsed.get("Version") != "2012-10-17":
        raise ArtifactConfigurationError("AWS policy document is invalid")
    return parsed


def _statements(policy: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    value = policy.get("Statement")
    rows = value if isinstance(value, list) else [value]
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise ArtifactConfigurationError("AWS policy statements are invalid")
    return tuple(rows)


def _values(value: object) -> frozenset[str]:
    rows = value if isinstance(value, list) else [value]
    if any(not isinstance(row, str) for row in rows):
        raise ArtifactConfigurationError("AWS policy values are invalid")
    return frozenset(rows)


def _trust_policy_subjects(
    policy: dict[str, Any],
    *,
    workload_roles: frozenset[str],
) -> frozenset[tuple[str, str]]:
    """Return one exact OIDC subject or the closed EC2 runtime trust subject."""
    statements = _statements(policy)
    if len(statements) != 1:
        raise ArtifactConfigurationError("AWS IAM trust policy is not closed")
    statement = statements[0]
    principal = statement.get("Principal")
    if not isinstance(principal, dict) or set(principal) not in (
        {"Federated"},
        {"Service"},
    ):
        raise ArtifactConfigurationError("AWS IAM trust principal is not closed")
    if "Service" in principal:
        if (
            set(statement) != {"Effect", "Principal", "Action"}
            or statement.get("Effect") != "Allow"
            or _values(statement.get("Action")) != {"sts:AssumeRole"}
            or principal["Service"] != "ec2.amazonaws.com"
        ):
            raise ArtifactConfigurationError("AWS IAM service trust is not supported")
        return frozenset({("service", "ec2.amazonaws.com")})

    if set(statement) != {"Effect", "Principal", "Action", "Condition"}:
        raise ArtifactConfigurationError("AWS IAM trust statement is not closed")
    if statement.get("Effect") != "Allow" or _values(statement.get("Action")) != {
        "sts:AssumeRoleWithWebIdentity"
    }:
        raise ArtifactConfigurationError("AWS IAM trust action is not supported")
    provider = principal["Federated"]
    if (
        not isinstance(provider, str)
        or provider in workload_roles
        or any(marker in provider for marker in ("*", "?"))
    ):
        raise ArtifactConfigurationError("AWS IAM federated trust provider is not exact")
    provider_parts = provider.split(":", 5)
    workload_scopes = {
        (parts[1], parts[4])
        for role in workload_roles
        if len(parts := role.split(":", 5)) == 6
    }
    if (
        len(provider_parts) != 6
        or provider_parts[0] != "arn"
        or provider_parts[2] != "iam"
        or provider_parts[3]
        or len(provider_parts[4]) != 12
        or not provider_parts[4].isdigit()
        or not provider_parts[5].startswith("oidc-provider/")
        or workload_scopes != {(provider_parts[1], provider_parts[4])}
    ):
        raise ArtifactConfigurationError("AWS IAM federated trust provider is invalid")
    issuer = provider_parts[5].removeprefix("oidc-provider/")
    if not issuer or issuer.startswith("https://") or issuer.endswith("/"):
        raise ArtifactConfigurationError("AWS IAM federated trust issuer is invalid")

    condition = statement.get("Condition")
    if not isinstance(condition, dict) or set(condition) != {"StringEquals"}:
        raise ArtifactConfigurationError("AWS IAM federated trust condition is not closed")
    claims = condition["StringEquals"]
    if not isinstance(claims, dict) or set(claims) != {
        f"{issuer}:aud",
        f"{issuer}:sub",
    }:
        raise ArtifactConfigurationError("AWS IAM federated trust claims are not exact")
    audience = claims[f"{issuer}:aud"]
    subject = claims[f"{issuer}:sub"]
    if audience != "sts.amazonaws.com":
        raise ArtifactConfigurationError("AWS IAM federated trust audience is not exact")
    if (
        not isinstance(subject, str)
        or not subject
        or any(marker in subject for marker in ("*", "?"))
    ):
        raise ArtifactConfigurationError("AWS IAM federated trust subject is not exact")
    return frozenset({(provider, subject)})


def _allowed_pairs(policy: dict[str, Any]) -> frozenset[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for statement in _statements(policy):
        if statement.get("Effect") != "Allow" or "Condition" in statement:
            raise ArtifactConfigurationError("AWS identity policy has a non-exact statement")
        actions = _values(statement.get("Action"))
        resources = _values(statement.get("Resource"))
        pairs.update((action, resource) for action in actions for resource in resources)
    return frozenset(pairs)


def _validate_runtime_policy(policy: dict[str, Any], settings: Settings) -> None:
    partition = settings.artifact_s3_runtime_role_arn.split(":", 2)[1]  # type: ignore[union-attr]
    bucket_arn = f"arn:{partition}:s3:::{settings.artifact_s3_bucket}"
    object_arn = f"{bucket_arn}/{settings.artifact_s3_private_prefix}/sha256/*"
    expected = frozenset(
        {
            ("s3:PutObject", object_arn),
            ("s3:GetObject", object_arn),
            ("s3:ListBucket", bucket_arn),
        }
    )
    if _allowed_pairs(policy) != expected:
        raise ArtifactConfigurationError("AWS runtime policy permissions differ")


def _validate_readiness_policy(policy: dict[str, Any], settings: Settings) -> None:
    partition = settings.artifact_s3_readiness_role_arn.split(":", 2)[1]  # type: ignore[union-attr]
    bucket_arn = f"arn:{partition}:s3:::{settings.artifact_s3_bucket}"
    roles = {
        settings.artifact_s3_runtime_role_arn,
        settings.artifact_s3_readiness_role_arn,
        settings.artifact_s3_negative_role_arn,
    }
    policies = {
        settings.artifact_s3_runtime_policy_arn,
        settings.artifact_s3_readiness_policy_arn,
    }
    expected = {(action, bucket_arn) for action in _BUCKET_ACTIONS}
    expected.update((action, role) for action in _ROLE_INSPECTION_ACTIONS for role in roles)
    expected.update((action, arn) for action in _POLICY_INSPECTION_ACTIONS for arn in policies)
    expected.update((action, "*") for action in _ANALYZER_ACTIONS)
    if None in roles or None in policies or _allowed_pairs(policy) != frozenset(expected):
        raise ArtifactConfigurationError("AWS readiness policy permissions differ")


def _validate_bucket_policy(policy: dict[str, Any], settings: Settings) -> None:
    partition = settings.artifact_s3_runtime_role_arn.split(":", 2)[1]  # type: ignore[union-attr]
    bucket_arn = f"arn:{partition}:s3:::{settings.artifact_s3_bucket}"
    object_arn = f"{bucket_arn}/{settings.artifact_s3_private_prefix}/sha256/*"
    expected = {
        "DenyInsecureTransport": (
            frozenset({"s3:*"}),
            frozenset({bucket_arn, object_arn}),
            {"Bool": {"aws:SecureTransport": "false"}},
        ),
        "DenyNonRuntimeObjectData": (
            frozenset({"s3:*"}),
            frozenset({object_arn}),
            {"ArnNotEquals": {"aws:PrincipalArn": settings.artifact_s3_runtime_role_arn}},
        ),
        "DenyUnconditionalPut": (
            frozenset({"s3:PutObject"}),
            frozenset({object_arn}),
            {"Null": {"s3:if-none-match": "true"}},
        ),
    }
    rows = {row.get("Sid"): row for row in _statements(policy)}
    if set(rows) != set(expected):
        raise ArtifactConfigurationError("AWS bucket policy statement set differs")
    for sid, (actions, resources, condition) in expected.items():
        row = rows[sid]
        if (
            row.get("Effect") != "Deny"
            or row.get("Principal") != "*"
            or _values(row.get("Action")) != actions
            or _values(row.get("Resource")) != resources
            or row.get("Condition") != condition
            or set(row) != {"Sid", "Effect", "Principal", "Action", "Resource", "Condition"}
        ):
            raise ArtifactConfigurationError("AWS bucket policy statement differs")


def _has_only_sse_s3(rules: object) -> bool:
    if not isinstance(rules, list) or len(rules) != 1 or not isinstance(rules[0], dict):
        return False
    default = rules[0].get("ApplyServerSideEncryptionByDefault")
    return (
        default == {"SSEAlgorithm": "AES256"}
        and rules[0].get("BucketKeyEnabled") in {None, False}
        and set(rules[0]) <= {"ApplyServerSideEncryptionByDefault", "BucketKeyEnabled"}
    )


def _validate_lifecycle(rules: object, private_prefix: str) -> None:
    if not isinstance(rules, list):
        raise ArtifactConfigurationError("AWS lifecycle configuration is invalid")
    completed_prefix = f"{private_prefix}/sha256/"
    for rule in rules:
        if not isinstance(rule, dict) or rule.get("Status") not in {"Enabled", "Disabled"}:
            raise ArtifactConfigurationError("AWS lifecycle rule is invalid")
        if rule.get("Status") != "Enabled":
            continue
        filter_value = rule.get("Filter", {})
        prefix = rule.get("Prefix")
        if isinstance(filter_value, dict):
            prefix = filter_value.get("Prefix", filter_value.get("And", {}).get("Prefix", prefix))
        intersects = not isinstance(prefix, str) or (
            completed_prefix.startswith(prefix) or prefix.startswith(completed_prefix)
        )
        if intersects and ("Expiration" in rule or "NoncurrentVersionExpiration" in rule):
            raise ArtifactConfigurationError("AWS lifecycle can expire completed artifacts")
