# Glossary

## Workstream

Source-agnostic governed contribution infrastructure for coordinating,
verifying, and recording work performed by humans, AI agents, or both.
Workstream binds project-defined tasks, locked rules, immutable submission
artifacts, deterministic checks, and authorized Reviews into trusted
`ContributionRecord` facts. Source applications and downstream economic or
reporting systems may consume those facts but do not control Workstream's
identity, authorization, submission, review, or contribution truth. Flow
Identity is the current v0.1 external authentication provider.

## Repository-Native Human-Agent SDLC

A software-development lifecycle in which intent, implementation, tests,
review, and durable decisions are visible in the repository. Repository records
support human judgment; they do not replace GitHub permissions or create a
second contribution-authorization system.

## Project

A configured work program with its own human-facing guide, submission artifact
policy, checker policies, review policy, revision policy, independently
published contribution policy, and queue.

## Project Owner

The external or internal organization that provides open-ended project material
and business terms. That material can be markdown, URL-backed documentation,
repository docs, examples, rubrics, task instructions, compensation business
terms, or other project-specific source material. The project owner
does not author or approve Workstream's machine-readable internal policy schema.

## ContributionPolicy

The stable project policy that determines what canonical contributions can
earn. Its immutable published `ContributionPolicyVersion` contains one explicit
`ContributionRule` for each contribution type. Unpaid rules create no award;
payable rules reference immutable `ContributionAwardDefinition` rows for money,
project points, or both. A Finance Authority publishes the policy. Project
owners provide business terms but do not author the machine policy directly.

## CompensationAward

The immutable result of evaluating one `ContributionRecord` against its frozen
`ContributionPolicyVersion`. Its instrument is `money` or `project_points`.
Money awards route downstream to payment-request/settlement adapters; points
awards route to the project-points adapter. Downstream adapters cannot create
award eligibility.

## ActorContext

Legacy name for the trusted per-request identity context resolved from a
verified Flow token. During WS-AUTH-001 migration it is replaced by a minimal
`VerifiedIssuerToken` plus locally resolved `AuthorizationContext`. Token roles
are not Workstream product authority.

## ActorIdentity

Legacy registry record for a verified Flow actor. WS-AUTH-001 classifies each
row before migrating safe UUID actor identifiers into canonical
`ActorProfile.id` plus a new `ActorIdentityLink`. It is not a grant or
Workstream-owned authentication.

## ActorProfile

The single canonical Workstream actor root. It records actor kind and status;
it does not itself grant project or administrative authority. Verified
issuer/subject identities attach through `ActorIdentityLink`. Authority comes
from `AdminRoleGrant` or exact-project `ProjectRoleGrant` records plus resource
and lifecycle guards.

Legacy typed profile row IDs are workflow metadata IDs and never canonical
actor IDs or grants.

## ActorIdentityLink

The active-or-revoked link between one canonical issuer/opaque subject and one
ActorProfile. Raw tokens, provider credentials, and full claims are not stored.

## SubmissionBundlePreparation

The bounded process-local operation that receives one contributor outer ZIP,
inspects and checks its internal tree in private scratch, and hands passing bytes
once to immutable artifact admission. It is not durable candidate storage, a
Submission, or review authority; process loss before durable intent requires
reupload.

## ArtifactContent

Workstream's provider-neutral immutable content identity: server-computed
SHA-256, byte count, and bounded media metadata. Opaque provider identifiers and
protocol observations are replica details, not this record's identity.

## SubmissionBundleAdmission

The capacity-charged verified result of one passing submission-bundle
preparation. Its closed lifecycle is `ready -> consumed|stale`. A ready admission
may remain unbound through client abandonment; consumption is atomic with one
immutable Submission and binding, while proven task/predecessor/locked-context
drift may make it stale. No state expires, releases storage capacity, or
authorizes deletion in v0.1.

## ArtifactBinding

The immutable logical association between `ArtifactContent` and one exact
Workstream project/resource/logical role. Staging is not a binding. Replacement
creates a new row with `supersedes_binding_id`; prior rows remain history. It
records Workstream meaning and provenance, not storage-provider state.

## ArtifactReplica

One provider copy of `ArtifactContent`, identified by an opaque
`provider_object_ref` and optional bounded protocol observations. Verification,
availability, and integrity states belong here and do not create task or review
states. Logical Workstream references are represented only by
`ArtifactBinding`.

