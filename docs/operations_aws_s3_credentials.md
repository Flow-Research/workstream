# AWS S3 credentials

Workstream stores file bytes in a private S3 bucket. PostgreSQL holds the
metadata and ownership used to authorize access. Contributors, reviewers,
setup agents and external checker guests do not receive the bucket credential.

The hosted application uses one dedicated IAM user's access key. This works
on AWS or another hosting provider. No certificate authority, certificate
renewal, three-identity verification job or expiring database activation is
required.

## Provision the dedicated identity

Create a dedicated IAM user in the bucket owner’s AWS account, without console
access, group membership or other attached policies. This policy does not grant
cross-account access. Generate its restricted policy and the bucket policy using
the deployment's actual bucket and existing private prefix:

```bash
cd backend
python -m scripts.aws_direct_user_config \
  --bucket YOUR_BUCKET \
  --private-prefix YOUR_EXISTING_PREFIX \
  --user-arn arn:aws:iam::YOUR_ACCOUNT:user/workstream-storage
```

The output contains `user_policy` and `bucket_policy`. Attach the former to
the dedicated user and apply the latter to the dedicated artifact bucket.
Review existing bucket users before replacing a bucket policy. Do not change
the prefix of an existing deployment: retained objects must remain readable.

The user can read and conditionally create objects only in Workstream's
content-addressed prefix. It cannot delete objects, administer IAM or modify
bucket settings. `ListBucket` is granted for this bucket so a missing-object
HEAD request returns an authoritative absence rather than an access denial;
it exposes key names to the trusted storage service, not other object bytes.
The application must never interpret an access-denied response as absence.

Keep S3 Block Public Access enabled, bucket-owner-enforced ownership,
versioning and default SSE-S3 (`AES256`) encryption enabled. This policy does
not grant KMS permissions; it does not qualify an SSE-KMS deployment. Do not configure lifecycle expiration of
retained artifacts. The bucket policy rejects insecure transport, foreign
object access, unconditional puts and deletion of objects or versions.

## Keep credentials private

Create an access key for this dedicated user. Store its two values in a private
JSON file readable only by the runtime service user:

```json
{"access_key_id":"REPLACE_LOCALLY","secret_access_key":"REPLACE_LOCALLY"}
```

Do not put the values in the release environment, shell command arguments,
Git, logs or chat. Mount the file read-only only into services performing
artifact operations. Beat, MCP, the document parser and checker guests do not
need it. Configure the exact IAM user ARN alongside the private file path;
startup must reject an unexpected identity or an ambient credential source.

## Verify and rotate

Before cutover, test a synthetic artifact using the real restricted identity:
conditional creation, complete hash/size readback, safe replay, missing-object
handling, and rejection of overwrites, deletion, foreign-prefix writes and
anonymous reads. Confirm guide reads and submission upload/recovery through
Workstream as well. These tests qualify the deployment; they do not create a
time-limited permission record required by ordinary storage operations.

To rotate, create the replacement key, write a new private file, verify the
identity and storage operations, restart affected consumers with the new file,
and disable the old key. Delete the old key after verifying that no service
uses it. Keep at most the active key and the temporary rotation key.

AWS authenticates each request. Workstream still enforces authorization,
namespace ownership, conditional creation and complete-byte verification.
Uncertain writes retain their existing recovery workflow; a failed request
does not establish successful storage.

## Security trade-off

AWS recommends temporary workload credentials where practical. A dedicated
long-lived key replaces certificate operations with responsibility for secure
key custody and rotation. It must not be the provisioning or administrator key.

Removing the old periodic database proof also removes its bounded detection
of out-of-band IAM/bucket configuration changes. Deployment administrators
remain trusted, and must requalify storage when changing credentials or bucket
configuration. This does not make file hashes or product authorization optional.

See [AWS IAM guidance](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)
and [S3 conditional-write enforcement](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes-enforce.html).
