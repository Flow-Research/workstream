# Discovery: WS-ART-001 S3-Compatible Object Storage Amendment

## Repository State

- `WS-ART-001-01` merged through PR #101 as `050eb15`.
- `backend/app/interfaces/artifacts.py` defines `ArtifactStore`.
- `backend/app/adapters/artifacts/local.py` implements LocalStorage.
- `backend/app/modules/artifacts/service.py` coordinates provider I/O outside
  PostgreSQL transactions.
- `backend/app/modules/artifacts/models.py` already contains upload, content,
  replica, receipt, and binding foundations.
- `backend/app/adapters/artifacts/__init__.py` has one resolver with a dormant
  `flow_node` branch that always fails.
- `backend/app/core/config.py` accepts `disabled|local|flow_node`; no
  S3-compatible object-storage configuration exists.
- `backend/pyproject.toml` has no asynchronous S3 SDK dependency.
- `docker-compose.yml` contains Postgres and Redis but no S3-compatible local
  service.

## Contract Mismatch Found

The merged v1 port makes providers own `verify`, `retain`, `release`, and
operation receipts. Those methods reflect the earlier Flow Node design and are
not the correct boundary for S3-compatible byte storage.

For v0.1:

- provider operations are immutable conditional put, open/range read, and
  head/status;
- Workstream independently verifies bytes through the read port;
- PostgreSQL owns operation receipts, bindings, reference state, and audit;
- physical delete is absent.

The v2 port must therefore replace v1 in one clean cut. No adapter alias or
compatibility shim is required because Workstream is still pre-production.

## AWS S3 Provider Facts Used By The Plan

- AWS S3 defines the production protocol contract and supports conditional
  writes, object head, full/range reads, workload identity, Block Public
  Access, bucket policy, and lifecycle inspection.
- Workstream independently computes SHA-256; ETag and provider metadata are not
  content identity.
- Production credentials come from one explicitly allowlisted AWS workload
  identity method. Static access keys are limited to local/CI MinIO.
- v0.1 uses one conditional single-request put and rejects objects above the
  hard size limit. Multipart completion is deferred until separately designed
  and proven.
- MinIO is protocol proof, not evidence that an AWS deployment is private or
  correctly authorized. AWS requires its own live readiness proof.

Canonical references:

- https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-control-block-public-access.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lifecycle-mgmt.html
- https://docs.aws.amazon.com/sdkref/latest/guide/standardized-credentials.html

## v0.1 Storage Algorithm

1. Prepare every untrusted source completely, compute Workstream SHA-256 and
   exact size, and reject any mismatched client commitment before provider I/O.
2. Seal that commitment with the exact second-pass stream.
3. Derive the private key
   `artifacts/sha256/<first-two-hex>/<remaining-hex>`.
4. Upload with one conditional no-overwrite `PutObject`; reject objects above
   the v0.1 512 MiB hard maximum before provider I/O.
5. Treat a precondition failure as a replay candidate, not success.
6. Head the existing object, then independently stream and hash the complete
   object before accepting it.
7. Mark the replica bindable only after SHA-256 and size match.

## Recovery Simplification

The S3-compatible object-storage design removes provider retain/release and
physical delete from v0.1.
Durable background work has one class:

- `provider_observation`: complete-object verification through fresh read;

There is no exact provider replay, destructive requeue, or ambiguous logical
provider effect in v0.1 recovery.

Operator authorization creates a reason-bound recovery envelope and linked
verification job. The job is the sole Celery execution owner. PostgreSQL
coordinates its invocations with a fixed lease, fresh executor UUID, and
generation fence. A periodic PostgreSQL scanner guarantees that a committed
job is eventually published even if the first broker call fails.

## Security Boundaries

- Authorization Service owns product decisions.
- S3 credentials authorize transport only and never imply product authority.
- Credentials come from deployment secret injection and never enter Postgres,
  Redis, Celery payloads, logs, receipts, or API responses.
- Only artifact-storage orchestration consumes the writable `ArtifactStore`
  through dependency injection and never imports the S3 implementation.
  Product modules and Celery jobs consume typed artifact operations instead.
- The S3 endpoint is trusted configuration. Production requires HTTPS and a
  private bucket; localhost HTTP is allowed only in local/test MinIO.
- No public bucket, custom-domain cache, or client-visible object key is used.
- Runtime credentials are bucket/prefix/action scoped. They cannot delete,
  copy, or administer provider configuration. AWS has bucket-level
  `s3:ListBucket` only so missing `HeadObject` can return 404; the port and
  application expose and call no object-list operation.
- Production release evidence proves AWS public-access controls, lifecycle
  safety, and anonymous-read denial.

## Deferred Flow Node

The previous Flow Node analysis is preserved on branch
`codex/ws-art-001-fn01-isolation-amendment`. A new deferred initiative will
retain the provider-conformance, focused-service, adapter, and migration plan.
It cannot block or modify v0.1 S3-compatible object-storage work.

## Deferred R2

Exact-head internal review found that the dual-provider plan introduced an R2
parent-credential and credential-issuer boundary that was not required to ship
v0.1. The user selected AWS S3 as the only production provider. R2 therefore
has no active runtime profile, credential service, deployment proof, or chunk;
later adoption requires separate discovery and approval.

The current pre-cutover application still accepts legacy caller-declared
provider schemes in guide-source, task, project-policy, checker, API-drill, and
template contracts. Those values have no active v0.1 provider meaning and do
not prove that Workstream can store or retrieve provider bytes. Chunk 03
removes direct provider schemes from guide-source identity. Chunk 05 removes
the remaining caller storage transport when submissions move to sealed
artifact-set bindings. No compatibility alias remains after either owning
cutover.