## ArtifactOperationReceipt

Append-only Workstream evidence for one immutable put acknowledgement. It links
the exact producer admission/attempt and replica and records operation, idempotency key,
`request_digest`, opaque `provider_object_ref`, replay observation, bounded
outcome/details, attempt number, correlation ID, and creation time. It contains
no response digest or provider receipt.

## SubmissionBundleManifest

The server-generated canonical semantic description of the file/directory tree
inside one contributor outer ZIP. It commits to normalized paths, entry types,
each file's SHA-256/byte count, and normalized regular-file executable intent
while excluding other ZIP packaging and permission metadata.
It is distinct from the exact outer-ZIP SHA-256/byte count. Together they bind
pre-submit evidence, verified admission, the immutable Submission, and its exact
artifact binding.

## ReviewPacketManifest

The planned immutable WS-REV semantic projection for one exact queue entry,
active ReviewLease, Submission, admitting CheckerRun, stamped context, response
evidence, and ART binding IDs. Only the exact active lease authorizes its packet
bytes; authorized history exposes bounded metadata only.

## ReviewEvidenceArtifact

The planned immutable WS-REV semantic relation from a lease/finding or
preparation/response evidence slot to one ART-finalized binding. ART owns the
bytes and binding; REV owns the lifecycle purpose and lineage.

## AdminRoleGrant

An immutable administrative authority record for Access Administrator,
Operator, Project Manager, Finance Authority, or Audit Authority at compatible
system/project scope.

## ProjectRoleGrant

An immutable exact-project contributor authority record with role `submitter`,
`reviewer`, or `adjudicator`. A contributor may hold all three capabilities
through separate active grants.

## Contributor

The umbrella human product term for a person participating in Workstream. A
contributor may have exact-project `submitter`, `reviewer`, and `adjudicator`
grants as independent records. The adjudicator grant creates no adjudication
capability in v0.1. A future separately approved initiative must define that
lifecycle before AUTH registers and activates any exact action. Celery, checker,
setup, and background workers are
internal services, not human product roles.

## Source

Where a task came from. In v0.1, sources are manual creation, controlled markdown import, or controlled CSV import.

## Origin

A future external task source that can submit tasks into Workstream through an adapter. External origin onboarding is not part of v0.1.

## Project Guide

The human-facing operating guide for a project. It contains the project instructions, quality bar, task examples, reviewer rubric, common rejection reasons, and links or summaries for the approved policies. A project guide may be markdown, an imported document, or a URL-backed guide, but runtime enforcement uses approved machine-readable policies attached to the guide version.

## Guide Sufficiency Report

The Workstream-owned sufficiency record for a project guide version and source
snapshot. It is normally produced by `ProjectGuideSufficiencyAgent`, but an
authorized covered Project Manager may also request that agent assessment over
the canonical verified material. A separately created manual report is
diagnostic and does not replace agent provenance.
It records
whether the guide passed, is blocked by gaps, or passed with warnings that an
authorized covered Project Manager must acknowledge before activation. Manual reports
clear only the manual policy path; agent derivation requires an agent-created
sufficiency report for the same snapshot.

## Project Setup Run

A non-authoritative orchestration ledger for automatic project setup. It records
queue status, current setup step, Celery task id, bounded errors, and output
record ids for guide sufficiency, submission artifact policy derivation, and
post-submit checker setup continuation. The actual policy truth remains in the
source snapshot, sufficiency report, submission artifact policy, effective
project policy, pre-submit checker policy, and post-submit checker policy rows.

## Submission Artifact Policy

The Workstream-derived, covered-Project-Manager-approved machine-readable
contract for what a contributor must submit. It is derived from open-ended project
guide material after guide sufficiency passes or passes with warnings, reviewed
by an authorized covered Project Manager after any
warnings are acknowledged, and attached to a project guide version. It defines
required artifacts, evidence requirements, forbidden artifacts, attestation
requirements, size limits, and project-specific packaging rules. It can add or
tighten requirements, but it cannot weaken Workstream's default submission
artifact rules. Server-generated manifests, SHA-256, and the configured storage
provider are unconditional platform invariants rather than project policy
choices.

The project-specific policy row is still `SubmissionArtifactPolicy`; Workstream
does not define a separate `ProjectSubmissionArtifactPolicy` type.

