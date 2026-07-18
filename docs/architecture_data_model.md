# Data Model

## Implementation Stack

The v0.1 persistence layer uses SQLAlchemy 2.x async models, Alembic migrations, and Pydantic schemas.

## Entity Overview

```text
ActorProfile
  ActorIdentityLink
  AdminRoleGrant
  ProjectRoleGrant
  QualificationSnapshot
AuthorityControl
AuthorityIdempotencyRecord
AuthorityInvalidationEvent

Project
  ProjectCompensationAdapterBinding
  ProjectGuide
  GuideSourceSnapshot
  GuideSourceSnapshotItem
  ProjectSetupRun
  GuideSufficiencyReport
  SubmissionArtifactPolicy
  EffectiveProjectSubmissionArtifactPolicy
  PreSubmitCheckerPolicy
  PostSubmitCheckerPolicy
  ReviewPolicy
  RevisionPolicy
  ContributionPolicy
    ContributionPolicyVersion
      ContributionRule
        ContributionAwardDefinition
  ProjectLesson

Task
  Assignment
  Submission
    EvidenceItem
    CheckerRun
      CheckerResult
    ReadinessCertificate (later optional)
    ReviewQueueEntry
      ReviewLease
        ReviewPacketManifest
    Review
      ReviewFinding
      ReviewEvidenceArtifact
      FindingResolution
      FinalAcceptance (accept only)
    RevisionContextPreparation
    SubmissionFindingResponse
  ContributionRecord
    CompensationAward
      CompensationFulfillmentReceipt
      CompensationStatusProjection
  ReputationEvent (deferred)
  AuditEvent
```

## Actor Authorization Model

The canonical target model is introduced by staged WS-AUTH-001 migrations. The
current legacy tables remain implementation evidence until their owning cutover
chunks merge.

### ActorProfile

`ActorProfile` is the single Workstream actor root.

Fields include:

- `id`
- `kind` (`human` or explicitly provisioned `service`)
- `status` (`active`, `suspended`, `deactivated`)
- permitted display/profile metadata
- database-time creation/update fields
- bounded suspension and reactivation attribution plus immutable terminal
  deactivation attribution after AUTH-09D-A migration `0026`

Profile status is a guard, not a role or project grant.
Lifecycle invalidation effectiveness is component-scoped. Reactivating a
profile records `effective=false -> effective=true` for that profile projection
without asserting that its identity link, grants, or fixed-service admission
make the whole actor effective.

### ActorIdentityLink

An identity link binds one canonical external issuer and opaque subject to one
ActorProfile. It has active/revoked state plus state-transition-guarded current
revocation and reactivation attribution. AUTH-09D-A migration `0026` enforces
complete attribution and bounded lifecycle reasons before AUTH-09D-B activates
link mutations. Append-only audit evidence preserves immutable transition
history; the current row carries only the latest state-compatible attribution.
Raw tokens, provider credentials, and full claim payloads are not stored.
The database enforces a unique `(issuer, subject)` pair across all links and, in
v0.1, at most one active identity link per ActorProfile. Revocation preserves
the immutable link and provenance; it does not free the pair for rebinding.

### AdminRoleGrant

Immutable administrative-grant history with role, compatible system/project
scope, target profile, issuing grant/actor, reason, active/revoked state, and
database time. Roles are Access Administrator, Operator, Project Manager,
Finance Authority, and Audit Authority.

### ProjectRoleGrant

Immutable exact-project contributor-grant history with role `submitter`,
`reviewer`, or `adjudicator`, target profile, issuing Project Manager grant,
role-specific qualification snapshot, reason, and active/revoked state.

Contributor is the umbrella human product term. A human may hold separate
active `submitter`, `reviewer`, and `adjudicator` grants for the same project;
each is revoked independently. An adjudicator grant authorizes no v0.1 action.
The review lifecycle defines no adjudication policy, queue, state, decision, or
API; a future separately approved initiative owns any lifecycle definition,
authorization, and release. Celery, checker,
setup, and background workers are internal services,
not human product roles.

### QualificationSnapshot

An immutable, privacy-bounded record of evidence considered by a covered
Project Manager before manual contributor grant creation. It never creates a
grant automatically.

### AuthorityControl

The singleton `AuthorityControl(id = 1)` row serializes one-time bootstrap and
every operation that could remove the final effective Access Administrator.

### Authority Idempotency And Invalidation

`authority_idempotency_records` binds one client key to the exact actor-kind,
opaque actor reference, closed mutation operation, canonical request digest,
and typed committed resource reference. The unique actor-scoped namespace
serializes concurrent retries. New rows begin `pending`; a deferred PostgreSQL
guard prevents that state from committing, and immutable database triggers
permit only one evidence-backed transition to `committed`.

The raw request and response body are never stored. Replay returns only an
internal resource type/UUID, optional positive version, and exact successful
status; route-owning code must reload and reauthorize that resource before
external disclosure. New linked audit rows use an actor-bound composite foreign
key while the `NOT VALID` migration preserves pre-foundation forward references.
Every committed authority mutation has exactly one concrete success event and
one causally linked `AuthorityInvalidationRequested` event in `audit_events`.
This foundation persists the request digest and typed replay reference only; no cache, queue,
background job processor, or consumer
acts on invalidation yet.

### API Rate Control Counter

`api_rate_control_counters` is a cross-replica fixed-window control for future
first-access and authority-management mutations. Its composite key is the
server-owned `control_scope` plus a 32-byte HMAC-SHA256 `key_digest` derived
from the exact verified issuer and opaque subject. It stores database-time
window start/expiry, a saturating `BIGINT` request count, and database-time
update evidence. It has no actor/profile foreign key or surrogate identifier
and stores no raw issuer, subject, email, role, token, claim, or network data.

One PostgreSQL upsert atomically inserts, increments, saturates, or resets an
expired counter using a single statement timestamp. Consumption and bounded
expired-row pruning commit in a short independent session before a route may
continue. These counters are abuse controls, not identity, grants, product
authority, audit events, or a replacement for exact authorization checks.

### Legacy Migration

Existing external `ActorIdentity.actor_id` UUIDs may become canonical profile
IDs only after exact issuer/subject/subject-kind classification. Typed legacy
profile row IDs never become actor IDs or grants. No email, subject shape,
skill, reputation, profile type, or token role is used to infer authority.

## Project

Fields:

- `id`
- `name`
- `slug`
- `description`
- `status`
- `created_at`
- `updated_at`

Status:

- draft
- active
- paused
- archived

## ProjectGuide

Fields:

- `id`
- `project_id`
- `version`
- `status`
- `content_markdown`
- `change_summary`
- `approved_by`
- `effective_at`
- `created_by`
- `created_at`
- `updated_at`
- `superseded_at`

The guide is versioned and human-facing. Its persisted body is the project
guide material itself, usually markdown or imported source material. The source
snapshot may include URL-backed docs, repository docs, examples, rubrics, task
instructions, reviewer guidance, or other project-specific source material.
`approved_by` and `effective_at` are server-written activation provenance, not
request-body fields and not contributor-facing guide content.

