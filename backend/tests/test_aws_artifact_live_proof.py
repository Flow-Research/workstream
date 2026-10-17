"""Offline contract tests for the native AWS artifact proof transport."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import UUID

from botocore.exceptions import ClientError
from pydantic import ValidationError
import pytest

from app.adapters.artifacts.aws_live_proof import (
    AwsArtifactLiveProof,
    _trust_policy_subjects,
    _validate_bucket_policy,
    _validate_lifecycle,
)
from app.core.config import Settings
from app.core.hashing import canonical_json_hash
from app.interfaces.artifacts import ArtifactConfigurationError
from tests.artifact_store_helpers import artifact_admission_limit_settings


_ACCOUNT = "123456789012"
_BUCKET = "workstream-artifacts-prod"
_PREFIX = "workstream/artifacts"
_RUNTIME_ROLE = f"arn:aws:iam::{_ACCOUNT}:role/workstream-runtime"
_READINESS_ROLE = f"arn:aws:iam::{_ACCOUNT}:role/workstream-readiness"
_NEGATIVE_ROLE = f"arn:aws:iam::{_ACCOUNT}:role/workstream-negative"
_RUNTIME_POLICY = f"arn:aws:iam::{_ACCOUNT}:policy/workstream-runtime"
_READINESS_POLICY = f"arn:aws:iam::{_ACCOUNT}:policy/workstream-readiness"
_OIDC_PROVIDER = f"arn:aws:iam::{_ACCOUNT}:oidc-provider/identity.example.test"
_GROUP_NONCE = UUID("0199f68b-5dc2-7000-8000-000000000001")


def _trust_policy(subject: str, *, audience: str = "sts.amazonaws.com") -> dict[str, Any]:
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Federated": _OIDC_PROVIDER},
                "Action": "sts:AssumeRoleWithWebIdentity",
                "Condition": {
                    "StringEquals": {
                        "identity.example.test:aud": audience,
                        "identity.example.test:sub": subject,
                    }
                },
            }
        ],
    }


def _ec2_runtime_trust_policy() -> dict[str, Any]:
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "ec2.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }


def _trust_policies() -> dict[str, dict[str, Any]]:
    return {
        _RUNTIME_ROLE: _trust_policy("system:serviceaccount:workstream:runtime"),
        _READINESS_ROLE: _trust_policy("system:serviceaccount:workstream:readiness"),
        _NEGATIVE_ROLE: _trust_policy("system:serviceaccount:workstream:negative"),
    }


def _runtime_identity_policy() -> dict[str, Any]:
    bucket_arn = f"arn:aws:s3:::{_BUCKET}"
    object_arn = f"{bucket_arn}/{_PREFIX}/sha256/*"
    return {
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Action": "s3:PutObject", "Resource": object_arn},
            {"Effect": "Allow", "Action": "s3:GetObject", "Resource": object_arn},
            {"Effect": "Allow", "Action": "s3:ListBucket", "Resource": bucket_arn},
        ],
    }


def _readiness_identity_policy() -> dict[str, Any]:
    bucket_arn = f"arn:aws:s3:::{_BUCKET}"
    pairs = [
        *(
            (action, bucket_arn)
            for action in (
                "s3:GetBucketPolicy",
                "s3:GetBucketPolicyStatus",
                "s3:GetBucketAcl",
                "s3:GetBucketPublicAccessBlock",
                "s3:GetBucketOwnershipControls",
                "s3:GetBucketVersioning",
                "s3:GetLifecycleConfiguration",
                "s3:GetEncryptionConfiguration",
            )
        ),
        *(
            (action, role)
            for action in (
                "iam:GetRole",
                "iam:ListRolePolicies",
                "iam:ListAttachedRolePolicies",
            )
            for role in (_RUNTIME_ROLE, _READINESS_ROLE, _NEGATIVE_ROLE)
        ),
        *(
            (action, policy)
            for action in ("iam:GetPolicy", "iam:GetPolicyVersion")
            for policy in (_RUNTIME_POLICY, _READINESS_POLICY)
        ),
        *(
            (action, "*")
            for action in (
                "access-analyzer:ValidatePolicy",
                "access-analyzer:CheckAccessNotGranted",
                "access-analyzer:CheckNoPublicAccess",
            )
        ),
    ]
    return {
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Action": action, "Resource": resource}
            for action, resource in pairs
        ],
    }


def _bucket_policy() -> dict[str, Any]:
    bucket_arn = f"arn:aws:s3:::{_BUCKET}"
    object_arn = f"{bucket_arn}/{_PREFIX}/sha256/*"
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "DenyInsecureTransport",
                "Effect": "Deny",
                "Principal": "*",
                "Action": "s3:*",
                "Resource": [bucket_arn, object_arn],
                "Condition": {"Bool": {"aws:SecureTransport": "false"}},
            },
            {
                "Sid": "DenyNonRuntimeObjectData",
                "Effect": "Deny",
                "Principal": "*",
                "Action": "s3:*",
                "Resource": object_arn,
                "Condition": {"ArnNotEquals": {"aws:PrincipalArn": _RUNTIME_ROLE}},
            },
            {
                "Sid": "DenyUnconditionalPut",
                "Effect": "Deny",
                "Principal": "*",
                "Action": "s3:PutObject",
                "Resource": object_arn,
                "Condition": {"Null": {"s3:if-none-match": "true"}},
            },
        ],
    }


def _settings_values(
    tmp_path: Path,
    *,
    trust_policies: dict[str, dict[str, Any]] | None = None,
    bucket_policy: dict[str, Any] | None = None,
) -> dict[str, object]:
    trusts = trust_policies or _trust_policies()
    policy = bucket_policy or _bucket_policy()
    return {
        **artifact_admission_limit_settings(),
        "environment": "production",
        "artifact_store_backend": "s3_compatible",
        "artifact_scratch_root": tmp_path / "scratch",
        "artifact_s3_provider_profile": "aws_s3",
        "artifact_s3_region": "us-east-1",
        "artifact_s3_bucket": _BUCKET,
        "artifact_s3_private_prefix": _PREFIX,
        "artifact_s3_credential_mode": "aws_workload_identity",
        "artifact_s3_aws_workload_identity_method": "container-role",
        "release_id": "sha256:" + "1" * 64,
        "artifact_s3_runtime_role_arn": _RUNTIME_ROLE,
        "artifact_s3_runtime_trust_policy_sha256": canonical_json_hash(trusts[_RUNTIME_ROLE]),
        "artifact_s3_runtime_policy_arn": _RUNTIME_POLICY,
        "artifact_s3_readiness_role_arn": _READINESS_ROLE,
        "artifact_s3_readiness_trust_policy_sha256": canonical_json_hash(trusts[_READINESS_ROLE]),
        "artifact_s3_readiness_policy_arn": _READINESS_POLICY,
        "artifact_s3_negative_role_arn": _NEGATIVE_ROLE,
        "artifact_s3_negative_trust_policy_sha256": canonical_json_hash(trusts[_NEGATIVE_ROLE]),
        "artifact_s3_bootstrap_principal_arn": (
            f"arn:aws:iam::{_ACCOUNT}:role/workstream-bootstrap"
        ),
        "artifact_s3_bucket_policy_sha256": canonical_json_hash(policy),
        "artifact_s3_operation_total_timeout_seconds": 300,
        "artifact_complete_read_deadline_seconds": 300,
        "artifact_terminal_persistence_margin_seconds": 120,
    }


def _settings(
    tmp_path: Path,
    *,
    trust_policies: dict[str, dict[str, Any]] | None = None,
    bucket_policy: dict[str, Any] | None = None,
) -> Settings:
    return Settings(
        **_settings_values(
            tmp_path,
            trust_policies=trust_policies,
            bucket_policy=bucket_policy,
        )
    )


class _ClientContext:
    def __init__(self, client: object) -> None:
        self._client = client

    async def __aenter__(self) -> object:
        return self._client

    async def __aexit__(self, *_args: object) -> None:
        return None


class _Session:
    def __init__(self, **clients: object) -> None:
        self.clients = clients
        self.requests: list[tuple[str, dict[str, object]]] = []

    def create_client(self, service: str, **kwargs: object) -> _ClientContext:
        self.requests.append((service, kwargs))
        return _ClientContext(self.clients[service])


class _IamClient:
    def __init__(
        self,
        trusts: dict[str, dict[str, Any]],
        *,
        identity_policies: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.trusts = trusts
        self.identity_policies = identity_policies or {
            _RUNTIME_POLICY: _runtime_identity_policy(),
            _READINESS_POLICY: _readiness_identity_policy(),
        }
        self.calls: list[tuple[str, str]] = []

    async def get_role(self, *, RoleName: str) -> dict[str, object]:
        self.calls.append(("get_role", RoleName))
        role_arn = next(arn for arn in self.trusts if arn.rsplit("/", 1)[-1] == RoleName)
        return {
            "Role": {
                "Arn": role_arn,
                "AssumeRolePolicyDocument": self.trusts[role_arn],
            }
        }

    async def list_role_policies(self, *, RoleName: str) -> dict[str, object]:
        self.calls.append(("list_role_policies", RoleName))
        return {"PolicyNames": [], "IsTruncated": False}

    async def list_attached_role_policies(self, *, RoleName: str) -> dict[str, object]:
        self.calls.append(("list_attached_role_policies", RoleName))
        policies = {
            "workstream-runtime": [_RUNTIME_POLICY],
            "workstream-readiness": [_READINESS_POLICY],
            "workstream-negative": [],
        }[RoleName]
        return {
            "AttachedPolicies": [
                {"PolicyName": policy.rsplit("/", 1)[-1], "PolicyArn": policy}
                for policy in policies
            ],
            "IsTruncated": False,
        }

    async def get_policy(self, *, PolicyArn: str) -> dict[str, object]:
        self.calls.append(("get_policy", PolicyArn))
        return {"Policy": {"Arn": PolicyArn, "DefaultVersionId": "v1"}}

    async def get_policy_version(self, *, PolicyArn: str, VersionId: str) -> dict[str, object]:
        assert VersionId == "v1"
        self.calls.append(("get_policy_version", PolicyArn))
        document = self.identity_policies[PolicyArn]
        return {"PolicyVersion": {"Document": quote(json.dumps(document))}}


def _client_error(code: str, operation: str) -> ClientError:
    return ClientError(
        {"Error": {"Code": code, "Message": "bounded test response"}},
        operation,
    )


class _Body:
    def __init__(self, content: bytes) -> None:
        self.content = content

    async def __aenter__(self) -> _Body:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def read(self) -> bytes:
        return self.content


class _RuntimeS3Client:
    def __init__(
        self,
        *,
        replay_code: str = "PreconditionFailed",
        overwrite_code: str = "AccessDenied",
        missing_code: str = "404",
        preexisting_content: bytes | None = None,
    ) -> None:
        self.replay_code = replay_code
        self.overwrite_code = overwrite_code
        self.missing_code = missing_code
        self.content = preexisting_content
        self.key: str | None = None
        self.calls: list[tuple[str, str, str | None]] = []

    async def put_object(self, **kwargs: object) -> dict[str, object]:
        key = str(kwargs["Key"])
        condition = kwargs.get("IfNoneMatch")
        self.calls.append(("put", key, str(condition) if condition is not None else None))
        if condition == "*" and self.content is None:
            self.content = bytes(kwargs["Body"])
            self.key = key
            return {"ETag": '"test"'}
        if condition == "*":
            if self.key is None:
                self.key = key
            raise _client_error(self.replay_code, "PutObject")
        if self.overwrite_code == "success":
            self.content = bytes(kwargs["Body"])
            return {"ETag": '"changed"'}
        raise _client_error(self.overwrite_code, "PutObject")

    async def head_object(self, **kwargs: object) -> dict[str, object]:
        key = str(kwargs["Key"])
        self.calls.append(("head", key, None))
        if self.content is None or key != self.key:
            raise _client_error(self.missing_code, "HeadObject")
        return {"ContentLength": len(self.content)}

    async def get_object(self, **kwargs: object) -> dict[str, object]:
        key = str(kwargs["Key"])
        self.calls.append(("get", key, None))
        assert self.content is not None
        return {"Body": _Body(self.content)}


class _DenyingS3Client:
    def __init__(self, codes: dict[str, str]) -> None:
        self.codes = codes
        self.calls: list[str] = []

    async def get_object(self, **_kwargs: object) -> None:
        self.calls.append("get")
        raise _client_error(self.codes["get"], "GetObject")

    async def put_object(self, **_kwargs: object) -> None:
        self.calls.append("put")
        raise _client_error(self.codes["put"], "PutObject")

    async def delete_object(self, **_kwargs: object) -> None:
        self.calls.append("delete")
        raise _client_error(self.codes["delete"], "DeleteObject")


class _ReadinessS3Client:
    def __init__(self, policy: dict[str, Any], lifecycle: list[dict[str, Any]]) -> None:
        self.policy = policy
        self.lifecycle = lifecycle

    async def get_bucket_policy(self, **_kwargs: object) -> dict[str, object]:
        return {"Policy": json.dumps(self.policy)}

    async def get_bucket_policy_status(self, **_kwargs: object) -> dict[str, object]:
        return {"PolicyStatus": {"IsPublic": False}}

    async def get_public_access_block(self, **_kwargs: object) -> dict[str, object]:
        return {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True,
            }
        }

    async def get_bucket_ownership_controls(self, **_kwargs: object) -> dict[str, object]:
        return {"OwnershipControls": {"Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]}}

    async def get_bucket_versioning(self, **_kwargs: object) -> dict[str, object]:
        return {"Status": "Enabled"}

    async def get_bucket_encryption(self, **_kwargs: object) -> dict[str, object]:
        return {
            "ServerSideEncryptionConfiguration": {
                "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
            }
        }

    async def get_bucket_acl(self, **_kwargs: object) -> dict[str, object]:
        return {
            "Owner": {"ID": "canonical-owner"},
            "Grants": [
                {
                    "Permission": "FULL_CONTROL",
                    "Grantee": {"Type": "CanonicalUser", "ID": "canonical-owner"},
                }
            ],
        }

    async def get_bucket_lifecycle_configuration(self, **_kwargs: object) -> dict[str, object]:
        return {"Rules": self.lifecycle}


def test_native_aws_trust_digests_load_from_exact_nonsecret_environment_names(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    values = _settings_values(tmp_path)
    expected = {}
    env_names = {
        "artifact_s3_runtime_trust_policy_sha256": (
            "WORKSTREAM_ARTIFACT_S3_RUNTIME_TRUST_POLICY_SHA256"
        ),
        "artifact_s3_readiness_trust_policy_sha256": (
            "WORKSTREAM_ARTIFACT_S3_READINESS_TRUST_POLICY_SHA256"
        ),
        "artifact_s3_negative_trust_policy_sha256": (
            "WORKSTREAM_ARTIFACT_S3_NEGATIVE_TRUST_POLICY_SHA256"
        ),
    }
    for field, env_name in env_names.items():
        expected[field] = values.pop(field)
        monkeypatch.setenv(env_name, str(expected[field]))
    for secret_name in (
        "WORKSTREAM_ARTIFACT_S3_ACCESS_KEY_ID",
        "WORKSTREAM_ARTIFACT_S3_SECRET_ACCESS_KEY",
        "WORKSTREAM_ARTIFACT_S3_SESSION_TOKEN",
    ):
        monkeypatch.delenv(secret_name, raising=False)

    settings = Settings(_env_file=None, **values)

    assert {field: getattr(settings, field) for field in env_names} == expected


@pytest.mark.parametrize(
    "digests",
    [
        ("sha256:" + "a" * 64, "sha256:" + "b" * 64, "not-a-digest"),
        ("sha256:" + "a" * 64,) * 3,
    ],
    ids=["non-canonical", "not-distinct"],
)
def test_native_aws_trust_digest_settings_are_canonical_and_distinct(
    tmp_path: Path,
    digests: tuple[str, str, str],
) -> None:
    values = _settings_values(tmp_path)
    for field, digest in zip(
        (
            "artifact_s3_runtime_trust_policy_sha256",
            "artifact_s3_readiness_trust_policy_sha256",
            "artifact_s3_negative_trust_policy_sha256",
        ),
        digests,
        strict=True,
    ):
        values[field] = digest

    with pytest.raises(ValidationError, match="trust polic"):
        Settings(**values)


@pytest.mark.asyncio
async def test_validate_iam_accepts_only_exact_roles_trusts_attachments_and_policies(
    tmp_path: Path,
) -> None:
    trusts = _trust_policies()
    iam = _IamClient(trusts)
    proof = AwsArtifactLiveProof(_settings(tmp_path, trust_policies=trusts), _Session(iam=iam))

    await proof._validate_iam()

    assert [call for call in iam.calls if call[0] == "get_role"] == [
        ("get_role", "workstream-runtime"),
        ("get_role", "workstream-readiness"),
        ("get_role", "workstream-negative"),
    ]
    assert [call for call in iam.calls if call[0] == "get_policy_version"] == [
        ("get_policy_version", _RUNTIME_POLICY),
        ("get_policy_version", _READINESS_POLICY),
    ]


@pytest.mark.asyncio
async def test_validate_iam_accepts_closed_ec2_trust_only_for_runtime_role(
    tmp_path: Path,
) -> None:
    trusts = _trust_policies()
    trusts[_RUNTIME_ROLE] = _ec2_runtime_trust_policy()
    proof = AwsArtifactLiveProof(
        _settings(tmp_path, trust_policies=trusts),
        _Session(iam=_IamClient(trusts)),
    )

    await proof._validate_iam()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda trusts: trusts[_READINESS_ROLE]["Statement"][0].__setitem__(
                "Principal",
                {"Federated": _OIDC_PROVIDER, "AWS": f"arn:aws:iam::{_ACCOUNT}:root"},
            ),
            "principal is not closed",
        ),
        (
            lambda trusts: trusts.__setitem__(
                _NEGATIVE_ROLE,
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"AWS": _RUNTIME_ROLE},
                            "Action": "sts:AssumeRole",
                        }
                    ],
                },
            ),
            "principal is not closed",
        ),
        (
            lambda trusts: trusts.__setitem__(_READINESS_ROLE, _ec2_runtime_trust_policy()),
            "supported only for the runtime role",
        ),
    ],
    ids=["unexpected-principal-shape", "cross-assume", "service-readiness-role"],
)
async def test_validate_iam_rejects_unsafe_trust_even_when_each_digest_matches(
    tmp_path: Path,
    mutate: Any,
    message: str,
) -> None:
    trusts = _trust_policies()
    mutate(trusts)
    proof = AwsArtifactLiveProof(
        _settings(tmp_path, trust_policies=trusts),
        _Session(iam=_IamClient(trusts)),
    )

    with pytest.raises(ArtifactConfigurationError, match=message):
        await proof._validate_iam()


@pytest.mark.asyncio
async def test_validate_iam_rejects_get_role_trust_document_digest_drift(
    tmp_path: Path,
) -> None:
    configured = _trust_policies()
    observed = deepcopy(configured)
    observed[_RUNTIME_ROLE] = _trust_policy("unexpected-runtime-subject")
    proof = AwsArtifactLiveProof(
        _settings(tmp_path, trust_policies=configured),
        _Session(iam=_IamClient(observed)),
    )

    with pytest.raises(ArtifactConfigurationError, match="trust policy digest differs"):
        await proof._validate_iam()


@pytest.mark.asyncio
async def test_validate_iam_rejects_one_extra_managed_policy_permission(
    tmp_path: Path,
) -> None:
    trusts = _trust_policies()
    runtime_policy = _runtime_identity_policy()
    runtime_policy["Statement"].append(
        {
            "Effect": "Allow",
            "Action": "s3:DeleteObject",
            "Resource": f"arn:aws:s3:::{_BUCKET}/{_PREFIX}/sha256/*",
        }
    )
    iam = _IamClient(
        trusts,
        identity_policies={
            _RUNTIME_POLICY: runtime_policy,
            _READINESS_POLICY: _readiness_identity_policy(),
        },
    )
    proof = AwsArtifactLiveProof(
        _settings(tmp_path, trust_policies=trusts),
        _Session(iam=iam),
    )

    with pytest.raises(ArtifactConfigurationError, match="runtime policy permissions differ"):
        await proof._validate_iam()


def test_trust_policy_subjects_distinguishes_role_arns_from_workload_subjects() -> None:
    roles = frozenset({_RUNTIME_ROLE, _READINESS_ROLE, _NEGATIVE_ROLE})
    assert _trust_policy_subjects(
        _trust_policy("system:serviceaccount:workstream:runtime"),
        workload_roles=roles,
    ) == frozenset(
        {
            (
                _OIDC_PROVIDER,
                "system:serviceaccount:workstream:runtime",
            )
        }
    )


def test_trust_policy_subjects_accepts_only_the_closed_ec2_runtime_shape() -> None:
    roles = frozenset({_RUNTIME_ROLE, _READINESS_ROLE, _NEGATIVE_ROLE})
    assert _trust_policy_subjects(
        _ec2_runtime_trust_policy(),
        workload_roles=roles,
    ) == frozenset({("service", "ec2.amazonaws.com")})

    unsafe = _ec2_runtime_trust_policy()
    unsafe["Statement"][0]["Condition"] = {"StringEquals": {"aws:SourceAccount": _ACCOUNT}}
    with pytest.raises(ArtifactConfigurationError, match="service trust is not supported"):
        _trust_policy_subjects(unsafe, workload_roles=roles)


def test_trust_policy_subjects_rejects_wildcard_oidc_subjects() -> None:
    roles = frozenset({_RUNTIME_ROLE, _READINESS_ROLE, _NEGATIVE_ROLE})

    with pytest.raises(ArtifactConfigurationError, match="subject is not exact"):
        _trust_policy_subjects(
            _trust_policy("system:serviceaccount:workstream:*"),
            workload_roles=roles,
        )


def test_trust_policy_subjects_rejects_foreign_oidc_provider_account() -> None:
    policy = _trust_policy("system:serviceaccount:workstream:runtime")
    policy["Statement"][0]["Principal"] = {
        "Federated": _OIDC_PROVIDER.replace(_ACCOUNT, "999999999999")
    }

    with pytest.raises(ArtifactConfigurationError, match="provider is invalid"):
        _trust_policy_subjects(
            policy,
            workload_roles=frozenset({_RUNTIME_ROLE, _READINESS_ROLE, _NEGATIVE_ROLE}),
        )


@pytest.mark.parametrize(
    ("condition", "message"),
    [
        (
            {
                "StringNotEquals": {
                    "identity.example.test:aud": "sts.amazonaws.com",
                    "identity.example.test:sub": "system:serviceaccount:workstream:runtime",
                }
            },
            "condition is not closed",
        ),
        (
            {
                "StringEquals": {
                    "identity.example.test:sub": "system:serviceaccount:workstream:runtime",
                }
            },
            "claims are not exact",
        ),
        (
            {
                "StringEquals": {
                    "identity.example.test:aud": "foreign-audience",
                    "identity.example.test:sub": "system:serviceaccount:workstream:runtime",
                }
            },
            "audience is not exact",
        ),
        (
            {
                "StringEquals": {
                    "foreign.example.test:aud": "sts.amazonaws.com",
                    "foreign.example.test:sub": "system:serviceaccount:workstream:runtime",
                }
            },
            "claims are not exact",
        ),
    ],
    ids=["negative-operator", "missing-audience", "foreign-audience", "foreign-issuer"],
)
def test_trust_policy_subjects_rejects_non_exact_oidc_conditions(
    condition: dict[str, object],
    message: str,
) -> None:
    policy = _trust_policy("system:serviceaccount:workstream:runtime")
    policy["Statement"][0]["Condition"] = condition

    with pytest.raises(ArtifactConfigurationError, match=message):
        _trust_policy_subjects(
            policy,
            workload_roles=frozenset({_RUNTIME_ROLE, _READINESS_ROLE, _NEGATIVE_ROLE}),
        )


@pytest.mark.parametrize(
    "principal",
    [
        "*",
        {"AWS": f"arn:aws:iam::{_ACCOUNT}:role/deployment-runner"},
    ],
    ids=["wildcard", "role-chaining"],
)
def test_trust_policy_subjects_rejects_unsupported_principals(principal: object) -> None:
    policy = _trust_policy("system:serviceaccount:workstream:runtime")
    policy["Statement"][0]["Principal"] = principal

    with pytest.raises(ArtifactConfigurationError, match="principal is not closed"):
        _trust_policy_subjects(
            policy,
            workload_roles=frozenset({_RUNTIME_ROLE, _READINESS_ROLE, _NEGATIVE_ROLE}),
        )


def test_bucket_policy_is_an_exact_closed_statement_set(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _validate_bucket_policy(_bucket_policy(), settings)

    extra = deepcopy(_bucket_policy())
    extra["Statement"].append(
        {
            "Sid": "UnexpectedAllow",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": "*",
        }
    )
    widened = deepcopy(_bucket_policy())
    widened["Statement"][2]["Action"] = ["s3:PutObject", "s3:DeleteObject"]
    for unsafe in (extra, widened):
        with pytest.raises(ArtifactConfigurationError, match="bucket policy statement"):
            _validate_bucket_policy(unsafe, settings)


@pytest.mark.parametrize(
    "prefix",
    [None, "workstream/", f"{_PREFIX}/sha256/", f"{_PREFIX}/sha256/ab/"],
    ids=["all-objects", "parent", "exact", "child"],
)
def test_lifecycle_rejects_enabled_expiration_intersecting_completed_artifacts(
    prefix: str | None,
) -> None:
    rule: dict[str, object] = {
        "ID": "unsafe-expiration",
        "Status": "Enabled",
        "Expiration": {"Days": 30},
    }
    if prefix is not None:
        rule["Filter"] = {"Prefix": prefix}

    with pytest.raises(ArtifactConfigurationError, match="expire completed artifacts"):
        _validate_lifecycle([rule], _PREFIX)


def test_lifecycle_allows_disabled_or_disjoint_expiration() -> None:
    _validate_lifecycle(
        [
            {
                "ID": "disabled-completed-expiration",
                "Status": "Disabled",
                "Filter": {"Prefix": f"{_PREFIX}/sha256/"},
                "Expiration": {"Days": 1},
            },
            {
                "ID": "unrelated-temporary-expiration",
                "Status": "Enabled",
                "Filter": {"Prefix": "temporary/"},
                "NoncurrentVersionExpiration": {"NoncurrentDays": 1},
            },
        ],
        _PREFIX,
    )


@pytest.mark.asyncio
async def test_readiness_uses_bounded_bucket_responses_and_runs_every_denial_guard(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bucket_policy = _bucket_policy()
    client = _ReadinessS3Client(bucket_policy, lifecycle=[])
    proof = AwsArtifactLiveProof(
        _settings(tmp_path, bucket_policy=bucket_policy),
        _Session(s3=client),
    )
    events: list[str] = []

    async def mark(name: str, *_args: object) -> None:
        events.append(name)

    monkeypatch.setattr(proof, "_validate_iam", lambda: mark("iam"))
    monkeypatch.setattr(proof, "_validate_access_analyzer", lambda *_: mark("analyzer"))
    monkeypatch.setattr(proof, "_prove_object_denials", lambda *_: mark("role-denials"))
    monkeypatch.setattr(proof, "_prove_anonymous_denials", lambda *_: mark("anonymous-denials"))

    evidence = await proof._readiness(_GROUP_NONCE)

    assert events == ["iam", "analyzer", "role-denials", "anonymous-denials"]
    assert evidence == {
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


@pytest.mark.asyncio
async def test_readiness_rejects_completed_artifact_lifecycle_before_iam(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bucket_policy = _bucket_policy()
    client = _ReadinessS3Client(
        bucket_policy,
        lifecycle=[
            {
                "Status": "Enabled",
                "Filter": {"Prefix": f"{_PREFIX}/sha256/"},
                "Expiration": {"Days": 30},
            }
        ],
    )
    proof = AwsArtifactLiveProof(
        _settings(tmp_path, bucket_policy=bucket_policy),
        _Session(s3=client),
    )

    async def forbidden() -> None:
        raise AssertionError("IAM was queried after unsafe lifecycle")

    monkeypatch.setattr(proof, "_validate_iam", forbidden)
    with pytest.raises(ArtifactConfigurationError, match="expire completed artifacts"):
        await proof._readiness(_GROUP_NONCE)


@pytest.mark.asyncio
async def test_runtime_immutability_proves_exact_bytes_replay_and_preservation(
    tmp_path: Path,
) -> None:
    client = _RuntimeS3Client()
    proof = AwsArtifactLiveProof(_settings(tmp_path), _Session(s3=client))

    evidence = await proof._runtime_immutability(_GROUP_NONCE)

    assert evidence["exact_readback"] is True
    assert evidence["replay_precondition"] is True
    assert evidence["unconditional_overwrite_denied"] is True
    assert evidence["missing_head_404"] is True
    assert evidence["preserved_after_denial"] is True
    assert evidence["first_put_replayed"] is False
    assert client.content == b"workstream-aws-artifact-proof-v1:" + _GROUP_NONCE.bytes


@pytest.mark.asyncio
async def test_runtime_immutability_accepts_an_exact_first_put_replay(tmp_path: Path) -> None:
    content = b"workstream-aws-artifact-proof-v1:" + _GROUP_NONCE.bytes
    client = _RuntimeS3Client(preexisting_content=content)
    proof = AwsArtifactLiveProof(_settings(tmp_path), _Session(s3=client))

    evidence = await proof._runtime_immutability(_GROUP_NONCE)

    assert evidence["first_put_replayed"] is True
    assert evidence["exact_readback"] is True
    assert evidence["preserved_after_denial"] is True
    assert client.content == content


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"replay_code": "AccessDenied"}, "AccessDenied"),
        ({"overwrite_code": "success"}, "expected an explicit denial"),
        ({"missing_code": "AccessDenied"}, "AccessDenied"),
    ],
    ids=["wrong-replay-code", "overwrite-succeeds", "missing-is-access-denied"],
)
async def test_runtime_immutability_rejects_unexpected_provider_outcomes(
    tmp_path: Path,
    changes: dict[str, str],
    match: str,
) -> None:
    proof = AwsArtifactLiveProof(
        _settings(tmp_path),
        _Session(s3=_RuntimeS3Client(**changes)),
    )

    with pytest.raises((ArtifactConfigurationError, ClientError), match=match):
        await proof._runtime_immutability(_GROUP_NONCE)


@pytest.mark.asyncio
async def test_object_denial_proof_requires_all_three_explicit_access_denials(
    tmp_path: Path,
) -> None:
    client = _DenyingS3Client(
        {
            "get": "AccessDenied",
            "put": "403",
            "delete": "AccessDenied",
        }
    )
    proof = AwsArtifactLiveProof(_settings(tmp_path), _Session(s3=client))

    await proof._prove_object_denials("known-key", b"challenge")

    assert client.calls == ["get", "put", "delete"]


@pytest.mark.asyncio
async def test_object_denial_proof_stops_on_an_unexpected_error_code(tmp_path: Path) -> None:
    client = _DenyingS3Client(
        {
            "get": "AccessDenied",
            "put": "SlowDown",
            "delete": "AccessDenied",
        }
    )
    proof = AwsArtifactLiveProof(_settings(tmp_path), _Session(s3=client))

    with pytest.raises(ClientError, match="SlowDown"):
        await proof._prove_object_denials("known-key", b"challenge")
    assert client.calls == ["get", "put"]
