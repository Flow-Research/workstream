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

## ART-03B Materialization And Extraction Discovery

Merged ART-03A and AUTH `WS-XINT-002-04A` provide the covered Project Manager
upload boundary. AUTH preparation happens before request-body intake; final
transaction-bound consumption locks the guide lineage and server-computed byte
facts before durable intent or provider I/O. Upload stores opaque immutable
bytes and does not parse them.

The current setup pipeline cannot yet consume those bytes safely:

- its Celery payload has four identifiers but no setup generation;
- `ProjectSetupRun` has no explicit generation fence;
- `GuideSourceMaterial` uses caller-originated metadata and optional excerpts,
  not verified ART bindings;
- no authorized integrity-checking guide read exists in project services;
- no typed detector, extractor registry, extraction policy, or canonical
  extraction record exists.

AUTH's reviewed `WS-XINT-002-04B` activates only fixed-service guide binding
and read. It does not grant a derived-artifact write. v0.1 therefore persists a
bounded canonical extraction record and provenance in PostgreSQL; a future
derived provider artifact requires a separately planned action and activation.

No document-parsing production dependencies are installed. Any new production
dependency requires explicit human approval through 03B3B1 before format implementation. OOXML ZIP
containers must pass one bounded classifier that distinguishes DOCX, PPTX, and
XLSX by internal markers. Audio/video transcription and OCR are not required by
current v0.1 setup and remain unsupported. PNG/JPEG/WebP classification and
metadata do not imply OCR or textual sufficiency.

## 2026-08-02 End-to-End v0.1 Planning Audit

Current `main` contains all ART guide implementation through `03B4`. During
this audit AUTH-04B was still pending; it subsequently merged in PR #245 at
`6babf81b`. Both fixed-service guide binding/read actions are now active, so
ART-03C may start after this planning reconciliation merges.

The remaining map had four material defects:

1. statuses still described merged 03B chunks as proposed or active;
2. 04A, 04C, 05, and 07 crossed too many L1 boundaries for one PR;
3. XINT-05A would activate contributor preparation before the fixed
   `artifact.pre_submit.checker_input.materialize` service action, even though
   hidden 04B makes that authority mandatory inside the continuous request;
4. ART ended at checker routing while XINT expected later reviewer artifact
   capabilities and the product intent required accepted contribution records
   to retain the same artifact identity.

The corrected finish line is bounded: ART owns guide cutover, one-ZIP intake,
semantic identity, prechecks, durable ready admission, atomic Submission
binding, checker materialization/output custody, reviewer packet byte access,
and accepted-contribution identity projection. REV owns review lifecycle and
notes/findings; CON owns ContributionRecord; client delivery remains a future
owner and is not silently implemented by ART v0.1.
