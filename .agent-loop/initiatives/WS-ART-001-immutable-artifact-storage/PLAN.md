# Plan: WS-ART-001 S3-Compatible Object Storage

## Contract Precedence

After explicit human merge approval, ADR 0013 and
`docs/spec_artifact_storage_service.md` are the canonical v0.1 artifact
contract. The earlier provider plan is superseded for v0.1 and retained only as
deferred initiative input.

## Architecture

```text
FastAPI / Celery composition roots
-> ExternalServiceAdapterFactory[ArtifactStoreBootstrap]
-> PostgreSQL exact namespace claim
-> initialized ArtifactStore v2 byte capability
   -> LocalStorageAdapter       local and focused tests
   -> S3CompatibleArtifactStore MinIO integration; AWS S3 production
-> ArtifactService orchestration
-> PostgreSQL metadata, bindings, receipts, audit, and recovery
```

Only the artifact-storage orchestration service receives the writable
`ArtifactStore` capability. Guide, task, submission, checker, and review
modules receive typed ingest, read, or materialization operations so they
cannot bypass admission, receipts, verification, binding, or audit.

Those product capabilities are closed and operation-specific:

```text
GuideArtifactIngestPort
ContributorArtifactUploadPort
ArtifactBindingPort
ArtifactMaterializationPort
CheckerArtifactOutputPort
ArtifactOperatorReadPort
ArtifactOperatorRecoveryPort
```

Their requests contain canonical Workstream IDs and authorized byte sources,
never adapters, provider references, storage namespaces, caller-assembled quota
scopes, arbitrary resource types, or caller-selected content IDs. Composition
roots may construct `ArtifactStorageOrchestrator`, but cannot expose it as a
route dependency or Celery argument. Architecture tests inspect imports,
constructor annotations, dependency providers, and Celery parameters.

`ArtifactStore` exposes only immutable byte-provider behavior:

```text
put(source: CommittedArtifactSource)
observe_put_result(commitment: ArtifactCommitment)
open(provider_object_ref, optional_range)
head(provider_object_ref)
```

The v2 port has no provider `verify`, `retain`, `release`, delete, list, signed
URL, or provider receipt lookup. Workstream performs full verification through
`open`; PostgreSQL owns operation receipts and reference/lifecycle state.

## Provider Selection

`WORKSTREAM_ARTIFACT_STORE_BACKEND` is exactly
`disabled|local|s3_compatible`.

- `disabled`: no artifact runtime activation;
- `local`: local/development/test only;
- `s3_compatible`: one S3-protocol adapter. AWS S3 is the only v0.1 production
  provider; MinIO is the local and CI integration-test service. Every replica
  persists immutable provider profile and storage-namespace identity. A
  populated deployment cannot switch endpoint/provider without a separate
  verified migration and maintenance cutover.

The old `flow_node` value is removed without alias or fallback. Flow Node later
registers as a new provider only through its separately approved initiative.

One immutable deployment-level `ArtifactStorageNamespace` singleton records
backend, adapter, provider profile, canonical non-secret namespace descriptor,
and descriptor hash. Startup and every provider operation atomically
insert-or-validate it before I/O. A different concurrent first writer loses and
fails closed. A populated deployment changes namespace only through a reviewed
maintenance migration.

S3 settings are explicit and secret-safe: endpoint URL, provider-specific
region, bucket, private prefix, addressing style, credential mode, optional
local access-key/secret/session token, connect/read/write/pool timeout, total
verification deadline, and maximum stream buffer. AWS production credential
mode `aws_workload_identity` selects exactly one allowlisted method:
`assume-role-with-web-identity`, `container-role`, or `iam-role`. Workstream
constrains the pinned credential resolver to the selected provider before any
provider is loaded, verifies the resolved method, and rejects explicit
credentials, ambient access keys, file/process/login/SSO sources, legacy
EC2/Boto sources, and every unselected workload provider. For the selected
method, startup accepts only that method's exact closed `AWS_*` environment
allowlist and rejects every other `AWS_*` or `BOTOCORE_*` SDK control before
constructing a session. Chunk 02B1 pins
`aiobotocore==3.7.0` and `botocore==1.43.0`; SDK upgrades require an explicit
dependency and credential-behavior review. MinIO static credentials are
local/CI only. The endpoint is omitted for native AWS S3 and explicit for
MinIO. AWS requires an explicit region and production requires HTTPS, a
non-local resolved endpoint, and backend `s3_compatible`. Secrets and resolved
credentials are never persisted or retained by errors. Object and credential
metadata transports explicitly ignore ambient HTTP proxy variables. Cloudflare
R2 has no v0.1 runtime profile, credential service, or configuration path.

