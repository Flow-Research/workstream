"""Generate restricted direct-user S3 policies; never create or accept credentials."""

from __future__ import annotations

import argparse
import json
import re

from app.core.s3_validation import is_canonical_s3_bucket, is_canonical_s3_prefix


def generate_policies(*, bucket: str, private_prefix: str, user_arn: str) -> dict:
    """Bind one IAM user to the existing content-addressed artifact namespace."""
    principal = re.fullmatch(
        r"arn:(aws|aws-us-gov|aws-cn):iam::[0-9]{12}:user/"
        r"(?:[A-Za-z0-9+=,.@_/-]+/)?[A-Za-z0-9+=,.@_-]{1,64}",
        user_arn,
    )
    if (
        principal is None
        or not is_canonical_s3_bucket(bucket)
        or not is_canonical_s3_prefix(private_prefix)
    ):
        raise ValueError("exact IAM user, bucket and private prefix are required")
    bucket_arn = f"arn:{principal.group(1)}:s3:::{bucket}"
    objects = f"{bucket_arn}/{private_prefix}/sha256/*"
    all_objects = f"{bucket_arn}/*"
    return {
        "user_policy": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": ["s3:GetObject", "s3:PutObject"],
                    "Resource": objects,
                },
                # HEAD of a missing key needs ListBucket to distinguish 404 from
                # access denial. No object data outside the prefix is granted.
                {
                    "Effect": "Allow",
                    "Action": "s3:ListBucket",
                    "Resource": bucket_arn,
                },
            ],
        },
        "bucket_policy": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "DenyInsecureTransport",
                    "Effect": "Deny",
                    "Principal": "*",
                    "Action": "s3:*",
                    "Resource": [bucket_arn, all_objects],
                    "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                },
                {
                    "Sid": "DenyForeignObjectAccess",
                    "Effect": "Deny",
                    "Principal": "*",
                    "Action": "s3:*",
                    "Resource": all_objects,
                    "Condition": {"ArnNotEquals": {"aws:PrincipalArn": user_arn}},
                },
                {
                    "Sid": "DenyOutsideArtifactNamespace",
                    "Effect": "Deny",
                    "Principal": "*",
                    "Action": ["s3:GetObject", "s3:GetObjectVersion", "s3:PutObject"],
                    "NotResource": objects,
                },
                {
                    "Sid": "DenyArtifactDeletion",
                    "Effect": "Deny",
                    "Principal": "*",
                    "Action": ["s3:DeleteObject", "s3:DeleteObjectVersion"],
                    "Resource": all_objects,
                },
                {
                    "Sid": "DenyUnconditionalPut",
                    "Effect": "Deny",
                    "Principal": "*",
                    "Action": "s3:PutObject",
                    "Resource": all_objects,
                    "Condition": {"Null": {"s3:if-none-match": "true"}},
                },
            ],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--private-prefix", required=True)
    parser.add_argument("--user-arn", required=True)
    arguments = parser.parse_args()
    try:
        policies = generate_policies(**vars(arguments))
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(policies, indent=2))


if __name__ == "__main__":
    main()
