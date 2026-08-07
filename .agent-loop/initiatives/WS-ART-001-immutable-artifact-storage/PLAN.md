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
SubmissionBundlePreparationPort
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
   producer, project, and deployment scope. For contributor submissions this
   durable reservation occurs only after all scratch-bound pre-submit gates
   pass. Any exceeded scope fails before provider I/O. Provisional and
   completed byte charges count; exact replay and
   concurrent same-content reservations cannot double-charge or oversubscribe.
   Product callers do not assemble this set; artifact orchestration derives it
   from authoritative actor/service, project, task, submission-bundle operation or
   checker-run, and deployment records. A missing required relationship fails
   before provider I/O.
4. Transaction A reserves the producer-specific admission and commits the server-computed
   digest, size, media type, operation identity, request digest, and CAS values.
5. Workstream passes the sealed `CommittedArtifactSource` to the injected
   adapter outside the transaction.
6. Transaction A also persists an `ArtifactPutAttempt` before I/O. A claimed
   attempt records executor, database-clock lease, and execution generation;
   the adapter conditionally stores under the content-addressed key or resolves
   an exact replay candidate.
7. Transaction B records provider acknowledgement, completes the provisional
   admission charges, sets the `ArtifactPutAttempt` to `object_confirmed`, and
   creates the replica with pending verification and unknown
   availability/integrity. No binding exists.
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
once, authoritative absence releases charges and moves the put attempt to
`absent_replay_required`. Mismatched bytes quarantine the key. No background
resolver repeats a provider write. Exact replay after absence must atomically
reacquire capacity before another provider call.
Workstream never stores upload bytes in Postgres, Redis, or Celery payloads.

Before binding, an object confirmed missing returns its reserved put attempt to
`absent_replay_required`, and only the original authorized producer may replay the
same bytes under the same operation identity. That pre-binding replay resets
the same replica from `missing/unavailable/unknown` to
`pending/unknown/unknown`, appends a receipt, and creates a new verification
job. After binding, a missing object
is a terminal artifact incident in v0.1: the immutable binding remains, the
product lifecycle stays blocked without blaming the contributor, and no route
replaces or rebinds the bytes. A digest/size mismatch on an existing key is
also unrecoverable in v0.1 and becomes a security incident; Workstream never
overwrites that key.

Contributor submission ZIPs, authorized caller-supplied guide bytes, and
generated checker logs/outputs all use the same bounded two-pass
`PreparedArtifact` scratch boundary. The first
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

## Server-Generated Submission Bundle Identity

Every Submission version has exactly one outer ZIP. Workstream keeps that ZIP
only in bounded private scratch while it walks the complete normalized
file/directory tree, enforces archive-safety/resource limits, hashes each file,
and derives two identities:

```text
archive identity  = SHA-256 and byte count of the exact outer ZIP
semantic identity = canonical hash of normalized path, entry type,
                    file SHA-256, file byte count, and normalized executable flag
```

ZIP timestamps, compression settings, comments, ownership, group, read/write
bits, special bits, and other platform permission metadata do not change
semantic identity. Executable intent is the sole permission-derived semantic:
for a regular entry created with valid Unix mode metadata it is true when any
execute bit is present; otherwise it is false. Directories have no executable
field. Explicit empty directories
and synthetic parents use one documented canonical representation. Symlinks and
special entries are rejected. Canonical paths use `/` separators, contain only
relative non-empty segments, and normalize Unicode to NFC. The identity remains
case-sensitive, but Workstream rejects exact duplicates, NFC collisions, and
Unicode case-fold collisions so the checked tree cannot vary by filesystem.
Collision detection completes before an entry enters the manifest, any project
precheck or materializer observes the tree, or provider I/O starts. A ZIP entry
within the outer archive is opaque in v0.1; recursive inspection means walking
the outer archive tree, not opening nested archives. A later capability requires
separate cumulative safety proof.

Both identities are compared with the immediate prior immutable `Submission`.
Exact archive equality or semantic equality rejects before checker and provider
I/O. One ordered pre-submission execution then consumes the same read-only
scratch tree. It is assembled from a central, versioned Workstream checker
catalogue:

```text
non-bypassable artifact-custody gates
+ Workstream default submission-policy checks
+ task-locked Project Guide checks
= one effective pre-submission execution plan and one result envelope
```

The catalogue is the sole registry for stable checker identifiers, versions,
phase/order, dependencies, owner, input capability, severity class, default
availability, disabled behavior, resource limits, stable outcomes, and policy
trace. Runtime services may dispatch through typed adapters, but may not grow a
second checker registry or scattered name-based conditionals.

Every catalogue entry has explicit `enabled|disabled` operational state. A
disabled mandatory security, integrity, or contributor-accountability entry
makes preparation fail closed as platform infrastructure unavailable; it is
never recorded as skipped-and-passing. A disabled advisory entry is omitted
from execution only through startup-validated, versioned deployment
configuration and is recorded in the bounded result manifest. Contributors,
Project Managers, task parameters, and project policy cannot toggle catalogue
availability or weaken a mandatory default. Project policy may narrow platform
limits but cannot raise them. Only a completed checker result may create bounded
structured contributor findings. Infrastructure failure, disabled mandatory
checks, resource exhaustion, cancellation, and authorization failure produce a
stable retryable infrastructure outcome with no contributor finding, durable
artifact, Submission, or review state; scratch is destroyed.

A passing result stays bound to the same process-local scratch generation and is
consumed immediately by the normal durable admission path. It is never a
provider object or reusable candidate. Process/scratch loss requires reupload.
The durable path writes the outer ZIP once, independently reads it completely,
and publishes a bindable admission only after the observed archive identity
matches. Existing put-attempt, observation, verification, receipt, scanner, and
recovery behavior resolves ambiguity. No candidate namespace, promotion copy,
retention window, physical deletion, or second recovery aggregate exists.

### Verified Submission-Bundle Admission

Verification publishes an immutable, capacity-charged
`SubmissionBundleAdmission` in `ready`. It binds the preparing actor and
identity-link provenance, project, task, assignment, immediate predecessor,
exact locked task/guide/policy context, verified `ArtifactContent`, semantic
manifest, and immutable pre-submit evidence set. Client abandonment is an
accepted quota-bounded v0.1 outcome: a `ready` admission may remain unbound
without creating a Submission, review, contribution, compensation, or
reputation effect.

The only transitions are `ready -> consumed` and `ready -> stale`.
Consumption occurs in the same transaction that creates the immutable
Submission and binding, and database uniqueness permits one consuming
Submission. Proven task closure, predecessor advancement, or locked-context
replacement makes a still-ready admission `stale` during a consumption attempt.
Authority loss alone does not make it stale; every attempt obtains fresh AUTH
authority, and restored authority may consume a still-compatible admission.
`consumed` and `stale` are terminal. No state expires, releases capacity, or
authorizes provider deletion. Ready, stale, and consumed admissions continue to
count against existing completed-byte scopes. Existing Operator admission-usage
projections add bounded unbound-ready and stale counts/bytes without exposing
content or provider identities.

Exact preparation replay returns the original admission without another put,
charge, evidence set, or admission. Uniqueness and status/terminal-field check
constraints enforce the lifecycle; the Submission owns a unique admission
reference as the second database fence.

### Durable Authorization Boundaries

The contributor request is authorized before scratch intake. Immediately before
durable capacity reservation and `ArtifactPutAttempt` creation, 04C opens the
owning transaction and consumes AUTH's transaction-local prepared capability.
AUTH—not ART—reloads and validates the current ActorProfile, exact identity link,
project authority, assignment, action availability, and canonical resource
facts. TASK/PROJECT owners lock task, predecessor, and locked context through
their typed capabilities. Authorization evidence, capacity reservation, and put
intent commit atomically; failure means no provider I/O and scratch cleanup.