Runtime enforcement uses machine-readable policies attached to the guide version. Workstream does not parse guide prose at submission time to decide which artifact checks to run.

Project owners provide open-ended setup material and business terms. Workstream
does not force every project owner through one universal intake checklist.
Workstream evaluates guide sufficiency, derives machine-readable project policy,
and owns the internal controls. A covered Project Manager grant authorizes the
guide-policy approval flow before the guide can activate.

Every task records the guide version active at creation or screening time before the task enters `READY`. Later source adapters must also lock the guide version during normalization before contributors see the task.

When a task is claimed or moved to `IN_PROGRESS`, its locked guide and policy context does not change silently. A newer upstream guide version can only affect unclaimed work or a controlled revision path when policy allows it and the audit log records the reason.

Material changes require a new guide version or policy version. They include
guide source material, submission artifact policy, pre-submit checker
generation rules, post-submit checker policy, review policy, revision policy,
and their guide-bound contracts. Contribution policy publication is independent
of guide versioning and affects only new TaskAssignments and ReviewLeases; their
frozen versions never drift.

## GuideSourceSnapshot

Fields:

- `id`
- `project_id`
- `guide_id`
- `guide_version`
- `manifest_schema_version`
- `manifest_json`
- `bundle_hash`
- `captured_at`
- `captured_by`

`GuideSourceSnapshot` is the immutable bundle binding for guide material. It
captures the exact guide/source material Workstream evaluated as a canonical
manifest. A guide can point at markdown, imported documents, URL-backed docs,
repository docs, examples, or rubric material, but downstream records do not
trust a mutable URL or mutable draft guide body. They bind to
`source_snapshot_id` and a server-derived `source_snapshot_hash` copied from
`GuideSourceSnapshot.bundle_hash`.

`bundle_hash` is:

```text
sha256(canonical_json(manifest_json))
```

Canonical JSON uses UTF-8, sorted object keys, no insignificant whitespace, and
source items sorted by `(source_kind, durable_ref, content_hash)`. Volatile
database ids, capture timestamps, and transient fetch locators are excluded from
the canonical manifest. Duplicate source items with the same
`source_kind + durable_ref` are rejected before hashing. Changing any included
document, example, rubric, repository doc, or inline guide body creates a new
snapshot and bundle hash.

Every snapshot includes a server-derived `project_guide` source item whose
content hash is computed from the current guide material fields. Caller-supplied
source items can add external docs, examples, or rubrics, but they cannot omit
the guide body from the bundle hash.

Source items may include a bounded `content_excerpt` in the canonical manifest
so setup agents can inspect representative task examples or source snippets
without following mutable refs at runtime. `content_excerpt` is untrusted source
material, is included in `bundle_hash`, and is not stored as a separate mutable
database column.

## GuideSourceSnapshotItem

Fields:

- `id`
- `source_snapshot_id`
- `item_order`
- `source_kind`
- `durable_ref`
- `ingestion_adapter`
- `content_hash`
- `artifact_content_id`
- `media_type`
- `created_at`

`GuideSourceSnapshotItem` records each material item included in the guide
bundle. `source_kind` distinguishes inline markdown, URL-backed documentation,
repository docs, examples, rubrics, imported files, and other approved source
types. `durable_ref` is opaque and sanitized; it is not the temporary fetch
locator. `artifact_content_id` references Workstream's provider-neutral
immutable content record; provider object references remain replica details.

URL-backed guide ingestion is split into two identities:

- temporary fetch locator: used only by an approved retrieval adapter
- durable source record: opaque sanitized source ref plus `artifact_content_id`

Ordinary URL query parameters can be used by approved adapters when fetching
legitimate documentation. Query strings are temporary fetch inputs only.
Workstream must not persist query strings, signed URLs, credentials,
token-bearing locators, local filesystem paths, or private storage paths as
durable source identity.

Any guide or source-material change creates a new source snapshot. That
invalidates prior sufficiency reports, derived policies, effective policies,
checker bundles, acknowledgements, and approvals for activation.
A new guide-source snapshot invalidates prior setup records for new activation
and unlocked tasks only. Tasks already locked to an earlier snapshot retain
that policy context unless an explicit audited rebase occurs.

## ProjectSetupRun

Fields:

- `id`
- `project_id`
- `guide_id`
- `guide_version`
- `source_snapshot_id`
- `source_snapshot_hash`
- `celery_task_id`
- `status`
- `current_step`
- `output_sufficiency_report_id`
- `output_submission_artifact_policy_id`
- `output_post_submit_checker_policy_id`
- `post_submit_derivation_summary`
- `error_code`
- `error_summary`
- `created_by`
- `created_at`
- `updated_at`
- `started_at`
- `finished_at`

`ProjectSetupRun` is a non-authoritative orchestration ledger for automatic
project setup. It records that Workstream queued or attempted the guide
sufficiency, submission artifact policy derivation, and post-submit checker
policy derivation continuations for one guide source snapshot. It does not
replace the source snapshot, sufficiency report, submission artifact policy,
effective project policy, pre-submit checker policy, or post-submit checker
policy rows.

Current step values are stable setup diagnostics, not product lifecycle states:

- `queued`
- `enqueue`
- `guide_sufficiency`
- `submission_artifact_policy_derivation`
- `project_setup`
- `post_submit_checker_policy_enqueue`
- `post_submit_checker_policy_derivation`
- `post_submit_checker_policy_compilation`

Statuses:

- `queued`
- `enqueue_failed`
- `running_sufficiency_agent`
- `sufficiency_blocked`
- `running_policy_derivation_agent`
- `policy_draft_ready`
- `running_post_submit_derivation_agent`
- `post_submit_setup_blocked`
- `post_submit_policy_compiled`
- `setup_blocked`
- `failed`

The run references downstream truth by id/hash. Operators can read the latest
run through the project setup API to understand whether setup is still queued,
blocked by guide sufficiency, waiting on policy approval, compiling post-submit
policy, blocked by unsupported checker requirements, or failed at the
queue/worker layer. Error summaries and post-submit derivation summaries are
bounded and redacted; server logs remain the source for sensitive diagnostics.
The default setup-run API returns the source snapshot id for correlation, but
does not return the exact source snapshot hash; exact hashes remain available
through source-snapshot and policy records when an authorized workflow needs
provenance inspection.

## GuideSufficiencyReport

Fields:

- `id`
- `project_id`
- `guide_id`
- `guide_version`
- `source_snapshot_id`
- `source_snapshot_hash`
- `status`
- `findings`
- `summary`
- `agent_name`
- `agent_version`
- `created_by`
- `created_at`
- `warnings_acknowledged_by_role`
- `warnings_acknowledged_by_actor`
- `warnings_acknowledged_at`
- `acknowledgement_note`

Status:

- `passed`
- `blocked`
- `passed_with_warnings`

Finding severity:

- `blocking_gap`
- `warning`
- `info`

