# Data Model

## Implementation Stack

The v0.1 persistence layer uses SQLAlchemy 2.x async models, Alembic migrations, and Pydantic schemas.

## Entity Overview

```text
ActorIdentity
  ActorProfile

Project
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
  PaymentPolicy
  ProjectLesson

Task
  Assignment
  Submission
    EvidenceItem
    CheckerRun
      CheckerResult
    ReadinessCertificate (later optional)
    Review
      ReviewFinding
    RevisionReplay
    RevisionContextPreparation
  ContributionRecord
  PaymentRecord
  ReputationEvent
  AuditEvent
```

## Actor Identity And Profile

Fields:

- `actor_id`
- `external_subject`
- `external_issuer`
- `email`
- `display_name`
- `last_seen_roles`
- `last_claim_snapshot`
- `auth_source`
- `is_dev_auth`
- `first_seen_at`
- `last_seen_at`
- `updated_at`

Actor identity comes from external Flow authentication. `external_issuer` plus
`external_subject` is the stable identity binding. Email is profile metadata and
must not be treated as the primary identity.

Workstream keeps `ActorIdentity` rows for local workflow continuity, audit
display, profile linkage, assignments, and later reputation records. It does
not own password authentication or primary login sessions. Workstream owns
product roles and exact resource authorization locally. Flow issuer plus subject
identifies the actor; it does not assign Workstream product roles. In the v0.1
bootstrap, route checks may still read trusted role claims from the current
`ActorContext` until the Workstream-owned role-assignment layer is introduced.

Actor registry refresh is bounded by
`WORKSTREAM_ACTOR_REGISTRY_REFRESH_INTERVAL_SECONDS`. Workstream verifies the
token on every protected request, but it may skip the local identity/profile
write when the stored identity is fresh, claims match, and required observed
profiles already exist. Setting the interval to `0` disables the skip path.

`ActorProfile` is the shared profile and eligibility model attached to an
`ActorIdentity`.

Fields:

- `id`
- `actor_id`
- `profile_type`
- `status`
- `skill_tags`
- `scope_type`
- `scope_id`
- `profile_metadata`
- `created_at`
- `updated_at`

Initial profile types:

- worker
- reviewer
- admin
- project_manager
- project_owner

Profile rows are metadata and workflow eligibility records. They do not grant
route access and are not the canonical Workstream role-assignment table. A
project owner profile is scoped source/contact metadata and is not the same as
a project manager permission role.

Initial profile statuses:

- `observed`: created or refreshed from a verified token role for audit/display
  metadata only; it is not workflow eligibility.
- `active`: created by an explicit profile workflow and allowed to satisfy
  workflow eligibility checks for that profile type.
- `disabled`: retained for audit but blocked from workflow eligibility.

Auth observation alone may create `observed` profiles, but it must not mark a
worker or reviewer profile `active`. Profile status can satisfy workflow
eligibility only when product authorization for the current request has already
passed.

The actor registry migration is intentionally destructive for the earlier
experimental `worker_profiles` and `reviewer_profiles` tables. Those obsolete
stores are dropped without compatibility backfill. Downgrade restores table
shape only; it does not preserve old experimental profile data.

`project_owner` is a scoped profile/contact relationship, not a route role. In
this chunk it is created from trusted relationship claims when present. Later
project setup/source-contact workflows may create the same scoped profile type
through an explicit trusted service path. It is not listed as a permission role
and does not grant operator access.

The trusted relationship claim key is
`claim_snapshot["workstream_relationship_profiles"]`. Each item must use
`profile_type = "project_owner"`, a non-empty `scope_type`, a non-empty
`scope_id`. Workstream stores only those scope identity fields in actor
identity/audit claim snapshots and stores server-owned profile metadata for the
observed relationship. Nested relationship `profile_metadata` from token claims
is discarded before persistence and is not route authorization.

Trusted v0.1 bootstrap request roles:

- admin
- project_manager
- worker
- reviewer
- finance
- auditor

`Operator` is a product persona, not a separate v0.1 permission role. In the application model, operator actions are performed by project managers, workers, reviewers, admins, or finance users depending on the action.

## Worker Actor Profile

Worker profile behavior is represented by `ActorProfile(profile_type="worker")`.
The public worker profile API remains worker-owned, but the persistence model is
the shared actor profile model.

## Reviewer Actor Profile

Reviewer profile behavior is represented by
`ActorProfile(profile_type="reviewer")`. Reviewer eligibility must be explicit;
observing a reviewer token role alone does not make the actor eligible for
review workflow.

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
request-body fields and not worker-facing guide content.

Runtime enforcement uses machine-readable policies attached to the guide version. Workstream does not parse guide prose at submission time to decide which artifact checks to run.