Durable put intent creates a technical recovery obligation that later human
revocation does not cancel. Verification may finish, but binding remains
impossible until 05 obtains fresh human `submission.create` authority and fresh
fixed-service ActionId `artifact.submission.binding.create` authority, mapped
to PermissionId `artifact.binding.create`. 05 consumes both prepared
capabilities in the single task transaction that locks the admission/context,
creates Submission and binding, and marks the admission consumed. Denial,
cancellation, stale execution, or persistence failure rolls back every protected
effect. After authority succeeds, proven task closure, predecessor advancement,
or locked-context replacement may instead commit only the terminal stale
transition and bounded evidence, with no Submission or binding. ART/TASK never
imports or locks AUTH-owned tables.

The submission producer is not encoded only in generic put-attempt columns or
an opaque request digest. Before provider I/O, 04C1 persists one immutable,
foreign-keyed durable intent joining the exact passing pre-submit evidence set
to the generic put attempt. That intent preserves the actor and identity link,
project, task, assignment, predecessor identity/version, locked guide/snapshot/
policy lineage, semantic manifest, archive commitment, effective plan, and
storage scheme needed for database-only 04C2 publication after process loss.
Neither scratch state nor a process-local capability is durable lineage, and
04C2 never reconstructs facts by parsing a request digest.

The normal path consumes a live `PreSubmitPassCapability` and the exact
`PreparedArtifact` immediately. If the process terminates after immutable passing
evidence commits but before the durable intent transaction, recovery requires a
complete fresh upload and checker execution with a new prepared generation,
evidence identity, and immediate pass capability. An old durable evidence row
never mints or remints process-local authority. Database uniqueness fences
concurrent continuation of each live generation to one intent, one capacity
effect, and one logical provider operation; content-addressed capacity and
provider storage continue deduplicating identical bytes across later complete
reuploads.

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

### Guide Materialization And Extraction Boundary

ART-03A upload remains a byte-custody request: authorize before intake, compute
the server digest and size, admit once, store opaque bytes, and verify them. It
does not parse content or wait for contributor submission checkers.

The expanded ART-03B work is delivered as eleven hidden PR-sized subchunks before
AUTH-04B activates fixed-service binding/read:

1. `03B1` creates an authoritative one-item/one-content guide binding tied to
   the exact setup run and explicit setup generation. Item metadata cannot
   assert content identity, and replaced or cross-lineage facts fail closed.
2. `03B2` performs fresh authorized full reads through `ArtifactStore`, writes
   only through `ArtifactScratchManager`, recomputes digest/size, records ART
   incidents, and classifies formats using signatures and bounded container
   markers.
3. `03B3A` installs the isolated no-network extraction framework, immutable
   content/usage provenance, and text, Markdown, JSON, and CSV extractors
   without new parser dependencies.
4. `03B3B1` selects the exact pinned parser dependency allowlist and adds its
   deterministic CI gate without changing packages or runtime code.
5. `03B3B2` installs only the approved PDF dependency and adds PDF extraction.
6. `03B3B3A` adds shared bounded OOXML container and security capabilities.
7. `03B3B3B`, `03B3B3C`, and `03B3B3D` separately add DOCX, PPTX, and XLSX.
8. `03B3B4` installs only the approved image dependency and adds PNG, JPEG, and
   WebP structural metadata extraction without OCR.
9. `03B4` adds `setup_generation` to the identifier-only Celery payload,
   reloads current state, assembles all required canonical extracted sources,
   invokes sufficiency, and persists exact provenance.

The canonical extraction status set is:

```text
extracted | unsupported | ambiguous | malformed | limit_exceeded |
parser_failure | cancelled | artifact_incident
```

Only `extracted` records enter agent input. Truncation or omission is explicit
and may be allowed only by the versioned extraction policy; required missing
semantics stop setup internally. Artifact incidents never become sufficiency
findings.

Stable setup mappings are exact:

| Extraction status | Redacted setup code | Recovery/remediation |
|---|---|---|
| `extracted` | none | Continue only when every required item is complete. |
| `unsupported` | `guide_source_format_unsupported` | Project Manager supplies a supported item in a new snapshot. |
| `ambiguous` | `guide_source_format_ambiguous` | Project Manager supplies an unambiguous item in a new snapshot. |
| `malformed` | `guide_source_malformed` | Project Manager supplies a corrected item in a new snapshot. |
| `limit_exceeded` | `guide_source_limit_exceeded` | Project Manager supplies a smaller/simpler item; limits are not raised inline. |
| `parser_failure` | `guide_source_extraction_failed` | Bounded automatic retry; after exhaustion, PM replaces the item and Operator may inspect redacted diagnostics. |
| `cancelled` | `guide_source_extraction_cancelled` | Current-generation transient cancellation may retry; stale-generation cancellation commits no report. |
| `artifact_incident` | `guide_artifact_incident` | Recoverable custody failure waits for ART recovery; terminal corruption requires a new item/snapshot. |

The configured 60-second timeout and 512-MiB address-space termination are
`limit_exceeded`, are not automatically retried, and require a smaller/simpler
item in a new snapshot. Executor loss before a classified limit breach is
`parser_failure`: it receives one bounded current-generation retry from fresh
materialization and fresh authority; repeated loss exposes only
`guide_source_extraction_failed` plus bounded redacted Operator diagnostics and
requires a corrected/new snapshot. No failed attempt creates a successful usage
record or report.

Guide-source items are not required to be ZIP files. The initial semantic
extractors are PDF, DOCX, PPTX, CSV, XLSX, Markdown, plain text, JSON, and
PNG, JPEG, and WebP metadata. Images are accepted and classified, but without
OCR their pixels cannot satisfy required textual guide semantics. Audio/video
and opaque/ordinary ZIP input are unsupported in v0.1. ZIP-
container classification rejects macros, external relationships, embedded
executables, ambiguous markers, excessive entries, decompressed bytes, depth,
or compression ratio before a document parser runs.

v0.1 stores bounded canonical extraction JSON/text in PostgreSQL rather than
creating an unapproved provider write under guide-read authority. It records
source digest/size, detected format, extractor and version, extraction-policy
version, output digest, truncation/omission facts, status, and bounded error
code. A separate immutable usage record binds that result to the exact binding,
source item, setup run, and generation. Original bytes remain authoritative. A
later derived-artifact store path requires a distinct AUTH action.

The existing `ProjectSetupRun.status=setup_blocked` remains the public state for
every terminal current-generation failure above. API, Operator, and Project
Manager projections use only the exact redacted mapping and remediation table.
None is a guide-insufficiency decision.

Any production parser dependency requires explicit human approval through 03B3B1. Candidate
libraries must undergo current security, maintenance, license, transitive-
dependency, malformed-input, and cancellation review before a later format chunk may add
them; no runtime plugin discovery or parser fallback is permitted.

1. Guide-source delivery is split into hidden byte ingest, AUTH activation,
   verified snapshot binding/materialization, AUTH activation, and the legacy
   identity/continuation clean cut.
2. Contributor intake accepts one outer ZIP, inspects and manifests its complete
   tree in bounded private scratch, and rejects exact or semantic unchanged work.
3. The central Workstream checker catalogue composes mandatory platform gates,
   Workstream default submission-policy checks, and locked Project Guide checks
   into one ordered effective execution against that same scratch tree. Failure
   produces no durable bytes.
4. Passing bytes enter the existing immutable store once. Complete read-back
   verification publishes one bindable admission; ambiguity uses existing ART
   recovery.
5. Submission creation consumes that exact admission and creates one immutable
   `Submission` version and binding; contributor finalization is not a manager
   action and no competing `SubmissionVersion` table is introduced.
6. Post-submit dispatch materializes the same binding, recomputes integrity, and
   stores checker logs/outputs as separately bound artifacts.
7. Review packet/evidence integration remains WS-REV. REV attaches a decision
   (`accept`, `needs_revision`, or `reject`) and note/findings to the exact
   Submission; the reviewer uploads no revision artifact.
8. A contributor response to `needs_revision` is another complete ZIP and
   immutable Submission linked to the prior Submission and exact Review.