## Immutable Object Identity

Every untrusted or initially uncommitted byte source first crosses the bounded
`PreparedArtifact` boundary. Workstream hashes and counts the complete source,
compares any client commitment before provider I/O, and seals a
`CommittedArtifactSource` that only the preparation service can construct.
Production upload accepts only that sealed source. The object key is derived
only from its server-computed canonical `sha256:<64 lowercase hex>` digest:

```text
<private-prefix>/sha256/<hex[0:2]>/<hex[2:]>
```

It contains no actor, project, task, customer filename, media type, or secret.
Workstream stores the key only as an opaque provider object reference.

The S3 adapter uses one conditional no-overwrite `PutObject`. A precondition
failure triggers exact existing-object recovery; it never overwrites and never
assumes the existing bytes are correct. v0.1 rejects objects above 512 MiB
before I/O. Multipart is deferred until a separate contract proves its
conditional-completion and recovery semantics.

The AWS bucket policy independently denies `PutObject` when the
`If-None-Match` header is absent; S3 requires a present value of `*` for this
operation. Live proof attempts an unconditional overwrite with the runtime
role, requires denial, and verifies that the original bytes remain unchanged.
This protects immutability even if adapter code omits its condition.

Runtime credentials are restricted to the dedicated Workstream artifact bucket
and completed-object prefix. They allow put/get on the object ARN and
`s3:ListBucket` on the bucket ARN only so a missing `HeadObject` returns 404
rather than an ambiguous 403. The port exposes no list method and Workstream
never calls a list API. Delete, copy, bucket administration, lifecycle, and
public-access mutation are denied. Production release separately proves AWS
Block Public Access/policy/ACL state plus anonymous-read denial against a known
object. A separate read-only
deployment identity inspects provider lifecycle configuration and blocks
activation when an enabled AWS expiration or noncurrent-version-expiration rule
can match the completed-object prefix.

The canonical specification locks the exact IAM manifest: runtime allows only
`s3:PutObject` and `s3:GetObject` on the completed-object ARN plus
`s3:ListBucket` on the dedicated bucket ARN for trustworthy absence
classification; readiness allows
only the named bucket/IAM/Access Analyzer read/check actions on the named
bucket, runtime role, runtime policy, or required `*` policy-check resource;
negative allows no S3/IAM/Analyzer action. The bucket policy has exact insecure-
transport, non-runtime-object, and missing-conditional-header deny statements.
Bootstrap authority is environment-owned and never supplied to Workstream or a
probe. Chunk 07 rejects every extra allow action, resource, inline/attached
policy, or bucket-policy exception.

AWS configuration added in 02B1 is not production-instantiable. Chunk 07 runs
three non-interchangeable proof executors: readiness under its OIDC role,
runtime immutability inside the actual workload identity, and negative access
under an independent OIDC role. Each writes an append-only
`ArtifactProviderProbeResult` bound to its STS-observed caller ARN, expected
ARN, release, namespace fingerprint, policy digest, common nonce, proof
version, database times, expiry, result, and evidence digest. No executor can
assume another proof identity.

