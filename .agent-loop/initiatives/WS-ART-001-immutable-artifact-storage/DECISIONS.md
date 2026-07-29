# Decisions: WS-ART-001 S3-Compatible Object Storage Amendment

## D1 - v0.1 Provider

AWS S3 is the only v0.1 production provider through
`S3CompatibleArtifactStore`. Every replica persists immutable provider profile
and storage namespace; a populated deployment changes provider only through a
separate verified maintenance migration. MinIO proves the S3 protocol locally
and in CI. AWS S3 becomes production-eligible only after private-bucket,
least-privilege, lifecycle, and anonymous-read-negative live proof.
LocalStorage remains a development/test adapter. Cloudflare R2 and Flow Node
are deferred and have no active runtime configuration or implementation chunk.

## D2 - Provider Boundary

The provider stores immutable bytes only. Workstream/PostgreSQL owns content
identity, bindings, references, lifecycle, receipts, audit, idempotency,
authorization evidence, and recovery state.

## D3 - ArtifactStore v2

ArtifactStore v2 accepts only a server-sealed `CommittedArtifactSource`, plus
read-only committed-put observation, open/range, and head. v1 provider
verify/retain/release/receipt methods are removed without compatibility aliases.
Workstream verifies by reading exact bytes.

## D4 - Required Commitments

Every untrusted source is fully prepared and server-hashed before provider I/O.
Any client commitment is checked before upload. Object keys use only that
server-computed digest and contain no product or customer identity.

## D5 - No Direct Upload

Workstream streams upload bytes. v0.1 has no presigned URL, signed upload
capability, browser-to-provider path, or client provider credential.

## D6 - Verification Before Binding

Provider acknowledgement sets the upload item to
`stored_pending_verification` and creates a pending replica, never a binding.
Celery independently reads and hashes the complete object. Only a matching
object becomes bindable.

## D7 - No Physical Deletion

v0.1 retains completed objects indefinitely. There is no provider delete,
garbage collector, automatic bucket deletion rule, legal-hold emulation, or
release API. A later initiative owns deletion policy and implementation.

## D8 - Recovery Ownership

Operator may authorize retry only for an exhausted terminal
`provider_unavailable` verification job. Celery executes under a fixed system
principal.
PostgreSQL coordinates Celery invocations with database time, executor UUID,
lease expiry, and generation fencing. Product task/review leases are unrelated.

## D9 - Closed Recovery Class

Recovery is read-only provider observation. No v0.1 recovery operation repairs
generic PostgreSQL facts, replays a provider mutation, or creates a destructive
effect.

## D10 - Durable Publication

Post-commit Celery publication is best effort, and a periodic PostgreSQL scanner
must republish pending/expired work within a configured SLA. Startup-only
scanning is insufficient.

## D11 - Observable Recovery

The recovery-attempt read route has an exact Authorization Service decision and
returns immutable source-job status plus current retry-job status. Operators
can observe eventual success or failure after retry without direct database
access.

## D12 - Shared Adapter Convention

S3CompatibleArtifactStore and LocalStorageAdapter are registered explicitly
through
`ExternalServiceAdapterFactory[ArtifactStoreBootstrap]`. The composition root
claims the bootstrap's exact namespace in PostgreSQL before initialization
yields the writable `ArtifactStore`. Only artifact-storage orchestration
receives that port. Product modules and Celery jobs receive typed artifact
operations from that owner. No service locator, plugin discovery, concrete
import, fallback constructor, dual factory, or bypassing writable-port injection
exists.

## D13 - Private S3 Deployment

Production uses HTTPS, a dedicated private AWS S3 bucket, Block Public Access,
and an allowlisted AWS workload-identity credential method. No public bucket,
signed URL, provider object key, endpoint, or credential appears in an API
response.
Runtime authority is restricted to put/get on the completed-object ARN and
bucket-level `s3:ListBucket` only for trustworthy missing-key `HeadObject`
classification. The port exposes no list method and Workstream calls no object-
list API. Delete, copy, lifecycle mutation, bucket administration, and public-
access mutation are denied. Static credentials are local/CI MinIO only.