`ProjectGuideSufficiencyAgent` creates this report asynchronously for a guide
version. Blocking gaps stop guide activation and create clarification requests
for the project owner. Warnings can be acknowledged only by an authorized
covered Project Manager before activation.

`source_snapshot_hash` is server-derived from the referenced
`GuideSourceSnapshot.bundle_hash`. Clients cannot supply a conflicting hash.
Manual sufficiency reports persist `agent_name` and `agent_version` as null.
Reports created through the agent route persist Workstream-owned agent identity;
provider-returned names or versions are not trusted as audit provenance.
A source snapshot has one sufficiency report. If a manual report already exists
for a snapshot, operators either continue through manual policy creation after
clearance or create a new guide-source snapshot to run the agent path.

## SubmissionArtifactPolicy

Fields:

- `id`
- `project_id`
- `guide_id`
- `guide_version`
- `source_snapshot_id`
- `source_snapshot_hash`
- `policy_version`
- `lifecycle_status`
- `policy_body`
- `policy_hash`
- `derivation_source`
- `source_material_refs`
- `derivation_agent_name`
- `derivation_agent_version`
- `created_by`
- `created_at`
- `updated_at`
- `approved_by_admin_role_grant_id`
- `approved_by_actor_profile_id`
- `approved_at`
- `supersedes_policy_id`
- `superseded_at`
- `change_summary`

Example:

```json
{
  "policy_version": "v1",
  "policy_body": {
    "required_artifacts": [
      {
        "key": "answer",
        "path": "outputs/final-answer.md",
        "hash_required": true,
        "required": true
      }
    ],
    "required_evidence": [
      {
        "key": "oracle_test_log",
        "label": "Oracle test log",
        "hash_required": true,
        "required": true
      }
    ],
    "forbidden_artifacts": [
      {
        "pattern": "*.tmp",
        "reason": "Temporary files are not reviewable."
      }
    ],
    "attestation_terms": ["project_specific_originality"],
    "manifest_required": true,
    "artifact_hash_required": true,
    "artifact_hash_algorithm": "sha256",
    "maximum_file_size_bytes": 52428800,
    "maximum_package_size_bytes": 104857600,
    "packaging": {
      "package_required": true,
      "allowed_package_formats": ["zip"]
    }
  },
  "policy_hash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "derivation_source": "agent_derivation",
  "derivation_agent_name": "SubmissionArtifactPolicyDerivationAgent",
  "derivation_agent_version": "workstream-policy-derivation-agent-v0.1",
  "source_material_refs": ["project-guide:v1"],
  "lifecycle_status": "approved",
  "approved_by_admin_role_grant_id": "00000000-0000-0000-0000-000000000010",
  "approved_by_actor_profile_id": "00000000-0000-0000-0000-000000000020",
  "approved_at": "2026-06-22T12:00:00Z"
}
```

Workstream derives this policy from project guide material after guide
sufficiency passes or passes with warnings. An authorized covered Project
Manager approves it after any sufficiency warnings are acknowledged. Project
owners and contributors do not supply or approve this internal
policy schema.
`derivation_source` is server-owned. The legacy technical token
`manual_admin_derivation` remains historical provenance until its owning
migration; it does not grant authority. Policies created by the derivation agent persist
`agent_derivation`. Client requests do not supply derivation provenance, and
manual `policy_version` values cannot use the reserved `agent-` prefix.
Agent-derived policy versioning and persisted derivation-agent identity are
server-owned. The derivation agent can run only from a Workstream-agent
sufficiency report for the same guide source snapshot; manual sufficiency
reports can support manual policy creation after clearance, but they do not
create agent-derivation provenance.
Agent-derived policy provenance is revalidated before approval and guide
activation, so seeded or stale rows with spoofed agent identity cannot become
the active policy context.

Project policy can add stricter requirements, but it cannot weaken Workstream's default submission artifact policy.
`artifact_hash_algorithm` is platform-locked to `sha256` for v0.1. Project
policy cannot change it, and trusted task runtime parameters cannot override it.
`source_snapshot_hash` is server-derived from the referenced snapshot bundle
hash.

Policy content, hashes, approval provenance, and source binding are immutable
after approval:

```text
draft      -> mutable
approved   -> immutable
superseded -> immutable
```

Changing an approved policy creates a new policy revision with
`supersedes_policy_id`. During that locked replacement transaction, Workstream
may update only the prior row's lifecycle closeout metadata
(`lifecycle_status = superseded`, `superseded_at`) so operators can see the
current lineage directly. Policy body, policy hash, source snapshot binding,
approval actor, approval role, and approval timestamp are not edited in place.

## EffectiveProjectSubmissionArtifactPolicy

Generated server-side from:

```text
WorkstreamDefaultSubmissionArtifactPolicy
+ SubmissionArtifactPolicy
```

Fields:

- `id`
- `project_id`
- `guide_id`
- `guide_version`
- `source_snapshot_id`
- `source_snapshot_hash`
- `submission_artifact_policy_id`
- `submission_artifact_policy_hash`
- `lifecycle_status`
- `merge_algorithm_version`
- `effective_policy`
- `effective_policy_hash`
- `created_by`
- `created_at`
- `supersedes_effective_policy_id`
- `superseded_at`

This policy is deterministic. It preserves Workstream defaults first and adds project-approved requirements. Duplicate project rule keys are rejected before merge. Default and project rules merge by canonical key, and any project rule that conflicts with Workstream defaults is a project setup defect.

The merge contract is executable per field:

| Field | Merge rule |
| --- | --- |
| `required_artifacts` | union by canonical artifact key |
| `required_evidence` | union by canonical evidence key |
| `forbidden_artifacts` | union |
| `attestation_terms` | union |
| `manifest_required` | logical OR |
| `artifact_hash_required` | logical OR |
| `allowed_storage_schemes` | intersection |
| `artifact_hash_algorithm` | platform-locked `sha256`; project policy cannot change it and task runtime parameters cannot override it |
| `maximum_file_size_bytes` | minimum non-null limit |
| `maximum_package_size_bytes` | minimum non-null limit |
| `packaging` | restrictive merge; conflicts block activation |

A required artifact or evidence rule matching a forbidden artifact rule blocks
project setup as a policy conflict. It is not deferred to contributor submission.

Approved and superseded effective policy content and hashes are immutable.
Recomputing the effective policy after guide/source/policy changes creates a new
row and hash. Supersession is represented by the replacement row's
`supersedes_effective_policy_id`. During that locked replacement transaction,
Workstream may update only the prior row's lifecycle closeout metadata
(`lifecycle_status = superseded`, `superseded_at`).

## PreSubmitCheckerPolicy

Fields:

- `id`
- `project_id`
- `guide_id`
- `guide_version`
- `source_snapshot_id`
- `source_snapshot_hash`
- `effective_policy_id`
- `effective_policy_hash`
- `lifecycle_status`
- `compiler_version`
- `compiled_bundle`
- `compiled_bundle_hash`
- `checker_names` (derived index projection)
- `checker_configs` (derived index projection)
- `created_by`
- `created_at`
- `supersedes_pre_submit_checker_policy_id`
- `superseded_at`