## Effective Project Submission Artifact Policy

The deterministic merge of Workstream's default submission artifact policy and the project-approved submission artifact policy. Workstream computes this effective project policy before generating the project pre-submit checker policy.

## Pre-Submit Checker Policy

The server-generated project checker matrix produced from the effective project submission artifact policy and one immutable default-catalogue snapshot. The compiled bundle embeds the catalogue version, canonical manifest digest, ordered entry ID/version/configuration hashes, and enabled/disabled state. Its compiled bundle hash therefore commits transitively to that exact snapshot, and each task locks that hash before entering the contributor pipeline. Runtime uses the same snapshot to derive the effective-plan hash. It runs against the uploaded ZIP in bounded scratch before Workstream creates a submission. A failed preparation returns `pre_submission_checker_failed` with bounded same-request details. The old standalone preflight route remains frozen legacy behavior until WS-ARCH-001-02I removes it with the legacy Submission path after all submission contexts and downstream prerequisites are live; it is not an alternate authority for this policy. Results never use review decision values: `accept`, `needs_revision`, or `reject`.

The hidden 04B2 Workstream-default execution slice and the hidden 04B3 complete
effective execution use the closed entry statuses
`passed`, `warning`, `failed`, `advisory_disabled`, and
`dependency_not_run`. These are checker-execution facts, not review decisions.
04B3 executes locked project-policy entries through that same plan and persists
one immutable ordered platform-plus-project evidence set after scratch cleanup.

## pre_submission_checker_failed

The contributor-facing domain error code returned when submission-bundle preparation is blocked by pre-submit checks. It includes bounded structured pass/fail/warning details in the same response and is not a review decision. It must not be stored as `accept`, `needs_revision`, or `reject`.

## Task

A unit of work inside a project.

## Task Work Context

The contributor-safe API projection of a task's guide, project summary, review
policy, revision policy, and lifecycle state. Initial work reads the task's
locked context. Human-review revision reads the validated immutable
RevisionContextPreparation head and digest, not a moving active-guide pointer.
It does not expose source snapshot
hashes, private source/import refs, compiled checker bundles, checker configs,
Celery ids, or setup errors.

## Task Submission Requirements

The contributor-safe API projection of the task's locked effective project
submission artifact policy. It tells the contributor the exact required artifacts,
evidence keys, forbidden artifact rules, storage reference rules, packaging
rules, hash algorithm, size limits, and attestation terms before submission.

## Task Locked Context

The permission-scoped Project Manager, Operator, or Audit projection of a task's
locked guide and policy provenance, including guide source snapshot id/hash,
effective policy id/hash, pre-submit checker policy id/hash, post-submit checker
policy id/hash/body summary, and exact review and revision policy
id/generation/hash identities.

## Task Contract

The normalized task fields required for Workstream to screen, assign, check,
review, compensate, and audit work.

## Submission Packet

The contributor supplies a summary, accountability attestation, and one outer
ZIP containing every required output/evidence file. Workstream derives the
archive hash/size, semantic manifest, evidence facts, verified admission,
artifact binding, and immutable Submission version server-side. Clients do not
supply canonical hashes, manifests, provider references, or content IDs.

## Checker

An automated rule that validates a task or submission before human review.

## Checker Policy

The set of required and warning checks for a project phase. Pre-submit checker policy is generated from the effective project submission artifact policy. Post-submit checker policy governs durable internal checker runs after a submission is finalized into the pre-review gate.

## Human Review

The judgment layer where a reviewer accepts, rejects, or requests revision.

## ReviewQueueEntry

The planned durable admission record connecting one exact finalized Submission
and successful current CheckerRun to server-selected human-review routing.

## ReviewLease

The planned permanent identity of one reviewer claim attempt. It binds the
canonical human reviewer, queue entry, exact Submission packet, lease timing,
and ContributionPolicyVersion inherited from the task lock.

## Review

The immutable result of one valid human decision under an active ReviewLease.
Stored decisions are exactly `accept`, `needs_revision`, or `reject`. Later
rounds append another Review rather than modifying history.

## ReviewFinding

A planned immutable structured issue submitted with a Review. Its lifecycle
meaning is `blocking` or `advisory` and it carries area, required change,
rationale, and optional finalized evidence.

## SubmissionFindingResponse