Project owners provide open-ended setup material and business terms. Workstream
does not force every project owner through one universal intake checklist.
Workstream evaluates guide sufficiency, derives machine-readable project policy,
and owns the internal controls. A Workstream actor with the `admin` or
`project_manager` role approves the guide-policy bundle before the guide can
activate.

Every task records the guide version active at creation or screening time before the task enters `READY`. Later source adapters must also lock the guide version during normalization before workers see the task.

When a task is claimed or moved to `IN_PROGRESS`, its locked guide and policy context does not change silently. A newer upstream guide version can only affect unclaimed work or a controlled revision path when policy allows it and the audit log records the reason.

Material changes require a new guide version or policy version. They include
guide source material, submission artifact policy, pre-submit checker
generation rules, post-submit checker policy, review policy, revision policy,
and payment policy.

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
- `content_cid` (future Flow Node binding)
- `media_type`
- `created_at`

`GuideSourceSnapshotItem` records each material item included in the guide
bundle. `source_kind` distinguishes inline markdown, URL-backed documentation,
repository docs, examples, rubrics, imported files, and other approved source
types. `durable_ref` is opaque and sanitized; it is not the temporary fetch
locator.

URL-backed guide ingestion is split into two identities:

- temporary fetch locator: used only by an approved retrieval adapter
- durable source record: opaque sanitized source ref plus content hash/CID

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
- `error_code`
- `error_summary`
- `created_by`
- `created_at`
- `updated_at`
- `started_at`
- `finished_at`

`ProjectSetupRun` is a non-authoritative orchestration ledger for automatic
project setup. It records that Workstream queued or attempted the guide
sufficiency and submission artifact policy derivation pipeline for one guide
source snapshot. It does not replace the source snapshot, sufficiency report,
submission artifact policy, effective project policy, or pre-submit checker
policy rows.

Statuses:

- `queued`
- `enqueue_failed`
- `running_sufficiency_agent`
- `sufficiency_blocked`
- `running_policy_derivation_agent`
- `policy_draft_ready`
- `setup_blocked`
- `failed`