Generated server-side from `EffectiveProjectSubmissionArtifactPolicy`, then
persisted and locked for the project guide version before tasks enter the
contributor pipeline. Every task under the same active project guide version reuses
that guide version's project pre-submit checker bundle. If the guide version
does not cover the task set, activation is blocked and the guide is improved or
the work is split into another project/guide. The task stores
`locked_pre_submit_checker_bundle_hash`, which equals
`PreSubmitCheckerPolicy.compiled_bundle_hash`; it does not own a newly derived
policy or newly compiled checker.

Task context APIs read this already-stamped context. `work-context` and
`submission-requirements` return task-visible contributor-safe guide and requirement
projections from the locked rows. `locked-context` requires the registered
covered Project Manager permission or an explicitly authorized Operator/Audit
projection and exposes the full
locked source snapshot, effective policy, pre-submit checker, post-submit
checker, review, and revision provenance. Compensation provenance comes from
the independently frozen `TaskAssignment` or `ReviewLease` version and is not
guide context. None of these reads
recompute from the current active guide.

Approval creates a project-scoped `PreSubmitCheckerPolicy` row with lifecycle
status `compiled`. The trusted compiler writes the immutable `compiled_bundle`
JSON and `compiled_bundle_hash` in the same approval path. The compiled bundle
is the canonical checker source of truth. It is stored as a structured snapshot,
not arbitrary executable code. `compiled_bundle_hash` binds the exact compiled
logic to `effective_policy_hash`. `checker_names` and `checker_configs` are
derived index projections only; they must be regenerated from `compiled_bundle`
and must not disagree with it.

The compiler must prove semantic coverage: every enforceable
`EffectiveProjectSubmissionArtifactPolicy` rule must produce deterministic
checker logic. It rejects checker specifications that omit a required artifact,
skip an evidence rule, weaken severity, omit a platform default, or produce a
bundle whose rules are not traceable back to the effective project policy.

For v0.1, task-specific runtime parameters come only from trusted task-contract
fields already owned by Workstream, such as task id, expected output, declared
artifact labels, or acceptance criteria references. There is no free-form
parameter map. Runtime parameters may fill placeholders in the locked checker
bundle, but they cannot change required checks, severity, allowed storage,
forbidden artifacts, hash algorithm, or platform defaults.

Compiled checker bundles, hashes, and effective-policy bindings are immutable.
Changing policy or compiler output creates a new row with
`supersedes_pre_submit_checker_policy_id`. During that locked replacement
transaction, Workstream may update only the prior row's lifecycle closeout
metadata (`lifecycle_status = superseded`, `superseded_at`).

The generated checker order is deterministic:

1. packet shape
2. artifact manifest presence
3. artifact hash validation
4. storage reference safety
5. forbidden artifact blocking
6. required artifact presence
7. evidence requirement presence
8. contributor attestation validation
9. low-quality artifact warnings

Pre-submit has two API paths:

```text
POST /tasks/{id}/submission-precheck
200 PreSubmitCheckResponse(status="failed", eligible_to_submit=false, results=[...])
```

```text
POST /tasks/{id}/submissions
422 DomainError(code="pre_submission_checker_failed", details={status, eligible_to_submit, results})
```

Blocking pre-submit failures prevent submission creation, create no submission
row, no submission version, no task transition to `submitted`, and no
submission-created audit event. Workstream still writes a task audit event named
`pre_submission_check_failed` with the structured checker result for project
operators. They do not return review decision values.

## PostSubmitCheckerPolicy

Fields:

- `id`
- `project_id`
- `guide_id`
- `guide_version`
- `source_snapshot_id`
- `source_snapshot_hash`
- `effective_policy_id`
- `effective_policy_hash`
- `pre_submit_checker_policy_id`
- `pre_submit_checker_bundle_hash`
- `required_checkers`
- `warning_checkers`
- `blocking_severities`
- `policy_hash`
- `policy_body`
- `lifecycle_status`
- `approved_by_admin_role_grant_id`
- `approved_by_actor_profile_id`
- `approved_at`
- `supersedes_policy_id`
- `superseded_at`
- `superseded_by_role`
- `superseded_by_actor`
- `supersession_kind`
- `supersession_reason`
- `created_by`
- `created_at`

`policy_body` is the canonical source for post-submit checker execution. The
hash is `sha256(canonical_json(policy_body))`. `required_checkers`,
`warning_checkers`, and `blocking_severities` are query projections and must
match `policy_body`.

`lifecycle_status` is `compiled`, `approved`, or `superseded`. The derivation
and compiler continuation creates `compiled` records. Guide activation requires
an `approved` generated policy with setup-role approval provenance and exact
`source_snapshot_id/hash`, `effective_policy_id/hash`, and
`pre_submit_checker_policy_id` plus pre-submit checker bundle hash matching the
active setup context. Server-owned approval/correction APIs move compiled
post-submit policies into that approved state or supersede rejected generated
output for regeneration. Superseded records retain actor, role, time, bounded
reason, policy hash, and policy body provenance. A replacement links through
`supersedes_policy_id` only when it replaces a correction-requested policy in
the exact same setup context; bounded correction feedback reaches setup-time
derivation, and Workstream rejects an identical replacement policy hash.

For generated setup, `PostSubmitCheckerPolicyDerivationAgent` runs only after a
authorized covered Project Manager approves the derived
`SubmissionArtifactPolicy`, producing an approved
`EffectiveProjectSubmissionArtifactPolicy` and compiled project
`PreSubmitCheckerPolicy`. The agent receives bounded guide-source material,
guide sufficiency summary, effective policy summary, pre-submit checker
summary, and the registered post-submit checker catalog. It returns a
constrained checker specification, unsupported required-check gaps, bounded
reasons, and setup notes. It does not produce executable code and it does not
judge contributor submissions at runtime.

The constrained derivation output contains:

- `required_checkers`
- `warning_checkers`
- `blocking_severities`
- `reasons`
- `unsupported_required_checks`
- `setup_notes`

Setup-run summaries persist bounded metadata from that output: checker lists,
server-owned agent name/version, reason count, sanitized evidence refs,
unsupported checker reason codes, and setup note count. They do not persist
free-form agent rationales, setup-note text, source excerpts, local paths,
exact source hashes, replayable refs, or contributor submission data. Agent-returned
agent names and versions are treated as untrusted metadata; persisted setup
summaries use Workstream's server-owned derivation agent identity.

Evidence references in `reasons` and unsupported-checker gaps are bounded
setup pointers such as `project_guide`, `source_item:N`, `sufficiency_report`,
`effective_policy`, and `pre_submit_checker`. The registered checker catalog is
agent input, not an evidence reference. Evidence refs must not contain local
filesystem paths, signed URLs, credentials, private storage locators, raw source
excerpts, or contributor submission data.