## D14 - Clean Cut

The `flow_node` backend value and ArtifactStore v1 contract are removed in
02A3. Migration `0025` refuses populated v1 artifact tables before DDL and
preserves their prior schema and rows. An empty pre-production environment may
be reprovisioned out of band and authoritative bytes reingested through v2; the
migration performs no fabricated backfill. No backward compatibility is
retained.

## D15 - Route Deployment Claims

Application tests prove one exact image/build. They do not prove rolling-fleet
atomicity. Public activation requires homogeneous compatible instances or an
external fleet activation barrier.

## D16 - Deferred Flow Node

`FN-ART-002` keeps a full future adapter plan. It is inactive, does not operate
Flow Node, and cannot block the S3-compatible v0.1. Later adoption requires the
same v2 conformance suite and an explicit no-fallback maintenance cutover.

## D17 - Deferred R2

Cloudflare R2 is not a v0.1 production provider. This initiative contains no
R2 credential issuer, sidecar, runtime profile, secret contract, deployment
proof, or active chunk. Any later R2 adoption requires a separate approved
initiative, current provider discovery, the ArtifactStore v2 conformance suite,
and an explicit no-fallback maintenance cutover.

Pre-cutover caller-declared `r2` and `r2://` values are legacy input, not an R2
provider contract. Chunk 03 removes direct provider schemes from guide-source
identity. Chunk 05 removes the remaining values with the legacy submission
transport. No compatibility path remains after either cutover.

## D18 - Generic Durable-Storage Admission

Chunk 02C1 installs one PostgreSQL-owned admission service before guide,
contributor, or checker-output ingest activates. Every producer reserves all
applicable task, producer, project, and deployment byte charges after
Workstream computes canonical SHA-256 and exact size and before provider I/O.
Charges are unique by scope and content identity and transition through
`provisional`, `completed`, or `released` with CAS protection. Provisional and
completed charges count. Ambiguous outcomes remain provisional; only fresh
authoritative absence releases a charge, and replay must reacquire capacity.
Confirmed, quarantined, and integrity-mismatched bytes remain completed and
charged while v0.1 has no physical deletion.
Operators receive bounded read-only admission-usage visibility and alerts.
Quota expansion is a reviewed configuration/runbook operation; it never
releases or edits an authoritative charge.

## D19 - Submission-Bundle Scratch Capacity

The earlier durable multi-step upload-session slot design is superseded before
activation. One continuous submission-bundle preparation reserves bounded
scratch capacity through the existing `ArtifactScratchManager`. No durable
upload session/item is a candidate store, no scratch path crosses a process or
Celery boundary, and process loss requires reupload. ART-04A must remove or make
unreachable every unused upload-session/item model and action path; no alias or
parallel contributor intake remains.

## D20 - Closed Materialization Sources

Before durable admission, the checker receives only one internal
`PreparedArtifact`/`ArtifactScratchManager`-owned submission-bundle workspace in
the same process-local orchestration. After admission, the provider-neutral
materializer accepts only immutable `ArtifactBinding` IDs. Neither form creates
a second handle, lease, ledger, quota, cleanup path, or premature product
binding. Both recompute the relevant SHA-256 and byte counts before a checker
receives a read-only workspace.

## D21 - Configured Storage Namespace Fence

One immutable deployment-level `ArtifactStorageNamespace` is atomically
claimed or validated before startup and every provider operation. Its
fingerprint covers the canonical non-secret adapter/profile/namespace
descriptor, and replicas and put attempts reference it. A different concurrent
first writer or later configuration fails before I/O. Changing a populated
deployment requires a separate verified maintenance migration.

## D22 - AWS Readiness Ownership

Provider-readiness inspection is not part of `ArtifactStore` and is not called
by product services. Chunk 02D exposes only static prerequisite status. Chunk
07 owns the deployment-only AWS harness that verifies the exact trusted
principal set, effective Block Public Access, policy/ACL state, Access Analyzer
findings, lifecycle safety, and negative read/write/delete behavior for
anonymous and unapproved authenticated principals.

