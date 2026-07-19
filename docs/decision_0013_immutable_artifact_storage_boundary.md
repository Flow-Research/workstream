# ADR 0013: Immutable Artifact Storage Boundary

## Status

Accepted. Amended on 2026-07-14 to use AWS S3 as the only v0.1 production
object store, MinIO for local/CI protocol proof, and defer Cloudflare R2 and
Flow Node to separate optional adapter initiatives.

## Context

Workstream accepts project-guide material, contributor submission artifacts,
checker inputs, checker logs, and checker outputs. A caller-declared URI or
hash does not prove that Workstream stored and evaluated one exact immutable
byte sequence.

ADR 0008 requires an object-storage abstraction. This ADR defines the exact
content identity, provider boundary, verification, binding, recovery, and
cutover rules required by Workstream.

## Decision

Workstream uses the provider-neutral `ArtifactStore` capability:

```text
LocalStorageAdapter          development and focused unit tests
S3CompatibleArtifactStore    integration and production
  AWS S3                     v0.1 production provider
  MinIO                      local and CI integration provider
```

The `local/CI` MinIO label is a non-production eligibility class, not a literal
endpoint-host restriction. Repository-owned Compose and CI instances publish
on host loopback. An operator-controlled private container-network endpoint may
be used only in local, development, or test environments and does not count as
production activation evidence.

AWS S3 is the only v0.1 production provider. Each replica persists immutable
provider profile and storage-namespace identity. Switching a populated
deployment requires a separately approved complete-copy, verification, and
maintenance cutover; it is not a hot configuration toggle. AWS becomes
production-eligible only after private-bucket, exact trusted-principal,
least-privilege, lifecycle, anonymous-read-negative, and unapproved-
authenticated-principal negative live proof succeeds in the deployment-only
Chunk 07 harness.

The AWS bucket is dedicated to Workstream artifact objects. The runtime role
has `s3:PutObject` and `s3:GetObject` on the completed-object ARN plus
`s3:ListBucket` on the bucket ARN solely so `HeadObject` can distinguish a
missing key as 404 rather than masking it as 403. `ArtifactStore` exposes no
list operation, Workstream never calls an object-list API, and every 403 remains
provider unavailable rather than evidence of absence. The runtime principal can
technically enumerate opaque hashes in this dedicated bucket; that accepted
v0.1 risk is recorded explicitly because AWS provides no narrower permission
that still yields trustworthy missing-key 404 responses.

Cloudflare R2 and Flow Node are not v0.1 dependencies. Later approved
initiatives may implement the same `ArtifactStore` port and conformance
contract. Workstream does not run, deploy, or maintain either for v0.1.

## Ownership

The object-storage provider owns:

- private immutable bytes;
- an opaque object reference;
- protocol-level put, read, range-read, and head behavior.

Workstream and PostgreSQL own artifact product state and persisted evidence:

- canonical SHA-256 and byte count;
- upload intent and idempotency identity;
- independent complete-object verification;
- content and replica records;
- guide, task, submission, checker, and future review bindings;
- lifecycle, operation receipts, audit, and recovery coordination;
- every product-state decision and the evidence of each Authorization Service
  decision.

The Authorization Service alone owns every artifact action/resource
authorization decision. PostgreSQL records its evidence but grants no authority.

Provider credentials are transport credentials. They are never product
authority and never replace an Authorization Service decision.

AWS production credential mode `aws_workload_identity` selects
exactly one allowlisted method: `assume-role-with-web-identity`,
`container-role`, or `iam-role`.
Workstream constrains the credential resolver to that selected method and
rejects explicit credentials, ambient access keys, file/process/login/SSO
sources, legacy EC2/Boto sources, and every unselected workload provider before
loading credentials. Static credentials are limited to local/CI MinIO.
Cloudflare R2 is deferred; this initiative defines no credential issuer,
sidecar, secret contract, or runtime profile for it.

## ArtifactStore Contract

The v0.1 port exposes only immutable byte-provider behavior:

```text
put(source: CommittedArtifactSource)
observe_put_result(commitment: ArtifactCommitment)
open(provider_object_ref, optional_range)
head(provider_object_ref)
```

The port has no provider `verify`, `retain`, `release`, delete, list, signed
URL, search, product binding, or provider-receipt lookup operation. Workstream
verifies through `open`; PostgreSQL owns operation receipts and references.

## Immutable Identity And Upload

Every untrusted or initially uncommitted source first crosses Workstream's
bounded `PreparedArtifact` boundary. Workstream computes digest and byte count,
checks any client commitment before provider I/O, and seals the commitment and
second-pass stream as one `CommittedArtifactSource`. Production upload accepts
only that source and derives an identity-free private object key:

```text
<private-prefix>/sha256/<first-two-hex>/<remaining-hex>
```

The key contains no actor, customer, project, task, filename, media type, or
secret. The S3-compatible adapter uses conditional no-overwrite semantics. A
precondition failure starts exact existing-object recovery; it is never treated
as proof that the object is correct.

v0.1 uses one conditional `PutObject` request and enforces a 512 MiB hard
maximum per object. Multipart upload is deferred until a separate initiative
proves its atomic no-overwrite and recovery algorithm.

Workstream streams bytes through its API/service boundary. v0.1 does not issue
presigned URLs, expose provider credentials, or permit browser-to-provider
uploads.

## Independent Verification

A provider acknowledgement sets the upload item to
`stored_pending_verification` and creates a pending replica, not a bindable
artifact. A durable Celery job performs a fresh complete-object read,
computes SHA-256 and byte count, and records an immutable verification receipt.
Only a matching replica becomes bindable.

ETag, provider checksum metadata, object metadata, and provider acknowledgement
are not canonical Workstream integrity facts. This rule keeps the same contract
portable across AWS S3, MinIO, LocalStorage, and future provider adapters.

## Privacy And Retention

Production object storage is private, uses TLS, and is not served through a
public bucket, public custom domain, or CDN cache. Provider references,
endpoints, and credentials do not appear in product API responses.

v0.1 performs no physical deletion of completed objects. PostgreSQL may record
logical reference state, but there is no runtime provider delete, retain,
release, garbage-collection, or legal-hold emulation API. Bucket lifecycle
rules must not delete the Workstream completed-object prefix. Production
activation uses a separate read-only deployment identity to inspect AWS
lifecycle rules and fails if an enabled expiration/deletion rule can intersect
that prefix. A separate approved initiative must define physical deletion.

Because completed bytes are retained, one generic Workstream admission service
enforces durable storage quotas in PostgreSQL before every provider write.
Applicable task, producer, project, and deployment charges are atomically
bounded. Provisional and completed charges count; ambiguous provider outcomes
remain provisional until deterministic recovery confirms existence or absence.
Only confirmed absence releases a charge. Cancelled, expired, unbound,
quarantined, and integrity-mismatched completed content remains charged until a
separately approved physical-deletion lifecycle exists. Exact deduplicated
content is charged once per applicable scope; concurrent reservations cannot
oversubscribe a limit.

## Recovery

Recovery has one closed class:

```text
provider_observation    fresh read and complete-object verification
```

Operator authorizes a reason- and idempotency-bound retry through a recovery-
attempt audit envelope that records distinct source and retry verification job
IDs. Exact request replay returns the original attempt/job IDs; altered replay
conflicts. A source verification job has at most one recovery attempt for its
entire lifetime; any later recovery must target the immediate retry job after
that job independently exhausts `provider_unavailable`. The retry job is the
only Celery execution owner. Celery executes
under a fixed internal service
principal. PostgreSQL coordinates duplicate executions using its clock, an
execution UUID, lease expiry, and an atomically incremented generation token. A
stale execution cannot write terminal state.

Post-commit broker publication is best effort. A periodic PostgreSQL scanner
re-publishes pending and expired work within a configured SLA. Startup-only
recovery is insufficient.

Artifact-recovery execution leases coordinate Celery workers only. They are
unrelated to contributor task claims, reviewer leases, review/revision state,
or human ownership.