When a task locks its project context, Workstream stamps
`locked_post_submit_checker_policy_body` by copying the persisted project
`PostSubmitCheckerPolicy.policy_body`. Submissions copy that body from the task,
and durable checker runs copy it from the submission. Checker execution
validates the body against the stamped hash, schema version, supported
`compiler_version`, and the locked body's internal structure, then executes from
that locked body, not from mutable project setup rows. Later project policy
edits therefore cannot change already locked task, submission, or checker-run
behavior. A future platform default-checker list change requires a separately
approved and security-reviewed versioning or migration path instead of silently
reinterpreting old locked bodies.

The policy body includes:

- `schema_version`
- `compiler_version`
- `project_id`
- `guide_version`
- `default_checkers`
- `required_checkers`
- `warning_checkers`
- `execution_checkers`
- `blocking_severities`

`execution_checkers` is the complete ordered durable checker list. It is
compiled from Workstream default durable checkers plus project-specific
required and warning checker classifications, and it is covered by
`policy_hash`. `default_checkers` must exactly match the platform-owned default
durable checker list at compile time. Runtime treats that stamped list as locked
policy data and validates it through `policy_hash` and the frozen default-list
snapshot for the stamped `compiler_version`, not by comparing it to the mutable
server constant. Default-only projects leave `required_checkers` and
`warning_checkers` empty; they still execute every default checker through
`execution_checkers`.

The trusted post-submit compiler owns the policy body. It rejects unknown
checker names, duplicate or conflicting classifications, warning-only
reclassification of default checkers, malformed locked-body drift, and
blocking-severity downgrades. Platform blocking severities are `critical` and `high`; project
policy may add stricter blocking severities but cannot remove those defaults.

Example:

```json
{
  "schema_version": "post_submit_checker_policy.v1",
  "compiler_version": "workstream-post-submit-compiler-v0.1",
  "project_id": "project-id",
  "guide_version": "v1",
  "default_checkers": [
    "check_submission_packet",
    "check_policy_context_present",
    "check_evidence_present",
    "check_evidence_integrity",
    "check_required_files",
    "check_forbidden_files",
    "check_confidentiality_attestation",
    "check_low_quality_generated_artifacts"
  ],
  "required_checkers": [],
  "warning_checkers": [],
  "execution_checkers": [
    "check_submission_packet",
    "check_policy_context_present",
    "check_evidence_present",
    "check_evidence_integrity",
    "check_required_files",
    "check_forbidden_files",
    "check_confidentiality_attestation",
    "check_low_quality_generated_artifacts"
  ],
  "blocking_severities": ["critical", "high"]
}
```

Post-submit checker policy governs durable internal checker runs after a submission is finalized. It does not replace the generated project pre-submit checker policy.

Migration note: the `0008_post_submit_checker_policy` migration adds explicit
post-submit policy hash, body, and lock columns. Existing local v0.1 checker
policy rows without policy hashes are intentionally not backfilled into
authority. They must be recreated or repaired through the project setup
lifecycle. Existing non-draft task, submission, or checker-run rows from the
construction database block the migration with an explicit preflight error
because Workstream cannot truthfully infer which post-submit policy body and
hash governed those runtime records. After the migration, runtime records fail
closed when a task, submission, or checker run lacks valid
`locked_post_submit_checker_policy_*` context.

Migration note: the `0014_post_submit_setup` migration adds required
post-submit policy provenance fields that bind a compiled policy to guide,
source snapshot, effective project policy, and pre-submit checker bundle
context. Existing construction-era `checker_policies` rows cannot be truthfully
backfilled into that provenance, so the migration fails closed until those local
draft-era rows are reset and recreated through project setup.

Migration note: the `0015_post_submit_correction` migration replaces the
single-row project/guide-version uniqueness rule with uniqueness for current
`compiled` or `approved` rows. Superseded rows remain append-only and retain
their policy body/hash, supersession kind/reason, actor/role/time provenance,
and any same-context correction replacement link. Correction lookup is scoped
to the exact guide, source
snapshot, effective project policy, and pre-submit checker provenance so stale
feedback cannot influence a later setup context.

## ReviewPolicy

Fields:

- `id`
- `project_id`
- `guide_version`
- `allowed_decisions`
- `minimum_finding_fields`
- `sla_hours`
- `created_at`

## RevisionPolicy

Fields:

- `id`
- `project_id`
- `guide_version`
- `max_revision_rounds`
- `revision_deadline_hours`
- `allowed_resubmission_states`
- `reviewer_reassignment_rule`
- `created_at`

Limit or deadline exhaustion blocks further preparation and submission; it does
not synthesize a reject Review. Project Guide context selection is deterministic,
not policy-selected: exact prior Submission identity/activation-sequence match
keeps context, any different valid active pair rebases forward or backward, and
missing or unsafe active context blocks for manager repair.

## ContributionPolicy

Fields:

- `id`
- `project_id`
- `name`
- `status`: `draft | active | retired`
- `current_published_version_id`
- `created_by`
- `created_at`
- `retired_by`
- `retired_at`

At most one policy is active for new work in one project. New TaskAssignments
and ReviewLeases require its published version; missing configuration is not an
implicit unpaid rule.

## ContributionPolicyVersion

Fields:

- `id`
- `contribution_policy_id`
- `project_id`
- `version_number`
- `status`: `draft | published | retired`
- publication and retirement actor/timestamp fields

Published and retired versions are immutable. TaskAssignment freezes the
submitter version; ReviewLease independently freezes the reviewer version.

## ContributionRule

Fields:

- `id`
- `contribution_policy_version_id`
- `project_id`
- `contribution_type`: `accepted_submission | completed_review`
- `compensation_mode`: `compensated | unpaid`

Every publishable version contains exactly one rule for each contribution type.
An unpaid rule has no award definitions. A compensated rule has one or two:
at most one `money` and one `project_points` definition.

## ContributionAwardDefinition

Fields:

- `id`
- `contribution_rule_id`
- `contribution_policy_version_id`
- `project_id`
- `contribution_type`
- `instrument_type`: `money | project_points`
- `unit_code`
- `quantity` as a `NUMERIC(38, 18)` fixed-point decimal greater than zero
- `adapter_binding_id`

API quantities are bounded decimal strings; binary floating point, exponent
notation, non-finite values, zero, negatives, overflow, and excess precision
are rejected rather than rounded. Money units are uppercase configured ISO 4217
codes. Project-points units have project-scoped identity
`(project_id, unit_code)`. Published definitions are immutable and project,
instrument, and unit consistent with the referenced adapter binding.

## ProjectCompensationAdapterBinding

Fields:

- `id`
- `project_id`
- `instrument_type`: `money | project_points`
- `adapter_actor_id`
- `route_key`
- `status`: `active | suspended | retired`
- creation, suspension, and retirement actor/timestamp fields

Provider endpoints, credentials, and tokens are deployment secrets, not domain
fields. At most one binding is active per project and instrument.

## ProjectLesson

Fields:

- `id`
- `project_id`
- `guide_version`
- `source`
- `lesson_type`
- `summary`
- `recommended_change`
- `status`
- `created_by`
- `created_at`
- `closed_at`

Lesson types:

- guide_update
- checker_update
- reviewer_policy_update
- revision_policy_update
- queue_policy_update
- contribution_policy_update
- risk_note

Status:

- open
- accepted
- rejected
- implemented

## Task

Fields:

- `id`
- `project_id`
- `locked_guide_version`
- `locked_guide_source_snapshot_id`
- `locked_guide_source_snapshot_hash`
- `locked_effective_project_submission_artifact_policy_id`
- `locked_effective_project_submission_artifact_policy_hash`
- `locked_pre_submit_checker_policy_id`
- `locked_pre_submit_checker_bundle_hash`
- `locked_post_submit_checker_policy_id`
- `locked_post_submit_checker_policy_version`
- `locked_post_submit_checker_policy_hash`
- `locked_post_submit_checker_policy_body`
- `locked_review_policy_version`
- `locked_revision_policy_version`
- `source_type`
- `source_ref`
- `source_payload_hash`
- `import_batch_id`
- `external_task_id`
- `title`
- `description`
- `task_type`
- `difficulty`
- `skill_tags`
- `estimated_time_minutes`
- `status`
- `acceptance_criteria`
- `rejection_criteria`
- `deadline_at`
- `created_by`
- `assigned_to`
- `created_at`
- `updated_at`

Status:

- draft
- screening
- ready
- claimed
- in_progress
- submitted
- evaluation_pending
- review_pending
- needs_revision
- accepted
- rejected
- cancelled

Source type:

- manual
- markdown_import
- csv_import

External origin adapters are later work. When added, they normalize into this task shape instead of creating a separate task lifecycle.

The task id points to the locked task contract. That contract includes the guide
version, guide source snapshot id/hash, effective project submission artifact
policy id/hash, generated project pre-submit checker policy id/bundle hash,
post-submit checker policy id/version/hash, review policy version, revision
policy version, acceptance criteria, derived display summaries, and skill tags.
Contributors submit against the task id; they do not restate policy versions.

Durable post-submit checker execution uses
`locked_post_submit_checker_policy_id`,
`locked_post_submit_checker_policy_version`, and
`locked_post_submit_checker_policy_hash`.
Contributor-facing task responses omit post-submit checker policy internals.

## TaskAssignment

Fields:

- `id`
- `task_id`
- `contributor_id`
- `assigned_by`
- `submitter_contribution_policy_version_id`
- `assigned_at`
- `accepted_at`
- `released_at`
- `status`

## Submission

Fields:

- `id`
- `task_id`
- `task_assignment_id`
- `contributor_id`
- `version`
- `status`
- `summary`
- `package_uri`
- `package_hash` (legacy caller input, never canonical artifact lineage)
- `artifact_hash` (server-derived verified lineage)
- `artifact_hash_manifest`
- `contributor_attestation`
- `locked_guide_version`
- `locked_guide_id`
- `locked_guide_activation_sequence`
- `locked_guide_source_snapshot_id`
- `locked_guide_source_snapshot_hash`
- `locked_effective_project_submission_artifact_policy_id`
- `locked_effective_project_submission_artifact_policy_hash`
- `locked_pre_submit_checker_policy_id`
- `locked_pre_submit_checker_bundle_hash`
- `locked_post_submit_checker_policy_id`
- `locked_post_submit_checker_policy_version`
- `locked_post_submit_checker_policy_hash`
- `locked_post_submit_checker_policy_body`
- `locked_review_policy_version`
- `locked_revision_policy_version`
- `submitted_at`
- `locked_at`
- `supersedes_submission_id`
- `revision_context_preparation_id` (revision submissions only)

The contributor submission packet supplies the task id, summary, outputs,
artifact hashes, evidence references, and contributor attestation. Workstream assigns the
submission version, creates evidence ids, and stamps locked guide source,
submission artifact, effective project policy, pre-submit checker, post-submit
checker, review, and revision policy provenance from trusted
task/project state. The contributor does not provide submission version, evidence
ids, checker results, checker run ids, guide versions, source snapshots,
effective project policy ids/hashes, pre-submit checker ids/bundle hashes,
post-submit checker policy ids/versions/hashes, review policy versions, or
revision policy versions. Submitter award eligibility remains governed by the
immutable TaskAssignment-frozen `ContributionPolicyVersion` and is not restated
on the submission.

Implementation note: submissions stamp explicit post-submit checker provenance
from the task. Durable `CheckerRun` creation uses those
`locked_post_submit_checker_policy_*` fields and fails closed when they are
missing, mismatched, deleted, stale, or unauthorized.
Contributor-facing submission responses omit post-submit checker policy internals.

Status:

- submitted

Submission status records the immutable packet version state. Task status carries
evaluation, human review, revision, acceptance, and rejection lifecycle states.

## EvidenceItem

Fields:

- `id`
- `submission_id`
- `type`
- `label`
- `uri`
- `hash`
- `size_bytes`
- `locked_at`
- `metadata`
- `created_at`

Types:

- log
- screenshot
- test_result
- package
- diff
- note
- external_reference

## CheckerRun

Fields:

- `id`
- `task_id`
- `submission_id`
- `submission_version`
- `status`
- `routing_recommendation`
- `outcome_source`
- `trigger_source`
- `attempt_number`
- `supersedes_checker_run_id`
- `is_current_for_submission`
- `started_at`
- `completed_at`
- `runner_version`
- `locked_guide_version`
- `locked_post_submit_checker_policy_id`
- `locked_post_submit_checker_policy_version`
- `locked_post_submit_checker_policy_hash`
- `locked_post_submit_checker_policy_body`
- `locked_review_policy_version`
- `locked_revision_policy_version`
- `package_hash`
- `artifact_hash_manifest`
- `artifact_manifest_hash`
- `summary`

Status:

- queued
- running
- completed
- failed

Run `passed`/`warning`/`failed` summary is derived from checker result counts, not stored as run status.

Routing recommendation:

- not_evaluated
- allow_review
- needs_revision
- checker_retry
- task_setup_blocked

`routing_recommendation` is a checker-side workflow hint, not a human review decision. `allow_review` means the automated checker found no blocking issue and the submission may proceed to human review. It must not be stored or reported as `accept`.

`task_setup_blocked` means the task's locked contract or policy context is incomplete, stale, or unsafe to review. It is an internal project-manager route, not a contributor-facing revision outcome.

## CheckerResult

Fields:

- `id`
- `checker_run_id`
- `checker_name`
- `status`
- `severity`
- `message`
- `suggested_fix`
- `contributor_message`
- `contributor_suggested_fix`
- `evidence_refs`
- `contributor_evidence_refs`
- `contributor_visible`
- `metadata`
- `created_at`

Status:

- passed
- warning
- failed

Severity:

- info
- low
- medium
- high
- critical

## CheckerDefinition

Fields:

- `id`
- `checker_id`
- `name`
- `phase`
- `default_severity`
- `default_blocks_review`
- `version`
- `contributor_visible`
- `description`
- `created_at`
- `retired_at`

Phase:

- project_activation
- task_screening
- submission_quality
- pre_review_gate
- lifecycle_transition
- compensation_fulfillment_reconciliation