## D23 - Closed Product Capability Ports

Only `ArtifactStorageOrchestrator` receives `ArtifactStore`. Product modules
receive closed ingest, upload, binding, materialization, checker-output, or
Operator-read/recovery capabilities with server-owned request shapes. Operator
read includes bounded admission usage; recovery exposes only reason-bound
verification retry. They cannot inject the orchestrator, choose adapters/
provider references/namespaces/content IDs, or assemble admission scopes.

## D24 - Durable Put Attempt

Transaction A creates `ArtifactPutAttempt` before provider I/O. It owns
ambiguous acknowledgement and process-loss recovery before a replica or
verification job exists. Resolution is read-only through
`observe_put_result`; no background worker replays a write. Terminal writes are
fenced by executor and generation and revalidate fixed service authority in the
same transaction.

## D25 - Paired Authorization Activation

AUTH-07 registers artifact permissions, AUTH-08 owns applicable Operator grant
definitions, AUTH-09A owns the static service-action matrix, AUTH-09B provisions
fixed service ActorProfiles and ActorIdentityLinks, and AUTH-09E admits them at
runtime. Registry, grant, profile, link, matrix, or feature presence alone is
non-executable. AUTH first registers an exact planned action and activation
custodian; the owning WS-ART chunk then supplies hidden canonical resource facts,
guards, surface declarations, behavior, and tests while the real kernel still
fails closed; AUTH finally integrates the evaluator and alone changes that
action to active. ART never writes action availability. AUTH-12, AUTH-14, and
AUTH-15 do not provide alternate artifact activation paths.

## D26 - AWS Release Activation

02B1 adds validated AWS configuration and provider-proof support but production
composition remains unavailable. Chunk 07 uses separate readiness, actual
runtime-workload, and negative-role executors that write immutable caller-ARN-
bound `ArtifactProviderProbeResult` rows. A credential-free coordinator writes
the release-bound `ArtifactProviderActivation` only from one matching,
unexpired pass of each type. Startup and every AWS I/O require that activation;
proof is refreshed every 5 minutes and expires within 15 minutes. MinIO
conformance never activates AWS. Authorized cloud administrators are trusted
inside the bounded validity window; S3 Object Lock is outside v0.1 unless a new
human-approved decision changes that threat boundary.

## D27 - AWS Missing-Object Classification

The AWS production bucket is dedicated to Workstream artifact objects. The
runtime role receives `s3:PutObject` and `s3:GetObject` on the completed-object
ARN plus `s3:ListBucket` on the bucket ARN only because S3 otherwise masks a
missing `HeadObject` result as 403. `ArtifactStore` has no list method and
Workstream never calls `ListObjects` or `ListObjectsV2`. The adapter maps only
404 to missing; 403 always means provider unavailable. Chunk 07 must prove a
nonexistent opaque challenge key returns 404 under the actual runtime identity
before AWS activation.

## D28 - Authorization Owns Artifact Activation Custody

AUTH owns all artifact ActionId registration, service identities, exact static
matrix rows, evaluators, activation custody, and availability. ART owns artifact
resource facts, lifecycle guards, hidden behavior, and capability surfaces. ART
must not invent a service principal, inspect AUTH grants or static matrix
membership, or activate an authorization action.

The seven fixed service identities and complete 25-action custody transfer are
defined canonically in
`../WS-AUTH-001-workstream-authorization-service/ACTIVATION_CUSTODY.md` and its
`WS-AUTH-001-ART-CUSTODY` chunk contract. Operator verification retry remains
an independently authorized human action. Service identity, Celery executor
identity, and execution-generation fencing never substitute for one another.

## D29 - One Outer ZIP Per Submission

Every contributor Submission version accepts exactly one outer ZIP. Workstream
recursively inspects the directory/file tree represented by that archive so a
locked Project Guide checker can require entries such as `task.toml`. An archive
entry that is itself a ZIP remains one opaque ordinary file. Nested archive
unpacking is outside v0.1 and requires a separate reviewed capability with
cumulative safety limits before a Project Guide may request it.

