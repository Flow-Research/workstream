"""Generate restricted direct-user S3 policies; never create or accept credentials."""

from __future__ import annotations

import argparse
import json
import re

from app.core.s3_validation import is_canonical_s3_bucket, is_canonical_s3_prefix


def generate_policies(*, bucket: str, private_prefix: str, user_arn: str, cleanup_user_arn: str) -> dict:
    """Separate source upload and cleanup while retaining immutable artifact access."""
    pattern = (r"arn:(aws|aws-us-gov|aws-cn):iam::([0-9]{12}):user/"
               r"(?:[A-Za-z0-9+=,.@_-]+/)*[A-Za-z0-9+=,.@_-]{1,64}")
    runtime, cleanup = re.fullmatch(pattern, user_arn), re.fullmatch(pattern, cleanup_user_arn)
    if (runtime is None or cleanup is None or runtime.groups() != cleanup.groups()
            or user_arn == cleanup_user_arn or not is_canonical_s3_bucket(bucket)
            or not is_canonical_s3_prefix(private_prefix)):
        raise ValueError("distinct same-account IAM users, exact bucket and private prefix are required")
    bucket_arn = f"arn:{runtime.group(1)}:s3:::{bucket}"
    artifacts = f"{bucket_arn}/{private_prefix}/sha256/*"
    source_prefix = f"{private_prefix}/submission-source/v1/"
    sources = f"{bucket_arn}/{source_prefix}*/bundle.zip"
    all_objects = f"{bucket_arn}/*"
    # Multipart LIST has no s3:prefix IAM condition key. The adapter limits
    # discovery to the exact managed key; object/abort rights remain scoped.
    bucket_reads = [
        {"Effect": "Allow", "Action": ["s3:ListBucket", "s3:GetBucketVersioning", "s3:ListBucketMultipartUploads"], "Resource": bucket_arn},
        {"Effect": "Allow", "Action": "s3:ListBucketVersions",
         "Resource": bucket_arn, "Condition": {"StringLike": {"s3:prefix": source_prefix + "*"}}},
    ]
    return {
        "user_policy": {"Version": "2012-10-17", "Statement": [
            {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject"], "Resource": artifacts},
            {"Effect": "Allow", "Action": ["s3:GetObject", "s3:GetObjectVersion", "s3:PutObject",
                "s3:ListMultipartUploadParts"], "Resource": sources},
            *bucket_reads,
        ]},
        "cleanup_policy": {"Version": "2012-10-17", "Statement": [
            {"Effect": "Allow", "Action": ["s3:GetObject", "s3:GetObjectVersion", "s3:DeleteObjectVersion",
                "s3:AbortMultipartUpload", "s3:ListMultipartUploadParts"], "Resource": sources},
            *bucket_reads,
        ]},
        "bucket_policy": {"Version": "2012-10-17", "Statement": [
            {"Sid": "DenyInsecureTransport", "Effect": "Deny", "Principal": "*", "Action": "s3:*",
             "Resource": [bucket_arn, all_objects], "Condition": {"Bool": {"aws:SecureTransport": "false"}}},
            {"Sid": "DenyForeignObjectAccess", "Effect": "Deny", "Principal": "*", "Action": "s3:*",
             "Resource": all_objects,
             "Condition": {"ArnNotEquals": {"aws:PrincipalArn": [user_arn, cleanup_user_arn]}}},
            {"Sid": "DenyOutsideArtifactNamespace", "Effect": "Deny", "Principal": "*", "Action": "s3:*",
             "NotResource": [bucket_arn, artifacts, sources]},
            {"Sid": "DenyCleanupOutsideSource", "Effect": "Deny", "Principal": "*", "Action": "s3:*",
             "NotResource": [bucket_arn, sources], "Condition": {"ArnEquals": {"aws:PrincipalArn": cleanup_user_arn}}},
            {"Sid": "DenyCleanupWrites", "Effect": "Deny", "Principal": "*", "Action": "s3:PutObject",
             "Resource": all_objects, "Condition": {"ArnEquals": {"aws:PrincipalArn": cleanup_user_arn}}},
            {"Sid": "DenyRuntimeDestruction", "Effect": "Deny", "Principal": "*",
             "Action": ["s3:DeleteObject", "s3:DeleteObjectVersion", "s3:AbortMultipartUpload"],
             "Resource": all_objects, "Condition": {"ArnNotEquals": {"aws:PrincipalArn": cleanup_user_arn}}},
            {"Sid": "DenyUnversionedDeletion", "Effect": "Deny", "Principal": "*",
             "Action": "s3:DeleteObject", "Resource": all_objects},
            {"Sid": "DenyArtifactDeletion", "Effect": "Deny", "Principal": "*",
             "Action": ["s3:DeleteObject", "s3:DeleteObjectVersion"], "Resource": artifacts},
            {"Sid": "DenyUnconditionalPut", "Effect": "Deny", "Principal": "*", "Action": "s3:PutObject",
             "Resource": artifacts, "Condition": {"Null": {"s3:if-none-match": "true"}}},
            {"Sid": "DenyUnconditionalSourceCompletion", "Effect": "Deny", "Principal": "*", "Action": "s3:PutObject",
             "Resource": sources, "Condition": {"Null": {"s3:if-none-match": "true"},
                 "Bool": {"s3:ObjectCreationOperation": "true"}}},
        ]},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--private-prefix", required=True)
    parser.add_argument("--user-arn", required=True)
    parser.add_argument("--cleanup-user-arn", required=True)
    arguments = parser.parse_args()
    try:
        policies = generate_policies(**vars(arguments))
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(policies, indent=2))


if __name__ == "__main__":
    main()