The checker registry prevents project guide templates, checker policies, and implementation code from drifting into different checker names for the same rule.

`pre_review_gate` is a checker phase, not a task status. The v0.1 task status during this phase is `evaluation_pending`.

## Future ReadinessCertificate

Current status:

Optional later record. v0.1 stores readiness proof on `CheckerRun`.

Fields:

- `id`
- `submission_id`
- `checker_run_id`
- `artifact_hash_manifest`
- `blocking_failures_count`
- `warnings_count`
- `ready_for_review`
- `issued_by`
- `issued_at`
- `invalidated_at`

Purpose:

If added later, the readiness certificate records the exact checker run and artifact hashes that allowed a submission to enter human review.

For v0.1, the current `CheckerRun` is the readiness proof. If any submitted artifact changes, a new submission version and checker run are required.

## ReviewQueueEntry And ReviewLease

`ReviewQueueEntry` immutably anchors one exact finalized Submission and its
current successful admitting CheckerRun. Mutable routing state carries
preferred/open/closed lifecycle, original queue age, and current preference.
The reviewer current-work API returns an active lease, one server-selected
offer, or none; it never exposes the full backlog.

`ReviewLease` is the permanent identity of one claim attempt. It stores the
canonical human reviewer ActorProfile ID, queue/Submission lineage, database
lease times, disposition, and the independently frozen reviewer
ContributionPolicyVersion. PostgreSQL enforces one active lease per reviewer and
queue entry.

`ReviewPacketManifest` is an immutable REV semantic projection over the exact
lease, Submission, admitting CheckerRun/results, stamped context, response
evidence, and ART binding IDs. It contains no bytes, digest, provider locator,
signed URL, receipt, scratch path, or AUTH matrix data.

## Review

Fields:

- `id`
- `submission_id`
- `review_lease_id`
- `predecessor_review_id`
- `reviewer_id`
- `decision`
- `summary`
- `confidence`
- `acceptance_evidence_refs`
- `locked_guide_version`
- `locked_review_policy_version`
- `created_at`
- `completed_at`

The Review and its submitted findings/resolutions are immutable. Later rounds
append a new Review following the Submission predecessor chain.

Decision:

- accept
- needs_revision
- reject

## ReviewFinding

Fields:

- `id`
- `review_id`
- `finding_kind`: `blocking | advisory`
- `area`
- `issue`
- `required_fix`
- `created_at`

## ReviewEvidenceArtifact

Fields:

- `id`
- `project_id`
- `review_id` (nullable, exactly one purpose owner)
- `review_finding_id` (nullable, exactly one purpose owner)
- `submission_finding_response_id` (nullable, exactly one purpose owner)
- `finding_resolution_id` (nullable, exactly one purpose owner)
- `artifact_binding_id`
- `evidence_purpose`
- `created_by_actor_id`
- `created_at`

This immutable REV relation binds one ART-finalized ArtifactBinding to the exact
review, finding, response, or resolution evidence slot. Exactly one purpose owner is set,
all lineage is same-project and same-task, and the row stores no bytes, digest,
provider locator, signed URL, receipt, scratch path, or credentials.

## SubmissionFindingResponse And FindingResolution

`SubmissionFindingResponse` immutably binds one unresolved blocking finding to
the assigned submitter's response text, optional finalized evidence binding,
exact preparation head, and new Submission. Advisory responses are optional
unless locked policy requires them.

`FindingResolution` is appended by the later Review for each required prior
finding. Its result is `resolved`, `unresolved`, or `not_applicable`; it carries
bounded rationale/evidence and never edits the finding or response.

## RevisionContextPreparation

Fields:

- `id`
- `task_id`
- `originating_review_id`
- `source_task_assignment_id`
- `target_task_assignment_id`
- `prior_submission_id`
- `prior_submission_version`
- `next_submission_version`
- `prior_locked_guide_id`
- `prior_locked_guide_version`
- `prior_locked_guide_activation_sequence`
- `next_locked_guide_id`
- `next_locked_guide_version`
- `next_locked_guide_activation_sequence`
- `prior_locked_effective_project_submission_artifact_policy_hash`
- `next_locked_effective_project_submission_artifact_policy_hash`
- `prior_locked_pre_submit_checker_bundle_hash`
- `next_locked_pre_submit_checker_bundle_hash`
- `prior_locked_review_policy_version`
- `next_locked_review_policy_version`
- `prior_locked_revision_policy_version`
- `next_locked_revision_policy_version`
- `outcome`: `kept | rebased | blocked`
- `direction`: `forward | backward | null`
- `context_digest`
- `predecessor_preparation_id`
- `preparation_sequence`
- `rebase_reason`
- `change_summary`
- `prepared_by`
- `audit_event_id`
- `created_at`

Purpose:

This immutable Review-rooted record is created before a contributor resumes a
human-review revision. Exact prior Submission guide identity/activation-sequence
match with the currently active guide keeps context. Any different valid active
pair rebases forward or backward. Missing, inconsistent, revoked, or unsafe
context blocks for manager repair. Task Context returns the validated chain
head. No guide rebase occurs during review; the reviewer reads the context
stamped on the leased Submission.

Revision preparation never rebases award eligibility. Submitter eligibility
remains governed by the TaskAssignment-frozen `ContributionPolicyVersion`; each
new ReviewLease independently freezes the then-current
`ContributionPolicyVersion` for reviewer contributions.

The contributor and reviewer history show prior/next identity, activation
sequence, direction, reason, and change summary. No ContributionPolicyVersion is
stored in this preparation.

## FinalAcceptance

Fields:

- `id`
- `project_id`
- `task_id`
- `submission_id`
- `source_review_id`
- `accepted_submitter_id`
- `accepted_at`
- `recorded_by`
- `policy_context_ref`

Purpose:

This immutable REV-owned internal fact is created only inside the authorized
`Review(accept)` transaction. Existing `Submission` is already the version
identity, so the stored FK is `submission_id`; no SubmissionVersion entity or
`submission_version_id` alias is introduced. `recorded_by` is the canonical
human reviewer `ActorProfile.id` on the source Review and ReviewLease.
`policy_context_ref` is a foreign key to the exact immutable `ReviewPolicy.id`
whose project and guide version match the reviewed Submission context.

PostgreSQL enforces `UNIQUE(task_id)`, `UNIQUE(source_review_id)`, and
`UNIQUE(submission_id)` plus same-project/task/Submission/Review/submitter/
reviewer/policy lineage. There is no public/manual create API and no separate
authorization action. `needs_revision` and `reject` create none. Accept/reject
are terminal in v0.1; no adjudication or replacement-acceptance path exists.
Reviewer-quality sampling is a non-mutating audit and never delays or changes
this record.

## ContributionRecord

Fields:

- `id`
- `project_id`
- `task_id`
- `submission_id`
- `contribution_type`: `completed_review | accepted_submission`
- `contributor_id`
- `source_review_id`
- `source_review_lease_id`
- `source_final_acceptance_id`
- `source_task_assignment_id`
- `artifact_hash`
- `contribution_policy_version_id`
- `created_at`

