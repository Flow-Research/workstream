# AWS S3 credentials

Workstream stores file bytes in a private S3 bucket. PostgreSQL holds the
metadata and ownership used to authorize access. Contributors, reviewers,
setup agents and external checker guests do not receive the bucket credential.

The hosted application uses a dedicated IAM user's access key. Source cleanup
uses a separate IAM user and private key file in its dedicated worker. This works
on AWS or another hosting provider. No certificate authority, certificate
renewal, three-identity verification job or expiring database activation is
required.

## Provision the dedicated identity

Create two distinct IAM users in the bucket owner’s AWS account, without console
access, group membership or other attached policies: the runtime uploader/reader
and the source-cleanup worker. The generator rejects cross-account or identical
principals. Generate their restricted policies and the bucket policy using
the deployment's actual bucket and existing private prefix:

```bash
cd backend
python -m scripts.aws_direct_user_config \
  --bucket YOUR_BUCKET \
  --private-prefix YOUR_EXISTING_PREFIX \
  --user-arn arn:aws:iam::YOUR_ACCOUNT:user/workstream-storage \
  --cleanup-user-arn arn:aws:iam::YOUR_ACCOUNT:user/workstream-source-cleanup
```

The output contains `user_policy`, `cleanup_policy` and `bucket_policy`. Attach
each identity policy only to its corresponding user; apply the bucket policy
to the dedicated artifact bucket.
Review existing bucket users before replacing a bucket policy. Do not change
the prefix of an existing deployment: retained objects must remain readable.

The runtime can read and conditionally create content-addressed artifacts and
operation-owned `submission-source/v1/<operation-id>/bundle.zip` objects. It can
read exact source versions, but cannot delete versions or abort multipart uploads.
Cleanup can read, abort and delete exact versions only in the managed source
prefix; it cannot write sources or access content-addressed artifact bytes.
Unversioned deletion is denied to both users, preventing delete-marker creation.

Bucket-level listing permits authoritative HEAD absence checks and multipart
handle discovery. It exposes bucket key/handle metadata to the trusted storage
services, not unrelated object bytes. AWS does not support an `s3:prefix` IAM
condition on `ListBucketMultipartUploads`; the adapter must still use bounded
exact-key discovery. Version listing is prefix-restricted. See the
[AWS S3 action/condition reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_s3.html).
Never interpret access denial as absence.

Failed and retained submission sources share the same prefix. IAM cannot tell
which source is accepted: the ART owner's committed cleanup claim, retention
checks and exact-version confirmation remain the deletion authority. Never
expose a general delete-by-key operation or cleanup credentials to API workers.

Keep S3 Block Public Access enabled, bucket-owner-enforced ownership,
versioning and default SSE-S3 (`AES256`) encryption enabled. This policy does
not grant KMS permissions; it does not qualify an SSE-KMS deployment. Do not configure lifecycle expiration of
retained artifacts. The bucket policy rejects insecure transport, foreign
object access, unconditional final writes and deletion of content-addressed
artifacts. Conditional-header enforcement exempts multipart initiation/parts
using `s3:ObjectCreationOperation`; completing the upload still requires
`If-None-Match`. This follows [AWS conditional-write enforcement](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes-enforce.html).

## Keep credentials private

Create an access key for each dedicated user. Store each pair in a separate private
JSON file readable only by the runtime service user:

```json
{"access_key_id":"REPLACE_LOCALLY","secret_access_key":"REPLACE_LOCALLY"}
```

Do not put the values in the release environment, shell command arguments,
Git, logs or chat. Mount the file read-only only into services performing
artifact operations. Beat, MCP, the document parser and checker guests do not
need it. Configure the exact IAM user ARN alongside the private file path;
startup must reject an unexpected identity or an ambient credential source.
The cleanup worker uses its own credential-file and IAM-ARN settings and an
explicit upload-principal ARN; composition rejects identical principals.

## Verify and rotate

Before cutover, test a synthetic artifact using the real restricted identity:
conditional creation, complete hash/size readback, safe replay, missing-object
handling, and rejection of overwrites, deletion, foreign-prefix writes and
anonymous reads. Qualify source multipart initiation/completion, pinned-version
reads, lost acknowledgments, separate-principal abort, exact-version removal
and retained-source survival. Runtime deletion and cleanup writes/foreign-prefix
access must fail with actual restricted credentials. The AWS intake gate stays
closed until this source qualification is complete. Confirm guide reads and submission upload/recovery through
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