A credential-free coordinator with database authority creates
`ArtifactProviderActivation` only from one matching unexpired pass result of
each type plus bootstrap-principal policy evaluation. Production startup and
every AWS I/O require an exact unexpired activation. Proof validity is at most
15 minutes and the three probes/coordinator run every 5 minutes; expiry or
configuration/policy drift fails before provider I/O with
`artifact_provider_live_proof_required`. Authorized infrastructure
administrators are trusted within that bounded window. S3 Object Lock is not a
v0.1 requirement and would require a separate human-approved decision.
Every call also requires enough remaining activation TTL for its total
operation deadline plus persistence and clock margins. The terminal transaction
rechecks the same activation; expiry after an ambiguous put preserves the
durable acknowledgement-unknown attempt rather than committing a terminal fact.

## Ingest Transactions

1. Authorization Service permits the exact upload action/resource.
2. Workstream prepares the complete untrusted source in bounded private scratch,
   computes digest and size, and rejects a mismatched client commitment before
   provider I/O.
3. PostgreSQL atomically reserves unique-byte charges at every applicable task,
   producer, project, and deployment scope. Contributor upload-session slots
   are a separate 04A reservation. Any exceeded scope fails before provider
   I/O. Provisional and completed byte charges count; exact replay and
   concurrent same-content reservations cannot double-charge or oversubscribe.
   Product callers do not assemble this set; artifact orchestration derives it
   from authoritative actor/service, project, task, upload-session or
   checker-run, and deployment records. A missing required relationship fails
   before provider I/O.
4. Transaction A reserves the upload item and commits the server-computed
   digest, size, media type, operation identity, request digest, and CAS values.
5. Workstream passes the sealed `CommittedArtifactSource` to the injected
   adapter outside the transaction.
6. Transaction A also persists an `ArtifactPutAttempt` before I/O. A claimed
   attempt records executor, database-clock lease, and execution generation;
   the adapter conditionally stores under the content-addressed key or resolves
   an exact replay candidate.
7. Transaction B records provider acknowledgement, completes the provisional
   admission charges, sets the item to `stored_pending_verification`, and
   creates the replica with pending verification and unknown
   availability/integrity; no binding exists.
8. A durable verification job is committed in PostgreSQL and published to
   Celery after commit. A periodic scanner republishes pending work within the
   configured SLA.
9. Celery opens the complete object, computes SHA-256 and size, and atomically
   records a verification receipt. Only a matching object becomes `ready` and
   bindable. Missing or changed bytes become unavailable/quarantined.

Provider acknowledgement loss keeps the durable put attempt and admission
charges provisional. A PostgreSQL scanner publishes ambiguous and expired
in-flight attempts; a fixed service principal runs read-only
`observe_put_result` plus a complete hash. Matching bytes complete Transaction B
once, authoritative absence releases charges and makes the item
`replay_required`, and mismatched bytes quarantine the key. No background
resolver repeats a provider write. Exact replay after absence must atomically
reacquire capacity before another provider call.
Workstream never stores upload bytes in Postgres, Redis, or Celery payloads.

Before binding, an object confirmed missing returns its reserved upload item to
`replay_required`, and only the original authorized uploader may replay the
same bytes under the same operation identity. That pre-binding replay resets
the same replica from `missing/unavailable/unknown` to
`pending/unknown/unknown`, appends a receipt, and creates a new verification
job. After binding, a missing object
is a terminal artifact incident in v0.1: the immutable binding remains, the
product lifecycle stays blocked without blaming the contributor, and no route
replaces or rebinds the bytes. A digest/size mismatch on an existing key is
also unrecoverable in v0.1 and becomes a security incident; Workstream never
overwrites that key.

Contributor uploads, authorized caller-supplied guide bytes, and generated
checker logs/outputs
all use the same bounded two-pass `PreparedArtifact` scratch boundary. The first
pass uses private ephemeral local scratch to hash/count; the second pass exposes
a sealed `CommittedArtifactSource` to ArtifactStore. No caller can pass an
arbitrary expected digest beside an arbitrary stream. Scratch is never
authoritative and is not persisted in product records. A cross-process
reservation ledger reserves the full 512 MiB maximum per active preparation
and enforces aggregate bytes/files/concurrency plus a minimum-free-space floor
within a dedicated volume quota. Preparation plus upload has a fixed total
deadline shorter than reservation TTL; there is no heartbeat. One periodic
Celery Beat task removes only expired entries while holding the ledger lock;
the API process performs the same idempotent cleanup once at startup. Chunk
02A2 builds these cleanup mechanics without activating them, and Chunk 02A3
owns both activation points. After
ambiguous completion, recovery checks the
provider first. Regenerated identical bytes may replay the original operation;
changed or non-reproducible bytes fail/abandon it and require a new source
snapshot/setup generation or checker-run attempt.

