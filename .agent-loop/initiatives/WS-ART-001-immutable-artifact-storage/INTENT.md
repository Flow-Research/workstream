# Intent: WS-ART-001 Immutable Artifact Storage

## Problem

Workstream records artifact URIs and caller-declared hashes without owning the
exact bytes. Pre-submit checks, post-submit checks, reviewers, revisions, and
audit records therefore cannot prove that they consumed one immutable artifact.

## Approved v0.1 Direction

Workstream will use one provider-neutral `ArtifactStore` capability:

```text
LocalStorageAdapter          development and focused unit tests
S3CompatibleArtifactStore    integration and production
AWS S3                       v0.1 production provider
MinIO                        local and CI protocol proof
```

Flow Node is not a v0.1 dependency. It remains a separately planned future
`ArtifactStore` implementation and does not run, deploy, or block Workstream
v0.1. Cloudflare R2 is also deferred and has no v0.1 runtime profile,
credential service, configuration path, or deployment.

Provider selection is not a hot switch for populated storage. Each replica
records immutable provider profile and storage namespace; changing providers
requires a separate verified migration and maintenance cutover.

## Success State

```text
authorized bytes
-> bounded server preparation and SHA-256/byte count
-> optional client commitment comparison
-> private Workstream upload stream
-> content-addressed S3-compatible object key
-> independent complete-object verification
-> immutable ArtifactContent and ArtifactReplica facts
-> sealed artifact-set commitment
-> ArtifactBinding to guide, submission, checker input, log, or output
```

PostgreSQL stores metadata, bindings, operation receipts, lifecycle state,
audit, and recovery coordination. The object provider stores bytes only.

## First-Principle Constraints

- Workstream computes and verifies canonical SHA-256 and byte count.
- Production writes use only Workstream's server-computed SHA-256 and byte
  count; any client commitment is checked before provider I/O.
- Object keys contain no customer filename, project, task, actor, or secret.
- The production bucket is private and is never exposed through a public or
  cached domain.
- Clients do not receive provider credentials, signed URLs, or direct-upload
  authority in v0.1.
- Provider success does not make bytes bindable. A complete independent read
  and hash must pass first.
- Workstream references and audit records are not encoded as provider tags,
  retention references, or object metadata.
- v0.1 performs no physical object deletion. Release and garbage collection
  require a later approved deletion-policy initiative.
- Local storage is forbidden in staging and production.
- No compatibility alias or dual provider-construction path is retained.

## Why S3-Compatible Object Storage First

S3-compatible storage already supplies durable private object storage, range
reads, and conditional writes. AWS S3 provides the v0.1 production service,
while MinIO proves the protocol locally and in CI. Workstream should build its
product semantics instead of first operating a new storage or credential
service.

Flow Node remains strategically useful, but extracting, authenticating,
hardening, deploying, and integrating it is unnecessary to prove Workstream's
v0.1 contribution lifecycle.

## Non-Goals

- no Flow Node runtime or adapter implementation;
- no Cloudflare R2 runtime profile or credential issuer;
- no public artifact publication or CDN path;
- no presigned or browser-direct uploads;
- no provider-side legal hold, pin, retain, or release API;
- no physical deletion or garbage collection;
- no semantic search;
- no review packet or reviewer evidence implementation, which remains WS-REV;
- no payment, reputation, blockchain, or marketplace expansion.

## Proof

- one conformance suite runs against LocalStorage and an S3-compatible MinIO
  service;
- the AWS S3 production profile is proven through private-bucket,
  least-privilege, lifecycle, and anonymous-read-negative checks;
- conditional concurrent writes cannot overwrite an existing object;
- adversarial first-writer input cannot occupy a client-selected digest key;
- complete-object verification catches changed, truncated, missing, or
  mismatched bytes;
- broker publication failure is recovered by a periodic PostgreSQL scanner;
- Operator retry is authorized, reason-bound, observable, and executed only by
  Celery under PostgreSQL generation fencing;
- guide, pre-submit, post-submit, and reviewer-facing records resolve the same
  immutable content commitment;
- the final real API drill runs without direct database inspection.

## Human Decisions

- S3-compatible object storage for v0.1 and deferred Flow Node: approved on
  2026-07-14.
- AWS S3 as the only v0.1 production provider: approved on 2026-07-14. R2 was
  deferred after exact-head review exposed its parent-credential boundary.
- One typed repository-wide external-service adapter/factory convention was
  explicitly approved during this planning work. WS-ART migrates only
  ArtifactStore; auth and agent-runtime owners decide and execute their own
  later clean cuts.
- Physical deletion: explicitly deferred.
- Each implementation chunk still requires a separate explicit start and
  explicit merge approval.