The run references downstream truth by id/hash. Operators can read the latest
run through the project setup API to understand whether setup is still queued,
blocked by guide sufficiency, waiting on policy approval, or failed at the
queue/worker layer. Error summaries are bounded and redacted; server logs remain
the source for sensitive diagnostics.

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
for the project owner. Warnings can be acknowledged only by a Workstream actor
with the `admin` or `project_manager` role before activation.

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
- `approved_by_role`
- `approved_by_actor`
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
    "allowed_storage_schemes": ["local", "s3", "r2"],
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
  "approved_by_role": "project_manager",
  "approved_by_actor": "flow-project-manager",
  "approved_at": "2026-06-22T12:00:00Z"
}
```

Workstream derives this policy from project guide material after guide
sufficiency passes or passes with warnings. A Workstream actor with the
`admin` or `project_manager` role approves it after any sufficiency warnings are
acknowledged. Project owners and workers do not supply or approve this internal
policy schema.
`derivation_source` is server-owned. Manual/admin-created policies persist
`manual_admin_derivation`; policies created by the derivation agent persist
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
project setup as a policy conflict. It is not deferred to worker submission.

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
worker pipeline. Every task under the same active project guide version reuses
that guide version's project pre-submit checker bundle. If the guide version
does not cover the task set, activation is blocked and the guide is improved or
the work is split into another project/guide. The task stores
`locked_pre_submit_checker_bundle_hash`, which equals
`PreSubmitCheckerPolicy.compiled_bundle_hash`; it does not own a newly derived
policy or newly compiled checker.

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
8. worker attestation validation
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
- `guide_version`
- `required_checkers`
- `warning_checkers`
- `blocking_severities`
- `policy_hash`
- `policy_body`
- `created_at`

`policy_body` is the canonical source for post-submit checker execution. The
hash is `sha256(canonical_json(policy_body))`. `required_checkers`,
`warning_checkers`, and `blocking_severities` are query projections and must
match `policy_body`.

When a task locks its project context, Workstream stamps
`locked_post_submit_checker_policy_body` by copying the persisted project
`PostSubmitCheckerPolicy.policy_body`. Submissions copy that body from the task,
and durable checker runs copy it from the submission. Checker execution
validates the body against the stamped hash and executes from that locked body,
not from mutable project setup rows or the current default-checker constant.
Later project policy edits therefore cannot change already locked task,
submission, or checker-run behavior.

The policy body includes:

- `schema_version`
- `project_id`
- `guide_version`
- `default_checkers`
- `required_checkers`
- `warning_checkers`
- `execution_checkers`
- `blocking_severities`

`execution_checkers` is the complete ordered durable checker list. It is
computed from Workstream default durable checkers plus project required and
warning checkers, and it is covered by `policy_hash`.

Example:

```json
{
  "schema_version": "post_submit_checker_policy.v1",
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
  "required_checkers": [
    "check_policy_context_present",
    "check_submission_packet",
    "check_evidence_present"
  ],
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
  "blocking_severities": ["high"]
}
```

Post-submit checker policy governs durable internal checker runs after a submission is locked. It does not replace the generated project pre-submit checker policy.

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

## ReviewPolicy

Fields:

- `id`
- `project_id`
- `guide_version`
- `requires_second_review`
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
- `auto_reject_after_limit`
- `allowed_resubmission_states`
- `context_rebase_rule`
- `context_rebase_triggers`
- `reviewer_reassignment_rule`
- `created_at`

`context_rebase_rule` defines whether a revision attempt keeps prior context, rebases to current active context, or blocks for project-manager repair when guide or policy context changed. `context_rebase_triggers` names the guide or policy changes that require preparation before the worker resumes.

## PaymentPolicy

Fields:

- `id`
- `project_id`
- `guide_version`
- `base_amount`
- `currency`
- `payout_type`
- `revision_payment_rule`
- `rejection_payment_rule`
- `accepted_payment_rule`
- `created_at`

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
- payment_policy_update
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
- `locked_payment_policy_version`
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
- `base_amount`
- `currency`
- `payout_type`
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
policy version, payment policy version, acceptance criteria, derived display
summaries, locked payment policy amount, locked payment policy currency, locked
payment policy payout type, and skill tags.
Workers submit against the task id; they do not restate policy versions.

Durable post-submit checker execution uses
`locked_post_submit_checker_policy_id`,
`locked_post_submit_checker_policy_version`, and
`locked_post_submit_checker_policy_hash`.
Worker-facing task responses omit post-submit checker policy internals.

## Assignment

Fields:

- `id`
- `task_id`
- `worker_id`
- `assigned_by`
- `assigned_at`
- `accepted_at`
- `released_at`
- `status`

## Submission

Fields:

- `id`
- `task_id`
- `worker_id`
- `version`
- `status`
- `summary`
- `package_uri`
- `package_hash`
- `artifact_hash_manifest`
- `worker_attestation`
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
- `locked_payment_policy_version`
- `submitted_at`
- `locked_at`
- `supersedes_submission_id`

The worker submission packet supplies the task id, summary, outputs, artifact
hashes, evidence references, and worker attestation. Workstream assigns the
submission version, creates evidence ids, and stamps locked guide source,
submission artifact, effective project policy, pre-submit checker, post-submit
checker, review, revision, and payment policy provenance from trusted
task/project state. The worker does not provide submission version, evidence
ids, checker results, checker run ids, guide versions, source snapshots,
effective project policy ids/hashes, pre-submit checker ids/bundle hashes,
post-submit checker policy ids/versions/hashes, review policy versions, revision
policy versions, or payment policy versions.

Implementation note: submissions stamp explicit post-submit checker provenance
from the task. Durable `CheckerRun` creation uses those
`locked_post_submit_checker_policy_*` fields and fails closed when they are
missing, mismatched, deleted, stale, or unauthorized.
Worker-facing submission responses omit post-submit checker policy internals.

Status:

- submitted
- checking
- check_failed
- review_pending
- needs_revision
- accepted
- rejected

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
- `locked_payment_policy_version`
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

`task_setup_blocked` means the task's locked contract or policy context is incomplete, stale, or unsafe to review. It is an internal project-manager route, not a worker-facing revision outcome.

## CheckerResult

Fields:

- `id`
- `checker_run_id`
- `checker_name`
- `status`
- `severity`
- `message`
- `suggested_fix`
- `worker_message`
- `worker_suggested_fix`
- `evidence_refs`
- `worker_evidence_refs`
- `worker_visible`
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
- `worker_visible`
- `description`
- `created_at`
- `retired_at`

Phase:

- project_activation
- task_screening
- submission_quality
- pre_review_gate
- lifecycle_transition
- payment_reconciliation

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

## Review

Fields:

- `id`
- `submission_id`
- `reviewer_id`
- `decision`
- `summary`
- `confidence`
- `acceptance_evidence_refs`
- `locked_guide_version`
- `locked_review_policy_version`
- `created_at`
- `completed_at`

Decision:

- accept
- needs_revision
- reject

## ReviewFinding

Fields:

- `id`
- `review_id`
- `severity`
- `area`
- `issue`
- `required_fix`
- `evidence_ref`
- `created_at`

Severity:

- low
- medium
- high

## RevisionReplay

Fields:

- `id`
- `task_id`
- `prior_submission_id`
- `new_submission_id`
- `created_by`
- `created_at`

Each replay has items:

- `prior_finding_id`
- `fix_summary`
- `evidence_ref`
- `worker_claim_status`
- `reviewer_closure_status`

Worker claim status:

- fixed
- disputed
- not_applicable

Reviewer closure status:

- closed_fixed
- closed_rebutted
- partially_closed
- still_open
- obsolete

## RevisionContextPreparation

Fields:

- `id`
- `task_id`
- `prior_submission_id`
- `prior_submission_version`
- `next_submission_version`
- `prior_locked_guide_version`
- `next_locked_guide_version`
- `prior_locked_effective_project_submission_artifact_policy_hash`
- `next_locked_effective_project_submission_artifact_policy_hash`
- `prior_locked_pre_submit_checker_bundle_hash`
- `next_locked_pre_submit_checker_bundle_hash`
- `prior_locked_review_policy_version`
- `next_locked_review_policy_version`
- `prior_locked_revision_policy_version`
- `next_locked_revision_policy_version`
- `prior_locked_payment_policy_version`
- `next_locked_payment_policy_version`
- `context_rebased`
- `rebase_reason`
- `change_summary`
- `prepared_by`
- `audit_event_id`
- `created_at`

Purpose:

This record is created before a worker resumes a task in `NEEDS_REVISION` when guide or policy context must be checked for the next attempt. It does not mutate the prior submission. It records whether the next attempt keeps the prior context or rebases to the current active guide and policy context under revision policy.

The worker and reviewer packets must show the prior version, next version, rebase reason, and change summary when `context_rebased = true`.

## ContributionRecord

Fields:

- `id`
- `project_id`
- `task_id`
- `accepted_submission_id`
- `accepting_review_id`
- `worker_id`
- `locked_guide_version`
- `checker_run_id`
- `artifact_hash_manifest`
- `acceptance_evidence_refs`
- `skill_tags`
- `difficulty`
- `accepted_amount`
- `currency`
- `payout_type`
- `created_from_audit_event_id`
- `status`
- `accepted_at`
- `created_at`
- `exported_at`
- `voided_at`
- `void_reason`

Status:

- recorded
- exported
- voided

Purpose:

The contribution record is created when work is accepted. It certifies that a specific worker completed accepted work under a locked project guide with cited evidence. Payment records and reputation events attach to this record, but do not replace it.

## PaymentRecord

Fields:

- `id`
- `contribution_record_id`
- `task_id`
- `worker_id`
- `base_amount`
- `accepted_amount`
- `pending_amount`
- `paid_amount`
- `currency`
- `payout_type`
- `status`
- `payment_reference`
- `locked_payment_policy_version`
- `dispute_reason`
- `disputed_at`
- `accepted_at`
- `paid_at`

Status:

- none
- pending
- payout_submitted
- paid
- disputed

## PaymentAdjustment

Fields:

- `id`
- `payment_record_id`
- `actor_id`
- `old_amount`
- `new_amount`
- `currency`
- `reason`
- `evidence_ref`
- `created_at`

Payment adjustments are append-only. Accepted amount changes must use this record instead of editing payment values silently.

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
- paid
- review_overturned
- review_confirmed

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

v0.1 audit storage is the existing Workstream `audit_events` ledger. Task
lifecycle events and actor profile eligibility events both write there so
operators can reconstruct why an actor was allowed to claim, submit, or later
review. Actor profile audit events use `entity_type = "actor_profile"` and
record profile type, scope, and skill/status details in `event_payload`. A
future shared audit module can move the code boundary out of the task module,
but this chunk does not create a second audit source of truth.

## Required Invariants

- a task must belong to a project
- a task records the project guide version used at creation
- a task cannot enter ready without passing screening or documented admin override
- a submission must belong to a task
- a review must belong to a submission
- an accepted task must have at least one accepted submission
- an accepted task must create a contribution record
- no payment exposure exists without a contribution record
- a paid task must have an accepted payment record
- reputation events for accepted work must reference the accepted contribution record
- reviewer-quality reputation events must reference a review or audit source
- payment amount changes require a payment adjustment record
- disputed payments cannot become `paid` without a dispute resolution audit event
- high-severity checker failures block review unless an admin override is recorded
- a checker run must reference the exact submission version and artifact hashes it evaluated
- the current checker run is the v0.1 readiness proof for the submission version that cleared automated checks
- a review cannot accept a submission if the checker run belongs to a different submission version
- every status transition creates an audit event
- every needs-revision decision has at least one review finding
- every revision context rebase creates an audit event and preserves prior submission context
- every accept decision cites evidence
- repeated review/checker failures become ProjectLesson records
- submission artifacts are immutable after `locked_at`
- a changed artifact requires a new submission version
- task lifecycle status and payment status remain separate