## v0.1 Retention And Deletion

Completed objects are retained indefinitely in v0.1. PostgreSQL tracks active
bindings and logical release eligibility, but no runtime path calls
`DeleteObject`, configures provider lifecycle deletion, or exposes a delete API.
The production bucket must not have an automatic deletion rule for the
Workstream prefix.

Retention is paired with durable admission control installed in Chunk 02C1
before any product ingest cutover. PostgreSQL bounds cumulative unique
provisional and completed bytes for every applicable task, producer, project,
and deployment. Charges use canonical content identity to avoid double-charging
exact deduplicated replay within one scope. Cancellation, expiry, absence of a
binding, quarantine, and integrity mismatch do not release completed-byte
charges. Only fresh authoritative absence releases a provisional charge;
replay must reacquire it atomically.

Physical deletion, garbage collection, legal hold, and retention windows are a
later explicit initiative. This removes destructive storage behavior from the
first production cutover.

## Server-Generated Artifact Set

The server seals an upload session before authoritative pre-submit execution.
Trusted inspection derives normalized display names, logical roles, media
types, archive members, path safety, individual sizes, total size, and
Workstream SHA-256 values. Canonical ordering and JSON produce
`artifact_set_hash`.

The pre-submit admission record binds actor, task, sealed session, artifact-set
hash, locked guide/policy/checker context, result, expiry, and canonical
submission input hash. Submission creation row-locks and consumes that exact
admission and session. No checked-versus-submitted byte swap is possible.

Pre-submit artifact reads use a bounded Workstream-owned transient retry budget.
If it is exhausted, the API returns HTTP 503 with
`pre_submission_infrastructure_unavailable`; this is neither a checker failure
nor a product review decision. The exact precheck attempt, sealed upload
session, and artifact set remain unconsumed and reusable until normal expiry.
Only infrastructure-attempt and audit facts are written. Idempotency binds
actor, task, session/artifact set, locked context, client key, and canonical
request digest: exact replay continues or returns the same attempt, changed
replay conflicts, and concurrent replay creates no duplicate. After retry-after
or infrastructure recovery, the contributor continues the same exact attempt
without Project Manager or Operator approval.

## Durable Verification And Recovery

Background jobs have exactly one operation class:

| Class | Action | Provider mutation | Terminal outcomes |
|---|---|---:|---|
| `provider_observation` | fresh complete-object read and hash | none | `verified`, `missing`, `integrity_mismatch`, `provider_unavailable` |

No v0.1 recovery path performs generic PostgreSQL repair, provider mutation
replay, retain, release, delete, or destructive requeue. Contradictory records
produce terminal `conflict` and an incident.

An Operator recovery request:

1. verifies that the target is a terminal `provider_unavailable` job whose
   automatic attempt budget is exhausted, then obtains a fresh exact
   Authorization Service decision;
2. atomically creates one reason/idempotency-bound recovery envelope, one retry
   verification job, and initiation audit;
3. returns `202` after commit with the attempt, source-job, and retry-job IDs and no
   provider I/O;
4. publishes the verification job to Celery best effort;
5. relies on the periodic PostgreSQL scanner to republish a pending job or one
   whose execution lease expired.

Pending, running, verified, missing, integrity-mismatch, conflict, and
non-exhausted provider-unavailable jobs are not Operator-retryable and produce
no attempt, new job, or initiation-success audit.