9. CON and future delivery own their lifecycle records but reference the same
   accepted Submission/binding. Full-byte streams recompute SHA-256 and byte
   count and fail closed on mismatch.

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
- New or materially changed backend subsystems remain at least 90 percent covered; the
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
- A narrow composition change in a subsystem that the chunk does not materially
  own does not create a new whole-subsystem gate over inherited code. Its new
  behavior must instead be exercised by focused tests and the repository
  baseline, while the owning subsystem's files retain their 90 percent gate.
  For 03A, the hidden project route, response schema, and staging relation are
  narrow ART composition surfaces exercised by guide-ingest tests and repository
  coverage; ART-owned files remain enforced by the ART foundation gate. Merged
  AUTH 11B's broader projects package remains outside
  03A and measured 71.54 percent when the proposed whole-project gate first ran.
  A later chunk that materially owns projects must close that debt before adding
  the projects 90 percent report; 03A may not claim or bypass such a report.
- When a chunk adds a newly owned coverage report, the active artifact
  implementation phase advances only after
  `scripts/test_lightweight_agent_gates.py` proves that command and step name
  occur exactly once in the backend workflow. 03A adds no new coverage report;
  hosted CI remains the authoritative proof that its retained repository, ART,
  and pre-existing subsystem gates execute without bypass configuration.
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

## 2026-08-02 Remaining v0.1 Execution Amendment

This section supersedes the earlier unsplit future-chunk sequence. It does not
change the merged foundation or guide extraction design.

```text
AUTH-04B implementation/activation [merged PR #245]
-> ART-03C guide verified-pipeline clean cut
-> ART-04A1 legacy contributor-intake removal
-> ART-04A2 bounded outer-ZIP safety/intake
-> ART-04A3 semantic manifest + unchanged-work gate
-> PLAN5 legacy-precheck clean-cut resequencing
-> ART-04B1 default-checker catalogue and effective-plan contract
-> ART-04B2 sealed scratch materialization and platform-default execution
-> ART-04B3 locked-project execution and immutable bounded evidence
-> XINT-06A pre-submit materializer activation
-> ART-04C1 durable intent + one provider write
-> ART-04C2 verified ready-admission publication
-> XINT-05A contributor preparation activation
-> ART-05A atomic Submission/binding/admission consumption
-> XINT-05B Submission/binding activation
-> ART-05B admission-backed Submission/API/dispatch cutover plus complete legacy precheck removal
-> ART-06A post-submit checker snapshot/materialization
-> ART-06B checker output binding and routing
-> XINT-06B post-submit/output activation
-> ART-07A lease-scoped reviewer packet materialization
-> XINT-07A reviewer packet activation only
-> ART-07B accepted-contribution artifact identity handoff
-> ART-08A Local/MinIO real API lifecycle proof
-> ART-08B AWS production-readiness/activation proof
-> XINT-08 + ART-08C final v0.1 conformance
```

04A1-04C2, including split 04B1-04B3, remain hidden internal pieces of one
continuous contributor request.
No intermediate HTTP route, durable upload session, scratch handle, local path,
or prepared authorization crosses those PR boundaries. 04C2 alone composes the
hidden endpoint after every internal dependency exists.

PLAN5 supersedes the former early 04A4 removal. The legacy standalone precheck
route and its internal `TaskService.create_submission` safety guard remain
temporary legacy behavior only until the verified-admission Submission path is
ready. They receive no new features or compatibility adapters. ART-05B then
deletes the route, public schemas/service entry point, internal guard, and
caller-owned package/hash/manifest contract in the same clean-cut transaction
and API migration that makes admission consumption authoritative. There is no
interval in which unchecked legacy Submission creation is reachable.

XINT-06 must split because live preparation requires the fixed pre-submit
materializer before XINT-05A can safely activate the human preparation action.
The later 06B activation owns only post-submit materialization plus checker
output write/binding. This removes the previous dependency cycle.

Reviewer packet materialization is an ART byte-custody capability consumed by
REV under an exact active lease. ART creates no review aggregate or decision.
Reviewer evidence upload/binding is not required by the approved v0.1 reviewer
workflow and remains unavailable. CON records the accepted Submission and ART
identity without provider I/O. Client delivery is explicitly deferred.