Purpose:

The record is immutable. Every valid recorded human Review creates one reviewer
`completed_review` contribution with direct Review and ReviewLease lineage.
`Review(accept)` creates FinalAcceptance; exactly one submitter
`accepted_submission` consumes that fact plus the exact TaskAssignment.
`needs_revision` and `reject` create no FinalAcceptance or submitter record.

Reviewer rows require `source_review_id` and `source_review_lease_id` and have
null FinalAcceptance/assignment sources. Submitter rows require
`source_final_acceptance_id` and `source_task_assignment_id` and have null
direct Review/lease sources. Partial unique constraints enforce one
`completed_review` per Review and one `accepted_submission` per
FinalAcceptance; database checks reject mixed or incomplete source shapes. The
record carries the exact Submission, actor, frozen contribution policy, and
stabilized artifact-hash lineage. Compensation awards may reference it but do
not replace it; reputation projection remains deferred.

## CompensationAward

Fields:

- `id`
- `project_id`
- `contribution_record_id`
- `contributor_id`
- `contribution_policy_version_id`
- `award_definition_id`
- `adapter_binding_id`
- `instrument_type`: `money | project_points`
- `unit_code`
- `quantity` as the definition's exact `NUMERIC(38, 18)` decimal
- `created_at`
- `correlation_id`

The award is immutable and copies its instrument, unit, quantity, and binding
from the published definition without conversion or rounding. Explicit unpaid
rules create no award. At most one award exists per contribution and instrument
type; fulfillment state is not stored on the award.

## CompensationFulfillmentReceipt

Fields:

- `id`
- `compensation_award_id`
- `project_id`
- `adapter_binding_id`
- `external_event_id`
- `reported_status`: `fulfilled | failed`
- `external_reference`
- `fulfilled_quantity`
- `fulfilled_at`
- `failure_code`
- `reported_at`
- `received_at`
- `correlation_id`

Receipts are immutable. `external_event_id` is a binding-scoped unique 1-128
character opaque ASCII token from `[A-Za-z0-9._:-]`. Fulfilled receipts require
the exact award `NUMERIC(38, 18)` quantity, a non-secret external reference with
the same bounds, and a timestamp. Failed receipts require a closed Workstream
failure code and null quantity, time, and external reference. Free-form provider
messages/codes, payloads, headers, signatures, credentials, URLs, and metadata
are never persisted, logged, emitted, exported, or returned. One award has at
most one fulfilled receipt.

## CompensationStatusProjection

Fields:

- `compensation_award_id`
- `delivery_status`: `pending_delivery | acknowledged_by_adapter`
- `fulfillment_status`: `pending | failed | fulfilled`
- `latest_receipt_id`
- `external_reference`
- `last_failure_code`
- delivery, fulfillment, and update timestamps

This projection is mutable and rebuildable. ContributionRecord,
CompensationAward, outbox delivery history, and fulfillment receipts remain the
authoritative records.

## ReputationEvent

Fields:

- `id`
- `actor_id`
- `task_id`
- `submission_id`
- `contribution_record_id`
- `event_type`
- `skill_tags`
- `weight`
- `score_delta`
- `reason`
- `created_at`

Event types:

- accepted
- needs_revision
- rejected
- revision_closed
- contribution_recorded
- compensation_fulfilled
- review_quality_sampled
- review_feedback_flagged

This entire record is deferred to a separate reputation initiative. Future
review-quality inputs are offline non-product evidence: they cannot alter an
immutable Review, create another product decision, or introduce adjudication
state.

## AuditEvent

Fields:

- `id`
- `entity_type`
- `entity_id`
- `event_type`
- `from_status`
- `to_status`
- `actor_id`
- `external_subject`
- `external_issuer`
- `actor_roles`
- `claim_snapshot`
- `auth_source`
- `is_dev_auth`
- `reason`
- `event_payload`
- `created_at`

Audit events are append-only.

Authority evidence extends the same row with `event_domain`, `event_version`,
database-owned `occurred_at`, request/correlation IDs, an actor-reference
namespace, and optional bounded target actor, matched grant, permission,
project, resource, denial, invalidation, idempotency-reference, and shallow
before/after fact fields. It does not create a parallel event table.

`actor_roles`, `claim_snapshot`, and `event_payload` are legacy-only data
surfaces. Authority rows keep them at `[]`, `{}`, and `{}` respectively, use
`auth_source = local_authority`, and leave external issuer, external subject,
and lifecycle status fields null. They never store tokens, claims, emails,
request bodies, issuer URLs, key material, or policy bodies. Typed validation
and database constraints reject mixed legacy/authority shapes.

v0.1 audit storage is the existing Workstream `audit_events` ledger. Task
Lifecycle events and authority events share the canonical audit repository so
operators can reconstruct why an actor was allowed or denied. Authority events
record bounded actor, matched grant/permission, scope, resource, reason, and
before/after facts without raw claims or unnecessary profile data. The shared
repository participates in its caller's transaction and does not commit or
open an independent session.

## Required Invariants

- a task must belong to a project
- a task records the project guide version used at creation
- a task cannot enter ready without passing screening; recovery uses only its
  registered scoped permission and cannot bypass missing task policy context
- a submission must belong to a task
- a review must belong to a submission
- an accepted task must have exactly one FinalAcceptance linked to its accepting
  Review and versioned Submission
- every valid recorded human review must create one reviewer `completed_review`
  contribution
- an accepted task must additionally create one submitter
  `accepted_submission` contribution sourced from FinalAcceptance
- `needs_revision` and `reject` must not create FinalAcceptance or a submitter
  contribution
- FinalAcceptance is unique per task, source Review, and Submission and has no
  independent creation API/action
- v0.1 has no adjudication state/action/queue/lease/decision/contribution or
  readiness dependency
- no compensation award exists without its contribution record
- a fulfilled award must have an immutable fulfillment receipt with the exact
  authorized quantity and external reference
- review-lifecycle v0.1 creates no reputation event; future reputation records
  must consume canonical contribution/review lineage without mutating it
- compensation award quantity is immutable after creation
- failed fulfillment may later receive one valid fulfilled receipt; a fulfilled
  award is terminal and rejects conflicting callbacks
- the mutable compensation projection never overrides award or receipt truth
- critical- and high-severity checker failures block review; registered
  recovery may retry or repair infrastructure but cannot create a review
  decision or erase checker evidence
- a checker run must reference the exact submission version and artifact hashes it evaluated
- the current checker run is the v0.1 readiness proof for the submission version that cleared automated checks
- a review cannot accept a submission if the checker run belongs to a different submission version
- every status transition creates an audit event
- every needs-revision decision has at least one unresolved blocking
  ReviewFinding
- every revision context rebase creates an audit event and preserves prior submission context
- every accept decision cites evidence
- repeated review/checker failures become ProjectLesson records
- submission artifacts are immutable after `locked_at`
- a changed artifact requires a new submission version
- task lifecycle status and compensation fulfillment status remain separate