## D30 - Scratch Before Durable Admission

Unchecked contributor bytes remain only in bounded private scratch through
format/safety inspection, canonical manifest generation, unchanged-work
comparison, mandatory platform gates, and locked project pre-submit checks.
Failed, unsafe, unchanged, abandoned, or checker-failing attempts never enter
object storage. Process or scratch loss before durable intent requires reupload.

No candidate provider namespace, retention window, promotion/copy, or physical
cleanup API is added. A passing ZIP enters the existing immutable
`ArtifactStore` path once. Ambiguous durable effects reuse existing put attempt,
observation, verification, receipt, scanner, and recovery abstractions.

## D31 - Canonical Submission Bundle Identity

Workstream records both exact archive identity (server-computed SHA-256 and byte
count) and semantic tree identity. The semantic manifest commits to normalized
file/directory path, entry type, each file's SHA-256 and byte count, and the
normalized executable flag for regular files. It does
not commit to archive timestamps, compression method/level, comments, ownership,
or ownership, group, read/write/special bits, or other platform permission
metadata. Valid Unix execute bits are normalized into the sole semantic
permission flag; non-Unix/invalid mode metadata defaults it to false. Symlinks
and unsupported special entries are
rejected. Exact archive equality or semantic-manifest equality with the
immediate prior immutable Submission rejects before provider I/O.

## D32 - Existing Submission Is The Version Aggregate

The current immutable `Submission` row plus its `version` and
`supersedes_submission_id` is the canonical version aggregate. There is no
competing `SubmissionVersion` table. A reviewer attaches only one of `accept`,
`needs_revision`, or `reject` plus note/findings to the exact Submission. A
contributor response to `needs_revision` uploads a new complete ZIP, creates the
next Submission, and records the exact prior-Submission and review relationship
through the TASK/REV joint contract.

Indexed latest/current/accepted queries or projections serve normal reads;
immutable relationships retain complete history and audit reconstruction.

## D33 - Integrity Is Rechecked On Egress

Historical verification is necessary but not sufficient for a later full-byte
read. Checker materialization, reviewer download, and downstream delivery use an
ART-owned provider-neutral read capability that recomputes complete SHA-256 and
byte count while streaming and fails closed on missing or mismatched bytes.
Consumer initiatives own their lifecycle decisions and reference the exact
Submission/binding; ART owns only byte identity, integrity, manifests, binding,
and access capability.

## D34 - Conservative Limits Remain

The existing configured upload, scratch, duration, and provider limits remain
unchanged. Any larger ZIP, extracted-byte, per-file, entry-count, depth,
compression-ratio, scratch, or time limit requires a separate reviewed change
with concurrency, capacity, runtime, cost, and abuse evidence.

## D35 - Verified Admissions May Remain Unbound

`SubmissionBundleAdmission` has the closed lifecycle `ready -> consumed|stale`.
Client abandonment is valid and remains charged to existing completed-byte
capacity. Consumption and Submission/binding creation are one transaction with
database uniqueness. Proven task/predecessor/locked-context drift makes a ready
admission stale; authority loss alone does not. No expiry, release, deletion,
retention process, or cleanup lifecycle exists in v0.1.

## D36 - Authorization Is Fresh At Both Durable Mutations

Initial route authorization is insufficient. 04C consumes an AUTH-owned
transaction-local prepared capability in the durable-intent transaction before
provider I/O. 05 obtains and consumes new human submission and fixed-service
binding capabilities in the atomic Submission/binding/admission transaction.
ART never reads or locks AUTH-owned persistence directly.

## D37 - Executable Intent Is Canonical, Not Archive Permission Preservation

Regular-file executable intent participates in semantic identity. Materializers
project fixed read-only or read-and-execute modes and fixed read-and-traverse
directory modes; they never preserve arbitrary ZIP permissions or automatically
execute a file. The Project Guide/checker policy remains the execution decision
owner. Shared scratch startup rejects inconsistent canonical mode configuration,
and secure cleanup remains owned by `ArtifactScratchManager`.

## D38 - One Contributor Preparation Action