The immutable submitter response to one prior ReviewFinding, with response text
and optional finalized evidence. Every unresolved blocking finding requires one
response before revision submission.

## FindingResolution

The immutable later-review judgment for one prior finding and revised
Submission: `resolved`, `unresolved`, or `not_applicable`, with bounded rationale
and evidence.

## RevisionContextPreparation

The immutable Review-rooted next-attempt context. It records the prior
Submission; source and target TaskAssignments; prior and next Project
Guide/source, submission/checker, review, revision, task-execution, and
submitter ContributionPolicy versions; context digest; change summary; and
`kept`, `rebased`, or `blocked` result. A human revision rebase records forward
or backward direction where applicable and publishes one complete next-attempt
context without rewriting prior work.

## FinalAcceptance

The internal immutable accept-only fact linking one task, versioned Submission,
source Review, accepted submitter, recording reviewer, time, and ReviewPolicy.
It has no manual API or separate action and is the sole source of the submitter
`accepted_submission` ContributionRecord.

## Revision Replay

The complete immutable response and resolution history connecting a prior
Review's findings to the next Submission and later Review.

## Evidence

Proof supporting task completion or review decision. Examples: logs, hashes, tests, screenshots, diffs, notes.

## Artifact Store

The provider-neutral ART v2 byte boundary beneath Workstream's typed product
capabilities. Its v0.1 byte-only operations are `put`, read-only
`observe_put_result`, `open`, and `head`; product services consume narrow typed
capabilities rather than importing the raw store. `LocalStorageAdapter`
implements it for development and focused tests.
`S3CompatibleArtifactStore` implements it for MinIO integration and AWS S3
v0.1 production deployments. Providers do
not own Workstream authorization, binding, lifecycle, audit, or integrity
decisions.

## Artifact Storage Namespace

The immutable deployment-level PostgreSQL fence that binds Workstream to one
configured artifact backend, adapter, provider profile, and non-secret storage
namespace fingerprint. Startup and every provider operation must validate the
same singleton before provider I/O. Changing a populated deployment requires a
separately reviewed storage migration.
For LocalStorage, the pre-provisioned private root's normalized path and
filesystem identity are hashed into that fingerprint, so replacing the root at
the same path fails closed before adapter construction mutates it.

## Artifact Verification Job

A durable Celery request to read and hash a complete stored object before its
replica becomes bindable. PostgreSQL coordinates execution with an executor
UUID, lease expiry, and generation fencing. This infrastructure lease is not a
contributor task claim or reviewer lease.

## Artifact Recovery Attempt

A reason- and idempotency-bound Operator authorization/audit envelope with
distinct source and retry verification job IDs. It is not executable work and
owns no Celery executor, execution lease, or generation; the retry verification
job owns those infrastructure coordination fields.

## S3-Compatible Artifact Store

The object-storage adapter that implements `ArtifactStore` using the S3
protocol. AWS S3 is the v0.1 production provider; MinIO is used for local and CI
integration proof. Cloudflare R2 is deferred to a separate approved initiative.

## Compensation Fulfillment

The award-delivery and fulfillment record set for payable compensation:
immutable `CompensationAward` and `CompensationFulfillmentReceipt` records plus
a rebuildable `CompensationStatusProjection`. Explicitly unpaid contribution
rules create no award.

## Reputation Ledger

The deferred outcome-based projection of contributor and reviewer performance.
It is not a v0.1 review-transaction side effect.

## Contribution Record

The immutable, evidence-backed record of one completed contribution under locked
project context. `completed_review` is created for every valid recorded human
Review and binds directly to that Review and ReviewLease.
`accepted_submission` is created only from FinalAcceptance and the exact
TaskAssignment; it is never inferred directly from `Review.decision`.
Compensation records may attach to either contribution type but do not replace
the contribution record; reputation projections remain deferred.

## Final Acceptance

The immutable REV-owned internal fact created only as a lifecycle consequence
of `Review(accept)`. It binds one project, task, existing versioned Submission,
source Review, accepted submitter, recording reviewer, acceptance time, and
locked ReviewPolicy. There is no public/manual create API or separate
authorization action. `needs_revision` and `reject` create none. In v0.1 it is
unique per task, source Review, and Submission and is the sole source of an
`accepted_submission` ContributionRecord.

## Human Owner

The person accountable for a submitted packet, even when agents or external tools helped produce the work.
