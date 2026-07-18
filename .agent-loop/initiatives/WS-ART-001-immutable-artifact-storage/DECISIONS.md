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

## D19 - Upload-Session Slot Expiry

Contributor open-session slots are separate from retained-byte admission.
Chunk 04A owns PostgreSQL-clock periodic Celery expiry and lazy expiry before
new-session admission. Both paths use the fixed system permission
`artifact.upload_session.expire` and one atomic terminal transition that
releases the slot exactly once. Cancellation or expiry never releases a
completed durable-byte charge.

## D20 - Closed Materialization Sources

The provider-neutral materializer accepts exactly one sealed upload artifact
set whose items are all `ready` before submission creation, or immutable
`ArtifactBinding` IDs after submission creation. Staging never creates a
premature product binding. Both forms resolve through phase-specific
authorization, stream exact provider bytes, and recompute SHA-256 and byte
count before a checker receives a read-only workspace.

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