The prior multi-step upload-session action proposal does not govern the new
continuous scratch-bound flow. AUTH first registers planned ActionId
`artifact.submission_bundle.prepare` mapped to existing PermissionId
`submission.create`. ART-04A through 04C then provide the complete hidden route,
canonical task/assignment/actor resource facts, guards, and manifest. AUTH alone
integrates and activates it afterward.

Contributor authority never implies fixed service authority. Checker
materialization, verification execution, pending-work scanning, ambiguous-put
resolution, and binding retain their distinct fixed actions. No compatibility
alias exposes the obsolete multi-step session actions.

## D39 - Guide Upload And Understanding Are Separate

Guide upload stores and verifies opaque original bytes. HTTP ingest does not
parse, extract, render, OCR, transcode, or wait for submission prechecks.
Understanding begins asynchronously only after an exact verified binding.
Unlike contributor submissions, guide-source items are not wrapped in one
mandatory outer ZIP. Each item retains its own verified format identity.

## D40 - Exact Setup Generation Is A Durable Fence

Every binding, extraction, agent input, and report identifies one project,
draft guide, source snapshot, setup run, and monotonic setup generation. Celery
carries only those identifiers and generation. Bytes, extracted text, scratch
handles, prepared authority, and provider credentials never enter Redis.

## D41 - Canonical Guide Materialization

The fixed guide-reader obtains fresh prepared authority, resolves an exact
verified binding, and streams through `ArtifactStore` into the existing
`ArtifactScratchManager`. Every full read recomputes SHA-256 and byte count.
Missing, changed, or truncated content is an ART incident, not guide
insufficiency. Project services and agents never access providers directly.

## D42 - Typed, Bounded Guide Extraction

One detector and typed extractor registry validates signatures and bounded
container markers. Initial text semantics cover PDF, DOCX, PPTX, CSV, XLSX,
Markdown, plain text, and JSON. PNG, JPEG, and WebP yield bounded structural
metadata only. Without OCR, image pixels cannot satisfy required textual guide
semantics. Audio/video and ambiguous binaries are unsupported in v0.1 and never
sent raw to agents. OOXML formats are distinguished from ordinary ZIPs.

Extraction runs asynchronously in a strongly isolated no-network subprocess
under fixed input, output, container, time, memory, and document limits using
only scratch-manager paths. Parser crash, malformed input, macros, external
relationships, embedded executables, cancellation, timeout, and executor loss
have bounded outcomes and cleanup. Production parser dependencies require
explicit human approval before implementation.

## D43 - Canonical Extraction Records, Not Implicit Provider Writes

v0.1 persists an immutable content-derived extraction representation in
PostgreSQL keyed by original content, format, extractor/version, and policy
version, with output digest, omission facts, status, and bounded error code. A
separate immutable usage record binds it to the exact guide binding, source
item, setup run, and generation. AUTH-04B grants read and binding only, so ART
does not use read authority to create a provider object.

## D44 - Sufficiency Consumes Complete Verified Material

The agent receives only bounded extraction records for all required items in
the current generation. Missing, corrupt, stale, ambiguous, unsupported, or
failed content stops policy derivation without creating a guide-insufficiency
decision. Reports preserve exact content and extraction provenance. Legacy
excerpts and durable refs are not authoritative after ART-03C.

## D45 - Extracted Guide Content Is Untrusted Agent Data

Canonical extraction proves byte provenance, not instruction authority. Agent
assembly labels and delimits source material as untrusted data, excludes tools,
provider access, credentials, and hidden instructions from that material, and
accepts only the typed sufficiency output contract. Prompt-injection text inside
a guide cannot alter system/developer policy or authorize an action.

## D46 - Setup Failures Have Stable Operational Outcomes

Existing `ProjectSetupRun.status=setup_blocked` uses stable redacted error codes
for artifact incident, unsupported format, malformed content, and extraction
failure. Recoverable incidents wait for ART recovery and expose a bounded
incident reference to authorized Operators. Terminal corruption or source
format/content failure requires the Project Manager to upload a corrected item
into a new snapshot. None creates a sufficiency decision.