Celery executes under one fixed system principal and a fresh service-principal
authorization decision. The verification job is the sole executable item.
PostgreSQL coordinates invocations using a fresh
`artifact_verification_executor_id`, database-clock lease expiry, and
incremented execution generation. Terminal verification, recovery-envelope
result, and terminal audit commit in one fenced transaction. A stale executor
updates zero rows and writes no terminal facts.

Put-attempt resolution follows the same rule. Both worker classes revalidate
the current fixed service actor, identity link, exact action/resource,
executor, and generation inside the same transaction as terminal state,
receipt/replica/attempt, recovery, and audit writes. Revocation, suspension,
resource drift, or stale execution updates zero rows and writes no terminal
fact.

AUTH-07 registers the closed artifact permissions, AUTH-08 defines applicable
Operator grants, AUTH-09A defines the static service-action matrix, AUTH-09B
provisions fixed service ActorProfiles and ActorIdentityLinks, and AUTH-09E
admits them at runtime. `WS-AUTH-001-ART-CUSTODY` transfers every current ART
action to the exact AUTH activation custodian without changing mappings or
availability. The owning WS-ART chunk then supplies hidden canonical resource
composition, guards, surface declarations, behavior, and tests while the real
kernel fails closed; the named AUTH activation chunk finally integrates the
evaluator and alone changes availability to active. Later AUTH-12, AUTH-14, and
AUTH-15 are not alternate artifact activation paths.

Complete reads have an end-to-end verification deadline derived from the 512
MiB maximum and minimum supported throughput. The deadline is shorter than the
execution lease by a persistence margin and applies even while bytes continue
arriving. v0.1 uses no heartbeat.

The recovery attempt stores `source_verification_job_id`,
`retry_verification_job_id`, `client_idempotency_key`, and a canonical request
digest. Idempotency scope is requester, source job, recovery class, and key.
An exact replay returns the original attempt and both job IDs; a changed request
under that key conflicts without side effects. Every source job has at most one
recovery attempt for its lifetime, so a new key cannot reuse an ancestor after
success or failure. The GET resolves scope through
the source job/content and returns both immutable source status and current
retry-job status. If that retry job later exhausts `provider_unavailable`, a
new recovery attempt may name it as the next source job, preserving the chain.

## Exact Operator Surfaces

```text
GET  /api/v1/operator/artifacts/bindings?resource_type={type}&resource_id={id}
GET  /api/v1/operator/artifacts/contents/{content_id}/replicas
GET  /api/v1/operator/artifacts/replicas/{replica_id}/receipts
GET  /api/v1/operator/artifacts/verification-jobs/{job_id}
POST /api/v1/operator/artifacts/verification-jobs/{job_id}/retry
GET  /api/v1/operator/artifacts/recovery-attempts/{attempt_id}
GET  /api/v1/operator/artifacts/audit-events
```

Every route has a distinct named Authorization Service action/resource
contract, bounded projection, stable pagination where applicable, and concealed
cross-resource denial. No route returns bucket, endpoint, object key,
credentials, raw provider error, or customer bytes.

The binding lookup is the Operator discovery entry point from a known project,
guide, task, submission, checker run, or future review resource. It returns
stable Workstream content, replica, and current-job IDs. Audit listing supports
exact resource/content/job/attempt filters.

## Product Cutover

1. Guide source capture stores exact bytes and binds the immutable source
   snapshot to content.
2. Task-scoped upload sessions accept contributor artifacts and seal one exact
   server artifact set.
3. Authoritative pre-submit executes against sealed verified bytes.
   One authorized artifact materializer allocates through the canonical scratch
   manager, recomputes every digest and byte count from the provider read, seals
   the verified workspace read-only, and is reused unchanged by post-submit.
4. Submission creation consumes the same admission and creates immutable
   bindings; contributor finalization is not a manager action.
5. Post-submit dispatch reads the same content commitment and stores checker
   inputs, logs, and outputs as artifacts.
6. Review packet/evidence integration remains WS-REV, but it consumes the same
   `ArtifactBinding` model.