## Failure Meaning

Storage conditions do not introduce task or review decisions. Stable failures
include `artifact_storage_unavailable`, `artifact_input_mismatch`,
`artifact_upload_expired`, `artifact_upload_consumed`, and
`artifact_integrity_failure`.

Transient post-submit retrieval failure keeps the task in
`evaluation_pending`. Integrity mismatch quarantines the replica and blocks
binding. Neither condition creates `accept`, `needs_revision`, `reject`, a
contribution, compensation-award, or reputation effect.

## Shared Adapter Convention

Artifact storage follows ADR 0014. `LocalStorageAdapter` and
`S3CompatibleArtifactStore` are reached through explicitly registered,
non-mutating `ArtifactStoreBootstrap` implementations in
`ExternalServiceAdapterFactory[ArtifactStoreBootstrap]`. The composition root
claims the bootstrap's exact namespace in PostgreSQL before initialization
yields the byte-only `ArtifactStore`. Only artifact-storage orchestration
receives that writable port. Product modules and Celery jobs receive typed
artifact ingest/read/materialization operations instead.

There is no service locator, runtime plugin discovery, concrete-adapter import
in product services, fallback constructor, compatibility alias, or dual factory
path.

## Clean Cutover

The existing ArtifactStore v1 provider `verify`, `retain`, `release`, and
receipt methods are removed in the same chunk that migrates LocalStorage and
all active callers. The dormant Flow Node backend setting is removed. The new
backend values are exactly `disabled`, `local`, and `s3_compatible`.

Migration `0025` refuses populated v1 artifact tables before DDL and preserves
their prior schema and rows. An empty pre-production environment may be
reprovisioned out of band and authoritative bytes reingested through v2; the
migration performs no automated rebuild or fabricated backfill. No alias,
nullable shadow field, dual write, or fallback remains.

## Review Boundary

WS-REV owns `ReviewPacketManifest` and `ReviewEvidenceArtifact`. Both reference
general `ArtifactBinding` records and consume the same immutable bytes. ART v2
owns bytes, bindings, candidate/finalize intake, verification, retention,
provider execution, and recovery. REV owns exact packet membership and the
finding/response evidence relationship.

Artifact bytes are readable only for the exact Submission packet covered by a
current active ReviewLease. Authorized history is bounded metadata only. Prior,
expired, consumed, sibling, later, cross-task, and cross-project leases cannot
read packet bytes.

Review decision and canonical contribution creation perform no ART call or
provider I/O. They consume stabilized binding facts and copy the server-derived
Submission `artifact_hash`. REV never imports the raw byte-only ArtifactStore,
concrete providers, ART repositories, scratch state, `ArtifactScratchManager`,
`PreparedArtifact`, or `CommittedArtifactSource`.

## Precedence

- ADR 0008 continues to require provider-neutral object storage.
- This ADR governs immutable artifact identity and provider integration.
- ADR 0011 continues to govern project policy derivation and deterministic
  checker compilation; WS-ART cutovers remove only obsolete caller-owned
  transport declarations.
- ADR 0012 and the Authorization Service govern product authority.
- ADR 0014 governs external adapter construction and injection.
- `docs/spec_artifact_storage_service.md` is the canonical implementation
  contract.
- `docs/spec_review_lifecycle.md` is canonical for review packet membership,
  lease-bounded disclosure, and evidence semantics.
- Archival reference specifications are non-executable inputs.

## Consequences

Positive:

- AWS S3 ships without coupling product services to a concrete adapter;
- Workstream proves exact bytes independently of provider-specific metadata;
- checkers and reviewers can reference the same immutable content;
- v0.1 avoids operating an unnecessary storage service;
- a future Flow Node adapter remains possible without product-service changes.

Tradeoffs:

- Workstream must operate durable verification and recovery jobs;
- completed-object deletion is intentionally deferred;
- AWS S3 needs a live private-bucket and workload-identity smoke proof;
- product cutovers wait for their named Authorization Service dependencies.
