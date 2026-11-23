"""Security boundaries of the generated dedicated S3 identity policies."""

import pytest

from scripts.aws_direct_user_config import generate_policies


def test_runtime_cannot_administer_or_delete_artifacts():
    policies = generate_policies(
        bucket="example-artifacts",
        private_prefix="workstream",
        user_arn="arn:aws:iam::123456789012:user/workstream-storage",
    )
    statements = policies["user_policy"]["Statement"]
    assert statements == [
        {
            "Effect": "Allow",
            "Action": ["s3:GetObject", "s3:PutObject"],
            "Resource": "arn:aws:s3:::example-artifacts/workstream/sha256/*",
        },
        {
            "Effect": "Allow",
            "Action": "s3:ListBucket",
            "Resource": "arn:aws:s3:::example-artifacts",
        },
    ]
    denials = {row["Sid"]: row for row in policies["bucket_policy"]["Statement"]}
    assert all(row["Effect"] == "Deny" for row in denials.values())
    assert denials["DenyArtifactDeletion"]["Action"] == [
        "s3:DeleteObject", "s3:DeleteObjectVersion"
    ]
    assert denials["DenyUnconditionalPut"]["Condition"] == {
        "Null": {"s3:if-none-match": "true"}
    }
    assert denials["DenyForeignObjectAccess"]["Condition"] == {
        "ArnNotEquals": {
            "aws:PrincipalArn": "arn:aws:iam::123456789012:user/workstream-storage"
        }
    }
    assert denials["DenyOutsideArtifactNamespace"]["NotResource"] == (
        "arn:aws:s3:::example-artifacts/workstream/sha256/*"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("user_arn", "arn:aws:iam::123456789012:user/*"),
        ("user_arn", "arn:aws:iam::123456789012:role/runtime"),
        ("user_arn", "arn:aws:iam::123456789012:user/ops/"),
        ("user_arn", "arn:aws:iam::123456789012:user//"),
        ("bucket", "*"),
        ("private_prefix", "*"),
        ("private_prefix", "../other"),
    ],
)
def test_rejects_unbounded_or_foreign_identity_configuration(field, value):
    arguments = {
        "bucket": "example-artifacts",
        "private_prefix": "workstream",
        "user_arn": "arn:aws:iam::123456789012:user/workstream-storage",
    }
    arguments[field] = value
    with pytest.raises(ValueError):
        generate_policies(**arguments)