The existing misleading `/submissions/{id}/finalize` endpoint is not retained
as a normal handoff. Its genuine exceptional behavior moves to
`POST /api/v1/operator/submissions/{id}/pre-review-gate-repair`, with exact
authorization, reason, audit, and no effect on already healthy automatic runs.

Route transitions are proved per exact application image. Public rollout is
blocked until every serving instance runs the compatible image or an external
fleet activation barrier exists; application tests do not claim rolling-fleet
atomicity.

## Migration Rules

- Migration `0025` refuses populated v1 artifact tables before DDL and preserves
  the prior schema and rows. Pre-production reprovisioning happens out of band
  into an empty database/storage namespace, followed by v2 reingest from
  authoritative bytes; unavailable bytes are not fabricated or migrated.
- `flow_node` configuration is rejected after the clean-cut settings migration.
- ArtifactStore v1 methods are removed in the same chunk that migrates all
  LocalStorage callers and tests.
- No compatibility model, alias, nullable shadow column, dual write, dual
  factory, or fallback adapter remains.
- Every migration proves fresh upgrade, prior-head upgrade, populated-state
  preservation or explicit refusal, empty downgrade/re-upgrade, and no byte
  storage in PostgreSQL.

## Verification Strategy

- LocalStorage and MinIO run one ArtifactStore v2 conformance suite.
- Testcontainers or CI service containers use real S3 API calls; provider
  behavior is not monkeypatched for integration proof.
- AWS S3 readiness uses a live private-bucket smoke proof with workload identity
  and no committed credentials. MinIO conformance does not activate AWS.
- Concurrent conditional put, acknowledgement loss, oversized-object refusal,
  truncation, changed bytes, missing object, range read, timeout, throttle,
  broker failure, periodic republish, duplicate Celery delivery, expired lease,
  stale finalization, and cross-resource authorization all have tests.
- New or changed backend subsystems remain at least 90 percent covered; the
  repository baseline cannot decrease.
- The 15 implementation chunk contracts define one ordered deterministic
  coverage table. Backend CI first runs the one exact full-suite
  `--cov=app --cov-report=term-missing --cov-fail-under=78` command. Stable,
  dedicated `coverage report --include=... --fail-under=90` steps then enforce
  90 percent separately for every accumulated changed subsystem using that full
  suite's coverage data. A chunk preserves prior subsystem reports and adds or
  changes only reports for newly owned surfaces; it never freezes a partial
  test list for a package that later expands. Independently executable
  services/examples have their own exact test-and-coverage steps.
- The active artifact implementation coverage phase advances only after
  `scripts/test_agent_gates.py` proves each expected step occurs exactly once in
  the backend `test` job, after the full-suite test step, without job/step
  conditions, `continue-on-error`, shell overrides, hidden step environment, or
  working-directory drift. Raw text or source-set matching is insufficient.
- Final proof uses real HTTP APIs and visible job/recovery endpoints, not direct
  database inspection.

## Deferred Flow Node Adapter

`FN-ART-002` preserves a complete future plan for a focused Flow Node artifact
provider and Workstream adapter. It starts only after the S3-compatible v0.1 is
proven and the user explicitly approves that initiative. It must implement the same
ArtifactStore v2 conformance contract and use an explicit maintenance cutover;
it may not add a dual-runtime fallback to v0.1.

## Deferred R2 Adapter

Cloudflare R2 is outside the v0.1 dependency graph. A later initiative must
perform current provider discovery, satisfy the same ArtifactStore v2
conformance contract, and define an explicit no-fallback maintenance cutover.
No R2 credential issuer, sidecar, runtime profile, or deployment proof belongs
to this initiative.

Before the product cutovers, guide-source validation, task schemas,
project-policy schemas, checker messages, the API drill, tests, and the
submission-artifact-policy template still expose legacy caller provider
declarations that have no active v0.1 provider meaning. Chunk 03 removes direct
provider schemes from guide-source identity. Chunk 05 deletes the remaining
caller transport as part of the submission binding clean cut. Later code must
not preserve an alias, fallback, or compatibility parser.
