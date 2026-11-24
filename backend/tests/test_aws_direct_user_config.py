"""Security boundaries of the generated dedicated S3 identity policies."""
import pytest
from scripts.aws_direct_user_config import generate_policies

RUNTIME = "arn:aws:iam::123456789012:user/workstream-storage"
CLEANUP = "arn:aws:iam::123456789012:user/workstream-source-cleanup"
BUCKET = "arn:aws:s3:::example-artifacts"
ARTIFACTS = BUCKET + "/workstream/sha256/*"
SOURCES = BUCKET + "/workstream/submission-source/v1/*/bundle.zip"


def _arguments():
    return dict(bucket="example-artifacts", private_prefix="workstream",
                user_arn=RUNTIME, cleanup_user_arn=CLEANUP)


def test_runtime_cannot_administer_delete_or_abort_sources():
    policies = generate_policies(**_arguments())
    statements = policies["user_policy"]["Statement"]
    assert statements[0] == {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject"], "Resource": ARTIFACTS}
    assert statements[1] == {"Effect": "Allow", "Action": ["s3:GetObject", "s3:GetObjectVersion", "s3:PutObject",
        "s3:ListMultipartUploadParts"], "Resource": SOURCES}
    denials = {row["Sid"]: row for row in policies["bucket_policy"]["Statement"]}
    assert all(row["Effect"] == "Deny" and row["Principal"] == "*" for row in denials.values())
    assert denials["DenyRuntimeDestruction"]["Action"] == ["s3:DeleteObject", "s3:DeleteObjectVersion", "s3:AbortMultipartUpload"]
    assert denials["DenyRuntimeDestruction"]["Resource"] == BUCKET + "/*"
    assert denials["DenyRuntimeDestruction"]["Condition"] == {"ArnNotEquals": {"aws:PrincipalArn": CLEANUP}}
    assert denials["DenyForeignObjectAccess"]["Condition"] == {"ArnNotEquals": {"aws:PrincipalArn": [RUNTIME, CLEANUP]}}
    assert denials["DenyOutsideArtifactNamespace"]["NotResource"] == [BUCKET, ARTIFACTS, SOURCES]


def test_cleanup_cannot_write_or_delete_retained_artifacts_or_create_delete_markers():
    policies = generate_policies(**_arguments())
    statements = policies["cleanup_policy"]["Statement"]
    assert statements[0] == {"Effect": "Allow", "Action": ["s3:GetObject", "s3:GetObjectVersion", "s3:DeleteObjectVersion",
        "s3:AbortMultipartUpload", "s3:ListMultipartUploadParts"], "Resource": SOURCES}
    denials = {row["Sid"]: row for row in policies["bucket_policy"]["Statement"]}
    assert denials["DenyCleanupOutsideSource"]["NotResource"] == [BUCKET, SOURCES]
    assert denials["DenyCleanupOutsideSource"]["Condition"] == {"ArnEquals": {"aws:PrincipalArn": CLEANUP}}
    assert denials["DenyCleanupWrites"]["Action"] == "s3:PutObject"
    assert denials["DenyCleanupWrites"]["Resource"] == BUCKET + "/*"
    assert denials["DenyCleanupWrites"]["Condition"] == {"ArnEquals": {"aws:PrincipalArn": CLEANUP}}
    assert denials["DenyUnversionedDeletion"]["Action"] == "s3:DeleteObject"
    assert denials["DenyUnversionedDeletion"]["Resource"] == BUCKET + "/*"
    assert denials["DenyArtifactDeletion"]["Resource"] == ARTIFACTS
    assert denials["DenyArtifactDeletion"]["Action"] == ["s3:DeleteObject", "s3:DeleteObjectVersion"]


def test_multipart_discovery_uses_supported_bucket_conditions():
    policies = generate_policies(**_arguments())
    for name in ("user_policy", "cleanup_policy"):
        bucket_statements = policies[name]["Statement"][-2:]
        assert bucket_statements == [
            {"Effect": "Allow", "Action": ["s3:ListBucket", "s3:GetBucketVersioning", "s3:ListBucketMultipartUploads"], "Resource": BUCKET},
            {"Effect": "Allow", "Action": "s3:ListBucketVersions", "Resource": BUCKET,
             "Condition": {"StringLike": {"s3:prefix": "workstream/submission-source/v1/*"}}},
        ]


def test_conditional_completion_is_required_without_blocking_multipart_parts():
    statements = generate_policies(**_arguments())["bucket_policy"]["Statement"]
    denials = {row["Sid"]: row for row in statements}
    assert denials["DenyUnconditionalPut"] == {
        "Sid": "DenyUnconditionalPut", "Effect": "Deny", "Principal": "*", "Action": "s3:PutObject",
        "Resource": BUCKET + "/*", "Condition": {"Null": {"s3:if-none-match": "true"},
            "Bool": {"s3:ObjectCreationOperation": "true"}},
    }
    assert denials["DenyInsecureTransport"]["Condition"] == {"Bool": {"aws:SecureTransport": "false"}}
    assert denials["DenyInsecureTransport"]["Resource"] == [BUCKET, BUCKET + "/*"]


@pytest.mark.parametrize("field,value", [
    ("user_arn", "arn:aws:iam::123456789012:user/*"),
    ("user_arn", "arn:aws:iam::123456789012:role/runtime"),
    ("user_arn", "arn:aws:iam::123456789012:user/ops/"),
    ("user_arn", "arn:aws:iam::123456789012:user//"),
    ("cleanup_user_arn", RUNTIME),
    ("cleanup_user_arn", "arn:aws:iam::999999999999:user/cleanup"),
    ("cleanup_user_arn", "arn:aws-cn:iam::123456789012:user/cleanup"),
    ("cleanup_user_arn", "arn:aws:iam::123456789012:role/cleanup"),
    ("bucket", "*"), ("private_prefix", "*"), ("private_prefix", "../other"),
])
def test_rejects_unbounded_or_foreign_identity_configuration(field, value):
    with pytest.raises(ValueError):
        generate_policies(**(_arguments() | {field: value}))
