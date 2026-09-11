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
Iso4217CurrencyCode

Project
  ProjectCompensationAdapterBinding
  ProjectCompensationUnit
  ProjectGuide
  GuideSourceSnapshot
  GuideSourceSnapshotItem
  GuideSourceArtifactBinding
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
    FinalAcceptance (one accepting Review or authorized TASK routing source)
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
  deactivation attribution in the v0.1 baseline

Profile status is a guard, not a role or project grant.
Lifecycle invalidation effectiveness is component-scoped. Reactivating a
profile records `effective=false -> effective=true` for that profile projection
without asserting that its identity link, grants, or fixed-service admission
make the whole actor effective.

The closed service identity `workstream.compensation.adapter` identifies only
an eligible adapter-binding target. It has no service-action matrix row and no
action authority. ACTORS locks the exact active service profile and its active
service identity link before returning immutable eligibility facts; generic
service kind and every other fixed-service identity are insufficient.

### ActorIdentityLink

An identity link binds one canonical external issuer and opaque subject to one
ActorProfile. It has active/revoked state plus state-transition-guarded current
revocation and reactivation attribution. The v0.1 baseline enforces
complete attribution and bounded lifecycle reasons. AUTH-09D-B activates exact
link revoke/reactivate mutations. Append-only audit evidence preserves immutable
transition history; the current row carries only the latest state-compatible attribution.
Raw tokens, provider credentials, and full claim payloads are not stored.
The database enforces a unique `(issuer, subject)` pair across all links and, in
v0.1, at most one active identity link per ActorProfile. Revocation preserves
the immutable link and provenance; it does not free the pair for rebinding.
Link reactivation is component-scoped: it restores only that exact credential
binding, does not reactivate its ActorProfile or restore grants, and cannot
bypass final-effective-Access-Administrator preservation.

### AdminRoleGrant

Immutable administrative-grant history with role, compatible system/project
scope, target profile, issuing grant/actor, reason, active/revoked state, and
database time. Roles are Access Administrator, Operator, Project Manager,
Finance Authority, and Audit Authority.

### ProjectRoleGrant

Immutable exact-project contributor-grant history with role `submitter`
or `reviewer`, target profile, issuing Project Manager grant,
role-specific qualification snapshot, reason, and active/revoked state.

Contributor is the umbrella human product term. A human may hold separate
active `submitter` and `reviewer` grants for the same project;
each is revoked independently. Adjudicator grants are outside v0.1.
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

Current guide content is the versioned PDF/DOCX/PPTX original-document manifest
and private ArtifactStore objects. Guide metadata writes do not accept inline
Markdown; PostgreSQL stores no newly extracted document bodies.

Fields:

- `id`
- `project_id`
- `version`
- `contribution_policy_version_id`
- `status`
- `activation_sequence` (nullable only while draft; immutable after allocation)
- `retained_content_markdown` (read-only retained data; excluded from current APIs)
- `task_examples` (required ordered JSON list on new guide versions)
- `task_examples_hash` (domain-separated canonical commitment to that list)
- `change_summary`
- `approved_by`
- `effective_at`
- `created_by`
- `created_at`
- `updated_at`
- `superseded_at`
- `selected_review_policy_id`
- `selected_review_policy_generation`
- `selected_review_policy_hash`
- `selected_revision_policy_id`
- `selected_revision_policy_generation`
- `selected_revision_policy_hash`

The guide is versioned and human-facing. Uploaded PDF/DOCX/PPTX originals live
in private ArtifactStore/S3 objects; PostgreSQL stores their metadata and the
ordinary task-example text. The examples are representative inference inputs,
not selected assignments, and do not create Workstream Tasks. One project-level
policy proposal covers the project task set.

New guide versions require 1–100 examples with nonblank `content` (at most 65,536
characters), optional `title` (500 characters), and optional `labels` (at most
20, each 1–100 characters). The complete canonical UTF-8 JSON list is bounded at
128 KiB. Content, order and optional metadata are preserved. The list and its
hash are immutable; corrections require a new guide version. Retained null
inputs remain stored but cannot start new inference. No document bodies are
extracted into PostgreSQL.
`approved_by` and `effective_at` are server-written activation provenance, not
request-body fields and not contributor-facing guide content.

Guide status is exactly `draft | active | superseded`. Draft rows have null
activation sequence/approval/effective/superseded provenance. Active and
superseded rows retain one positive per-project activation sequence plus original
approval/effective provenance; superseded rows additionally retain
`superseded_at`. The planned 02A migration enforces this shape and immutable
chronology before Task stamping consumes it.

Draft guides may have no selected review/revision policy while the authorized
policy writer is unavailable. Active and superseded guides require both exact
identity triples, and PostgreSQL freezes those selections after activation.

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
of guide versioning. A published version affects work only when a later guide
activation binds it or controlled human-revision preparation atomically rebases
the continuing Task and TaskAssignment for the next attempt. Ordinary task and
review claims only copy the already-locked attempt lineage; prior Submissions,
ReviewLeases, Reviews, ContributionRecords, and CompensationAwards never drift.

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
captures uploaded-document declarations and the owning guide's task-example
commitment. It accepts document/upload items only. Downstream records bind to
`source_snapshot_id` and a server-derived `source_snapshot_hash` copied from
`GuideSourceSnapshot.bundle_hash`.

`bundle_hash` is:

```text
sha256(canonical_json(manifest_json))
```

Canonical JSON uses UTF-8, sorted object keys, and no insignificant whitespace.
The `guide_source_snapshot.task_examples` manifest contains the example hash
and count, the server-owned snapshot id and generation plus each
server-owned item id/order and its non-authoritative source metadata. Caller
hashes, content identifiers, excerpts, provider references, and fetch locators
are excluded. Each guide has one declared document set. Changing a declaration,
document bytes or task examples requires a new guide version, which receives
its own internal snapshot and initial setup.

## GuideSourceSnapshotItem

Fields:

- `id`
- `source_snapshot_id`
- `item_order`
- `source_kind`
- `source_label`
- `ingestion_adapter`
- `media_type`
- `created_at`

`GuideSourceSnapshotItem` records each uploaded document in the guide bundle.
Its current `source_kind` is `document` and `ingestion_adapter` is `upload`;
`source_label` is display metadata, never a fetch locator. Exact original bytes
are bound by committed `GuideSourceArtifactIngest` document custody and
`ArtifactContent`. The setup agent receives only scoped opaque handles, not S3
keys or credentials. No URL fetching, Markdown body, or extraction continuation
is part of this path. File access and provider allocations retain exact original
identity under the runtime custody contracts below.

A new guide version requires its own sufficiency findings, policy proposals,
acknowledgements and approvals before activation. Prior immutable evidence is
retained and cannot substitute for the new version's evidence. Tasks already
locked to an earlier guide and snapshot retain that policy context unless an
explicit audited rebase occurs.

## ProjectSetupRun

The field and status inventory below includes retained superseded setup
setup diagnostics, not instructions to implement those continuations again.
The unified path uses the compilation/projection/finalization contracts below:
after its finalization receipt exists, the run and its output references are
immutable. Later approval, post-policy projection and correction own separate
operation provenance. New model output requires a new compilation generation,
not reopening a finalized `policy_draft_ready` row.

Fields:

- `id`
- `project_id`
- `guide_id`
- `guide_version`
- `source_snapshot_id`
- `source_snapshot_hash`
- `setup_generation`
- `celery_task_id`
- `continuation_verification_job_id`
- `continuation_started_at`
- `status`
- `current_step`
- `output_sufficiency_report_id`
- `output_submission_artifact_policy_id`
- `output_post_submit_checker_policy_id`
- `post_submit_derivation_summary`
- `error_code`
- `error_summary`
- `error_artifact_incident_id`
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

`setup_generation` is a positive, guide-local monotonic identity. It prevents
an earlier setup run from continuing after a newer run exists for the same
draft guide; it is not a user-visible revision number.

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
- `dispatch_pending`
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

## GuideSourceArtifactBinding

Fields:

- `id`
- `project_id`
- `guide_id`
- `source_snapshot_id`
- `source_item_id`
- `project_setup_run_id`
- `setup_generation`
- `content_id`
- `verified_replica_id`
- `logical_role`
- `supersedes_binding_id`
- `created_by_service`
- `created_at`

`GuideSourceArtifactBinding` is retained read-only evidence from the removed
guide verification flow. Current guide setup uses committed original-document
metadata and attempt-scoped document access records; it creates no new binding
or extraction records. The retained binding links a source item and setup
generation to its recorded `ArtifactContent` and replica. Composite foreign keys preserve the exact
project, guide, snapshot, item, setup-run, generation, content, and replica
lineage. Retained `supersedes_binding_id` references remain intact. Their presence
does not authorize any current reader or writer.

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
- `project_setup_run_id`
- `setup_generation`
- `agent_material_sha256`
- `agent_material_byte_count`
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

The unified compiler assesses sufficiency once for the immutable guide material.
Blocking gaps stop at findings; sufficient guides stop at draft policy review.
The deterministic sufficiency projector creates the report from the persisted
`ProjectGuideCompilation`, with server-owned agent identity. Provider-returned
names and versions never establish provenance. The exact source snapshot hash,
setup generation, canonical material hash/byte count, document access evidence
and compilation identity bind the current original-document source evidence.
The compilation input additionally binds the exact task-example list through
its canonical input hash; source snapshots commit its hash and count.

Manual reports use their separately authorized API and persist null agent name
and version. They do not execute inference or supply compilation provenance.
The removed run-sufficiency route is not a manager rerun API; that later workflow
belongs to POL-05A → AUTH-12F4 → POL-05B.

The live Celery path consumes the sufficiency projector under fresh fixed-service
authority. Its immutable `ProjectGuideComponentProjectionOperation` binds the
attempt, compilation, generation, component/result hashes and authorization.
Projection itself leaves setup unchanged; the separate finalizer atomically
records permitted outputs and seals the generation.

## GuideSufficiencyReportSourceUsage

Fields:

- `id`
- `report_id`
- `item_order`
- `source_item_id`
- `binding_id`
- `content_id`
- `extraction_usage_id`
- `extraction_attempt_id`
- `extracted_content_id`
- `project_setup_run_id`
- `setup_generation`
- `canonical_output_sha256`

This table is retained read-only evidence; current compilation writes no rows
here. Each retained row records which exact ART binding and extraction lineage supplied
one ordered source item to a sufficiency report. Composite foreign keys prevent
mixing source items, content, extraction attempts, setup runs, or generations.
A report cannot consume the same extraction usage twice or assign two items the
same order.

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
  "derivation_source": "unified_compilation",
  "derivation_agent_name": "ProjectGuideCompilationProjection",
  "derivation_agent_version": "v1",
  "source_material_refs": ["artifact-content:00000000-0000-0000-0000-000000000030#extraction-usage:00000000-0000-0000-0000-000000000040"],
  "lifecycle_status": "draft",
  "approved_by_admin_role_grant_id": null,
  "approved_by_actor_profile_id": null,
  "approved_at": null
}
```

The live unified compiler proposes this policy together with sufficiency and
separate pre-submission/post-submission policy components. ART readiness starts
one Celery compilation; sufficient guides stop at draft review and blocked
guides stop at findings. The deterministic artifact-policy projector consumes
the persisted component only after its exact sufficiency projection exists.
Its immutable operation binds inputs, output digest, prior report, generation
and authorization evidence. Finalization records the exact permitted outputs.

`derivation_source`, agent identity and generated policy version are server-owned
provenance. Clients cannot supply them or use the reserved `agent-` version
prefix. Manual policies retain their own authorized provenance. A unified draft
cannot use the generic manual-policy approval route: manager proposal review,
correction, fresh-generation rerun and approval remain POL-05A → AUTH-12F4 →
POL-05B. Projection creates neither effective policy nor executable checkers.

## ProjectGuideComponentProjectionOperation

This immutable internal receipt records one `guide_sufficiency` or
`submission_artifact_policy` projection per setup generation. It is the replay
and provenance boundary between a persisted unified compilation and the
canonical product row; it is not another report or policy source of truth.
Changed lineage, output content, authority evidence, or replay facts fail
closed. Database guards prevent updates, deletes, or truncation of projection
custody and of the protected agent-derived business content.

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

## ProjectGuideSetupFinalization

The hidden finalizer records one immutable receipt per setup generation,
compilation, operation, and authorization decision. Composite custody binds the
accepted compilation, attempt and request, exact sufficiency projection/report,
and the artifact-policy projection/draft when required. Canonical fact and
authority digests include the complete lineage and explicit nullable policy
triple.

In one caller-owned root transaction, the receipt and setup transition commit
or roll back with staged authorization evidence. `guide_blocked` closes as
`sufficiency_blocked`; ready and warning results close as `policy_draft_ready`.
Only status, diagnostic step, the two output pointers, and completion time
change; `updated_at` is preserved. PostgreSQL assigns receipt creation and setup
completion the same transaction timestamp and prevents receipt or finalized
setup rewrites. Legacy-only setup generations retain their existing lifecycle.

Exact replay uses the stored pre-finalization source digest and verifies the
closed setup outputs and timestamp before returning the stored receipt. It
creates no new evidence or projection. AUTH-12B2 supplies the explicit concrete
finalization adapter with current service and exact historical authority checks.
The default port remains unavailable; HTTP and Celery composition belongs to POL-04B.
Finalization grants no approval, activation, post-submit, or task-readiness
behavior. Later live post-submit integration requires separately reviewed
custody because this finalized setup row is immutable.

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
checker, review, and revision provenance. Contribution-policy provenance comes
from the guide-bound task lock copied to `TaskAssignment`, stamped on each
immutable Submission, and copied from that Submission to `ReviewLease`.
None of these reads
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

At the deferred WS-ARCH-001-02I cutover, the legacy standalone
`/tasks/{id}/submission-precheck` path is removed. Pre-submit then runs only
inside the same process-local preparation request that owns the uploaded ZIP
and bounded scratch generation:

```text
POST /api/v1/tasks/{id}/submission-bundle-preparations
422 DomainError(code="pre_submission_checker_failed", details={status, eligible_to_submit, results})
```

After that cutover no independent precheck route or client-owned manifest can
reproduce the authoritative result. `POST /api/v1/tasks/{id}/submissions` consumes the verified ready
admission and does not receive scratch paths or rerun the pre-submit plan.

Before that cutover, hidden ART-04B2 establishes the execution boundary without
exposing a route. The fixed materializer authorizes before any prepared-byte
read or workspace reservation. One callback-scoped sealed tree is checked
against the server commitment and semantic manifest. ART-04B3 extends that same
callback to execute the locked project-policy phase and normalize every
platform and project result into one typed envelope. The tree is cleaned before
the transaction-bound evidence service reloads the actor, identity link, task,
assignment, predecessor, guide and locked policy rows and persists one
`PreSubmitEvidenceSet` with ordered `PreSubmitEvidenceResult` members. Evidence
identity is deterministic over the complete custody and locked-policy context;
exact replay returns the same durable set without minting another pass
capability, and changed facts fail closed. Only first persistence of a passing
execution produces a process-local, generation- and predecessor-bound
single-use capability for immediate admission continuation; a later attempt
must re-prepare the bundle. The evidence-set ID alone is never that capability.

ART-04C1 consumes that live capability and exact prepared generation inside the
final authorization transaction. One immutable `SubmissionBundleDurableIntent`
then joins the passing evidence set one-to-one with the generic
`ArtifactPutAttempt`. The join is the database-recoverable producer fence for
later verification publication; it does not duplicate evidence lineage, store
scratch state, or create a bindable admission. Provisional capacity, the put
attempt, authorization evidence, and this join commit before provider I/O.
Generic observation and recovery continue from the put attempt after process
loss.

ART-04C2 adds one `SubmissionBundleAdmission` only when the verifier's complete
read produces a matching successful receipt. The row joins the exact durable
intent and evidence to provider-neutral content, the verified replica, the
verification receipt, and exactly one direct-put or observed-confirmed receipt.
It starts in `ready`. The hidden ART admission-consumption capability may apply
`ready -> consumed|stale` only inside a caller-owned root transaction after
exact TASK and ART lineage validation. A consumed admission records the exact
Submission identifier and lifecycle version while its generic artifact binding
uses its independent binding-chain version. The capability remains deny-only
and route-unreachable until the later TASK composition and AUTH activation
chunks.
The hidden preparation route keeps scratch and prepared handles process-local,
returns before durable verification finishes, and remains excluded from OpenAPI
and crosses the active `artifact.submission_bundle.prepare` PREP boundary before durable intent.

Blocking pre-submit failures prevent submission creation, create no submission
row, no submission version, no task transition to `submitted`, and no
submission-created audit event. Workstream still writes a task audit event named
`pre_submission_check_failed` with bounded identifiers, catalogue identity,
stable codes, counts and categories for project operators. It excludes paths,
filenames, scratch/provider references, raw output, evidence contents,
credentials and free-form checker messages. Pre-submit results never return
review decision values.

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

For generated setup, the sole unified guide compiler proposes the post-submit
component in the same inference as sufficiency and pre-submit policy proposals.
It receives exact verified guide material and registered capability snapshots.
POL-04B retains that component in the immutable compilation and stops at draft
review. Later approval and deterministic post-submit projection/compilation
consume it without another agent call. The setup runtime does not execute
checkers or judge contributor submissions.

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

When a task locks project context, Workstream copies the canonical persisted
`PostSubmitCheckerPolicy.policy_body` and its exact hash. Submission and checker
runs copy that same body/hash. Later changes to a project's policy do not rewrite
those locked facts. Project policy versions describe changes to project rules;
they do not select different software readers.

Initial v0.1 has one supported body, compiler and catalogue. Earlier development
representations reject; no migration reader, translation or fallback preserves
them. Retained data and immutable evidence are not deleted or rewritten by this
cleanup. New setup generations use the current contract; any data disposition
requires separate authorization.

The canonical body contains:

- `schema_version`: `post_submit_checker_policy`
- `compiler_version`: `workstream-post-submit-compiler`
- `project_id` and `guide_version`
- `catalogue_id`, `catalogue_source_version`, `catalogue_schema_version` and
  `catalogue_manifest_sha256`
- ordered `entries`, with checker ID, definition/implementation identity,
  classification and closed configuration
- `blocking_severities`

Each mandatory entry has classification `platform_default`. The eight defaults
cannot be omitted, reordered or reclassified. The sole selectable structural
addition is `check_acceptance_criteria_present`, classified as `project_required`
or `project_warning`. Default/required/warning/execution lists are derived from
these entries; they are not another serialized policy body. Existing persisted
required/warning/blocking summaries must exactly match the parsed canonical body
at setup continuation, activation, task locking/reading, submission validation
and execution. A recomputed hash cannot make an unsupported body valid.

Each entry has this shape (illustrative entry, not a complete policy):

```json
{
  "checker_id": "check_submission_packet",
  "definition_version": "v0.1",
  "implementation_version": "workstream-structural",
  "classification": "platform_default",
  "configuration": {}
}
```

The compiler rejects unknown selections, conflicting classifications, invalid
configuration, missing defaults and weakened blocking severities. The floor is
`critical` and `high`; projects may add stricter severities. Raw structural
warnings remain distinct from policy-adjusted blocking outcomes.

Post-submit checker policy governs durable internal checker runs after a submission is finalized. It does not replace the generated project pre-submit checker policy.

Baseline invariant: post-submit policy hash, body, and lock columns are
explicit. Pre-v0.1 development rows without policy hashes are not backfilled
into authority; recreate the database and use the project setup lifecycle.
Runtime records fail
closed when a task, submission, or checker run lacks valid
`locked_post_submit_checker_policy_*` context.

Baseline invariant: required post-submit policy provenance binds a compiled
policy to guide, source snapshot, effective project policy, and pre-submit
checker bundle context. Construction-era rows are not an upgrade source.

Baseline invariant: the single-row project/guide-version uniqueness rule is
replaced by uniqueness for current
`compiled` or `approved` rows. Superseded rows remain append-only and retain
their policy body/hash, supersession kind/reason, actor/role/time provenance,
and any same-context correction replacement link. Correction lookup is scoped
to the exact guide, source
snapshot, effective project policy, and pre-submit checker provenance so stale
feedback cannot influence a later setup context.

## ReviewPolicy

`human_review_required: bool = true` is persisted in the existing immutable
guide-bound policy. Creation defaults true; updates that omit it inherit the
exact predecessor's value. Only JSON booleans are accepted. False is configurable
in draft, but guide activation rejects it until automated FinalAcceptance/CON
execution is available. No new policy entity or acceptance-mode enum is added.

`semantics_format` pins the hash representation to the immutable version.
Existing rows are backfilled with `v1` and true without changing their stored
hash, completeness status or downstream selectors. v1 retains its original
`workstream.review_policy.v1` hash input, which excludes the new field; it cannot
represent false. New rows use `v2`, whose `workstream.review_policy.v2` digest
includes the explicit boolean. Neither format repairs incomplete semantics.
The migration's boolean backfill default is removed afterward; API/ORM creation
defaults true, and direct SQL must provide a non-null boolean. Downgrade refuses
any v2 history, including true, because removing the format would lose meaning.

The [implementation record](../.commitrail/changes/pre-review-plan-reconciliation.md#delivered-policy-setting-implementation)
binds the configuration proof. Automated routing and final acceptance remain
separate work; existing attempts retain their exact locked policy versions.

Fields:

- `id`
- `project_id`
- `guide_version`
- `policy_generation`
- `policy_hash`
- `human_review_required`: strict boolean, creation default `true`
- `semantics_format`: `v1 | v2`, immutable hash representation
- `semantics_status`: `complete | legacy_incomplete`
- `supersedes_policy_id`
- `review_preference_window_seconds`
- `review_lease_duration_seconds`
- `max_active_review_leases_per_reviewer`: `1` in v0.1
- `self_review_allowed`: `false` in v0.1
- `reject_policy`: `close_task` in v0.1
- `finding_evidence_requirement`
- `allowed_decisions`
- `minimum_finding_fields`
- `created_at`

## RevisionPolicy

Fields:

- `id`
- `project_id`
- `guide_version`
- `policy_generation`
- `policy_hash`
- `semantics_status`: `complete | legacy_incomplete`
- `supersedes_policy_id`
- `max_revision_rounds`
- `revision_deadline_hours`
- `allowed_resubmission_states`
- `reviewer_reassignment_rule`
- `created_at`

Limit or deadline exhaustion blocks further preparation and submission; it does
not synthesize a reject Review. Complete next-attempt context selection is
deterministic: exact prior component matches keep, every changed valid active
guide/policy component rebases together, and missing or unsafe active context
blocks for manager repair.

## ContributionPolicy

Fields:

- `id`
- `project_id`
- `name`
- `status`: `draft | active | retired`
- `current_published_version_id`
- `last_transition_operation_id`
- `created_by`
- `created_at`
- `retired_by`
- `retired_at`

At most one policy is active for guide activation in one project. Guide
activation and task readiness require its published version; missing
configuration is not an implicit unpaid rule. Later TaskAssignment and
ReviewLease creation copy the attempt's locked version even if it has since
been retired.

## ContributionPolicyVersion

Fields:

- `id`
- `contribution_policy_id`
- `project_id`
- `version_number`
- `status`: `draft | published | retired`
- `last_updated_by` and `last_updated_at` for the authorized complete-draft
  replacement anchor
- `last_transition_operation_id` for database-verifiable publication or
  retirement custody
- publication and retirement actor/timestamp fields

Published and retired versions are immutable. Guide activation binds one
version; WorkstreamTask locks it before claimability, TaskAssignment copies it,
Submission stamps the attempt value, and ReviewLease copies that immutable
stamp.

## ContributionPolicyLifecycleEvent

Each policy mutation appends one immutable event containing the operation and
request digest, actor/project/policy/version identity, version number, prior
published-version identity, exact policy/version state transition, and
database-owned occurrence time. PostgreSQL rejects event update, delete, and
truncate. Exact operation replay may return only this immutable result after a
fresh authorized read; it never reconstructs success from mutable policy state.
Publish and retire events additionally carry a conditional publication-custody
operation reference; draft events never carry it.

## ContributionPolicyTransitionCustody

Each publish or retire operation owns one immutable custody row binding the
operation/request digest, actor, project, policy, target version, optional prior
current version, event type, and database-generated occurrence time. Deferred
PostgreSQL guards require the aggregate, affected versions, and lifecycle event
to carry the same unique transition operation. Replacement publication retires
the prior version with the same actor and time. Custody rows reject update,
delete, and truncate and roll back with product state and authorization
evidence.

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
- `quantity` in the exact `NUMERIC(38, 18)` value envelope, stored unrounded
  and checked explicitly before persistence
- `adapter_binding_id`

API quantities are bounded decimal strings; binary floating point, exponent
notation, non-finite values, zero, negatives, overflow, and excess precision
are rejected rather than rounded. Money units are uppercase configured ISO 4217
codes. Project-points units have project-scoped identity
`(project_id, unit_code)` and whole-number quantities. Published definitions are immutable and project,
instrument, and unit consistent with the referenced adapter binding.

## ProjectCompensationUnit

Fields:

- `project_id`
- `instrument_type`: `money | project_points`
- `unit_code`
- `iso_currency_code` for money, null for project points
- `status`: `active | retired`
- creation and retirement actor/timestamp fields

The identity is `(project_id, instrument_type, unit_code)`. Money units reference
the migration-owned immutable ISO 4217 List One registry. Project-points units
are project-scoped. Award definitions reference the unit identity with a
composite foreign key. Persistence initially allows active creation only and
defers unit lifecycle mutation to the authorized contribution-policy behavior.

## ProjectCompensationAdapterBinding

Fields:

- `id`
- `project_id`
- `instrument_type`: `money | project_points`
- `adapter_actor_id`
- `route_key`
- `status`: `active | suspended`; retirement remains a future lifecycle extension
- `binding_lifecycle_version`, starting at 1 and incrementing once per valid
  active-to-suspended or suspended-to-active transition
- creation, suspension, resume, and retirement actor/timestamp fields; only the
  current suspension or resume attribution is populated after version 1

`route_key` is a non-secret 1-120 character ASCII identifier matching
`^[A-Za-z][A-Za-z0-9._:-]{0,119}$`; traversal pairs, whitespace, path/URL/query
syntax, controls, and Unicode are forbidden. Provider endpoints, credentials,
and tokens are deployment secrets, not domain fields. At most one binding is
active per project and instrument. CP02 installs hidden, route-unreachable
create/read/suspend/resume behavior and immutable transition events while AUTH
actions remain unavailable. Retirement is not implemented.

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
- `locked_guide_id`
- `locked_guide_version`
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
- `locked_review_policy_id`
- `locked_review_policy_generation`
- `locked_review_policy_hash`
- `locked_revision_policy_id`
- `locked_revision_policy_generation`
- `locked_revision_policy_hash`
- `locked_contribution_policy_version_id`
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

The task id points to the locked task contract. That contract includes the exact
same-project guide ID/version/activation-sequence triplet, guide source snapshot
id/hash, effective project submission artifact
policy id/hash, generated project pre-submit checker policy id/bundle hash,
post-submit checker policy id/version/hash, exact review and revision policy
id/generation/hash identities, acceptance criteria, derived display summaries,
and skill tags. Contributors submit against the task id; they do not restate
policy identities.

`locked_contribution_policy_version_id` is copied from the then-active guide
when the Task first acquires its complete context lock, before `ready`
(the existing transition acquires it at screening). Later readiness checks
validate that frozen tuple, not equality to a newer active guide or global
policy selector. Ordinary claim never changes it. Human
`needs_revision` complete-context preparation is the only boundary that may
atomically rebase this field on the continuing Task for the next attempt, with
prior/next lineage recorded before contributor access.

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

The v0.1 baseline excludes the retired persisted human
owner to `contributor_id`. The non-null `varchar(36)` value is protected by
foreign key `fk_task_assignments_contributor_id_actor_profiles`, index
`ix_task_assignments_contributor_id`, and trigger
`task_assignments_contributor_human`. The trigger reuses invoker-rights function
`public.require_human_actor_profile_reference()` to reject service profiles.
It deliberately permits suspended and deactivated human profiles because this
column preserves historical attribution rather than current authority.

At initial claim, `submitter_contribution_policy_version_id` must equal the
Task's locked version. It remains fixed throughout that submission attempt.
Only human `needs_revision` complete-context preparation may atomically rebase
the continuing assignment field for the next attempt; ordinary publication,
task claim, submission, and review claim cannot change it.

## Submission

Fields:

- `id`
- `task_id`
- `task_assignment_id`
- `contributor_id`
- `version`
- `status`
- `summary`
- `submission_bundle_admission_id` (hidden canonical intake identity from WS-ARCH-001-02F; public cutover remains 02I)
- `artifact_binding_id` (hidden canonical byte binding from WS-ARCH-001-02F; public cutover remains 02I)
- `artifact_content_id` (hidden canonical immutable ART content identity from WS-ARCH-001-02F; public cutover remains 02I)
- `submission_bundle_manifest_id` (target server-generated manifest identity)
- `pre_submit_evidence_set_id` (target checker evidence identity)
- `package_uri` (legacy caller transport removed by WS-ARCH-001-02I, which implements the superseded WS-ART-001-05B cutover)
- `package_hash` (nullable legacy caller input removed by WS-ARCH-001-02I; never canonical)
- `artifact_hash` (legacy transitional column replaced by exact binding/content identity and removed separately after all readers cut over)
- `artifact_hash_manifest` (legacy caller manifest removed by WS-ARCH-001-02I)
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
- `locked_review_policy_id`
- `locked_review_policy_generation`
- `locked_review_policy_hash`
- `locked_revision_policy_id`
- `locked_revision_policy_generation`
- `locked_revision_policy_hash`
- `submitted_at`
- `locked_at`
- `supersedes_submission_id`
- `remediation_source_checker_run_id` (checker-remediation submissions only)
- `revision_context_preparation_id` (human-Review revision submissions only)
- `contribution_policy_version_id` (immutable exact attempt policy copied from
  the TaskAssignment during Submission creation)

The submission contributor uses foreign key
`fk_submissions_contributor_id_actor_profiles`, index
`ix_submissions_contributor_id`, and trigger
`submissions_contributor_human`, backed by the same reusable lineage function.

The current Submission `contributor_id` uses the same migration, foreign-key,
and canonical-human trigger contract as TaskAssignment. Claim and submission
creation additionally lock and revalidate the caller's exact active human
ActorProfile and active issuer/subject identity link before locking the task
and active assignment. That transaction participant establishes current
identity eligibility only; project roles, grants, actions, and resource policy
remain owned by the authorization service.

The contributor first supplies one outer ZIP, summary, and attestation to
submission-bundle preparation. Workstream computes the exact archive identity,
server-generated semantic manifest, required-file/evidence facts, and immutable
pre-submit evidence set, then stores and verifies the bytes into a ready
admission. Final Submission creation supplies that admission identity and
summary/attestation context; Workstream assigns the submission version, creates
the exact artifact binding, and stamps locked guide source,
submission artifact, effective project policy, pre-submit checker, post-submit
checker, review, and revision policy provenance from trusted
task/project state. The contributor does not provide submission version, evidence
ids, checker results, checker run ids, guide versions, source snapshots,
effective project policy ids/hashes, pre-submit checker ids/bundle hashes,
post-submit checker policy ids/versions/hashes, exact review policy identities,
exact revision policy identities, provider references, package hashes, or
artifact manifests. Submitter award eligibility is governed by the
TaskAssignment-selected `ContributionPolicyVersion` for the exact attempt and
is not contributor-supplied. Submission creation stamps that identifier
immutably before any later rebase can change the continuing assignment. Human
revision preparation records prior/next policy lineage before it may update
that selector; publication alone cannot.

Version 1 has neither revision-source field. Every later version has exactly one:
a checker-remediation version stores the server-derived
`remediation_source_checker_run_id`, while a human-Review revision stores the
server-selected `revision_context_preparation_id`. The checker source must be the
completed, needs-revision, current-at-selection CheckerRun for the immediate
predecessor Submission and same Task. PostgreSQL enforces same-task/immediate-
predecessor lineage, one successor per source CheckerRun, source-field XOR, and
post-finalization immutability. A later CheckerRun retry cannot rewrite committed
Submission lineage. Contributor requests supply neither authoritative source ID.

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
- `locked_review_policy_id`
- `locked_review_policy_generation`
- `locked_review_policy_hash`
- `locked_revision_policy_id`
- `locked_revision_policy_generation`
- `locked_revision_policy_hash`
- `artifact_binding_id` (target after ARCH-04B/04C custody)
- `submission_bundle_manifest_id` (target after ARCH-04B/04C custody)
- `package_hash` (legacy; replacement custody in ARCH-04B/04C)
- `artifact_hash_manifest` (legacy; replacement custody in ARCH-04B/04C)
- `artifact_manifest_hash` (legacy; replacement custody in ARCH-04B/04C)
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
- `dispatch_authority`
- `definition_id` (stable catalogue definition ID for pre-submit; registry
  checker ID for durable)
- `definition_version` (catalogue definition or registry checker version
  selected by authority; the effective plan separately binds the top-level
  catalogue ID/version and manifest hash)
- `result_source`
- `effective_plan_hash`
- `rule_instance_id` (nullable only for non-policy/default definitions)
- `locked_policy_hash` (nullable only when no locked policy produced the result)
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

These authority-neutral provenance fields are explicitly typed and persisted.
`dispatch_authority` discriminates the identity namespace. The API/result
envelope serializes them under `definition` and `policy_trace`; they are never
hidden only in the open-ended `metadata` field. Pre-submit evidence uses the
same typed envelope without creating a durable `CheckerRun`; its immutable
evidence rows store these fields directly under the 04B3 schema.

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
- `submission_bundle_manifest_id` (target if this deferred record is ever added)
- `blocking_failures_count`
- `warnings_count`
- `ready_for_review`
- `issued_by`
- `issued_at`
- `invalidated_at`

Purpose:

If added later, the readiness certificate records the exact checker run and
server-generated manifest/binding identity that allowed a submission to enter
human review.

For v0.1, the final current `CheckerRun` is the checker proof. Planned ARCH-04E
adds the TASK-owned immutable routing manifest that binds that result, exact
Submission/binding/policy/authority lineage and evaluation generation, plus a
separate current routing pointer. TASK publishes manifest, pointer and
`review_pending` atomically after consuming CHECKERS facts. This is the canonical
handoff to REV, not an optional signed ReadinessCertificate or a replacement
authorization system. Its implementation remains planned. Any submitted
artifact change requires a new Submission and checker run.

## ReviewQueueEntry And ReviewLease

`ReviewQueueEntry` immutably anchors one exact finalized Submission/version,
Task, project, and its current successful `allow_review` CheckerRun. The 03A1
foundation does not yet implement the later ARCH-04E routing-manifest input;
live admission must consume that exact TASK handoff while retaining these
immutable CheckerRun/binding anchors. This adoption is an upstream dependency,
not activation of REV behavior. The 03A1
foundation persists only `pending` and `closed` queue state plus open/preferred
routing metadata; it exposes no route, selection behavior, or lease shape.
PostgreSQL validates the cross-owner lineage and checker admissibility when the
queue identity is written. The immutable queue row preserves that admission
fact if an upstream current-checker pointer changes later; it does not constrain
later mutations of upstream-owned rows.

`ReviewAdmissionIdempotencyRecord` reserves one exact admission operation and
SHA-256 request digest. It may begin pending without a queue, but can become
committed only when it references the matching queue identity and the same
completed, current `allow_review` CheckerRun. This is replay persistence, not an
automatic checker hook or authorization decision.

The later reviewer current-work API returns an active lease, one server-selected
offer, or none; it never exposes the full backlog.

`ReviewLease` is the permanent identity of one claim attempt. It stores the
canonical human reviewer ActorProfile ID, queue/Submission lineage, database
lease times, disposition, and the ContributionPolicyVersion copied from the
immutable Submission attempt stamp during claim, transitively inherited from
Task/Assignment without current-policy lookup. PostgreSQL enforces one active lease per reviewer and
queue entry. The queue's deferred `active_lease_id` relationship must agree
with the single active lease at transaction commit, allowing later claim and
close commands to stage both sides atomically without exposing behavior in the
persistence chunk.

Fields:

- `id`
- `review_queue_entry_id`
- `project_id`
- `task_id`
- `submission_id`
- `submission_version`
- `reviewer_id`
- `reviewer_contribution_policy_version_id`
- `attempt_generation`
- `status`
- `claimed_at`
- `expires_at`
- `closed_at`
- `close_reason`

Status is `active`, `consumed`, `released`, `expired`, or `revoked`. An active
attempt has no close fields. Terminal close provenance is exact:
`review_recorded`, `manual_release`, `lease_expired`, `grant_revoked`, or
`admin_override`. Identity, queue/Submission lineage, reviewer, frozen policy,
generation, and lease times never change; terminal attempts are wholly
immutable. The reviewer policy FK is non-null and same-project through CON's
canonical `ContributionPolicyVersion(id, project_id)` identity. Claim copies
the exact version stamped on the admitted Submission/task attempt; it performs
no current-policy lookup. A version that was published when the attempt was
prepared remains valid for that attempt after later retirement or publication.
REV's database guard rejects a draft, crossed-project, or lineage-mismatched
identity. Reviewer and preferred-reviewer FKs accept only canonical human
ActorProfiles.

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
- `locked_review_policy_id`
- `locked_review_policy_generation`
- `locked_review_policy_hash`
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
- `prior_locked_guide_source_snapshot_id` and hash
- `next_locked_guide_id`
- `next_locked_guide_version`
- `next_locked_guide_activation_sequence`
- `next_locked_guide_source_snapshot_id` and hash
- prior and next locked submission-artifact-policy identity and hash
- `prior_locked_effective_project_submission_artifact_policy_hash`
- `next_locked_effective_project_submission_artifact_policy_hash`
- prior and next locked pre-submit-checker policy identity, version, and hash
- `prior_locked_pre_submit_checker_bundle_hash`
- `next_locked_pre_submit_checker_bundle_hash`
- prior and next locked post-submit-checker policy identity, version, and hash
- `prior_locked_review_policy_id`, generation, and hash
- `next_locked_review_policy_id`, generation, and hash
- `prior_locked_revision_policy_id`, generation, and hash
- `next_locked_revision_policy_id`, generation, and hash
- prior and next locked task-template and task-execution policy context
- `prior_submitter_contribution_policy_version_id`
- `next_submitter_contribution_policy_version_id`
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

This immutable Review-rooted record is created atomically before a contributor
can observe human-review-caused revision. Checker remediation retains the Task's
locked context and creates no preparation. Preparation compares the prior
Submission's complete stamped context with every applicable currently active
Project Guide and policy selector: guide identity/version/activation sequence,
source snapshot, submission-artifact policy, effective project policy,
pre-submit and post-submit checker policies, ReviewPolicy, RevisionPolicy,
task-template/task-execution context, and the ContributionPolicyVersion in the
attempt's locked context. At this human revision boundary, TASK validates the
complete currently active project context through owner ports, including CON's
policy-validation port. An exact component match is kept;
every changed valid component is rebased together for the next attempt. Missing,
incomplete, inconsistent, crossed-project, revoked, or otherwise unsafe context
blocks the whole preparation for manager repair. Task Context returns only the
validated complete chain head. No context rebase occurs during active review;
the reviewer reads the context stamped on the leased Submission.

Publication never silently rebases award eligibility during active or completed
work. After a human `needs_revision`, revision preparation records prior and
next `ContributionPolicyVersion` references and atomically updates the
continuing Task and TaskAssignment only for the next submission attempt when
the complete current context changed. Prior Submissions, ReviewLeases, Reviews,
ContributionRecords, and CompensationAwards retain their old version. The next
Submission stamps the rebased version, and its ReviewLease copies that version.

The contributor and reviewer history show prior/next guide, policy—including
ContributionPolicyVersion—identity, activation sequence where applicable,
direction, reason, and change summary.

## FinalAcceptance

The [shared acceptance contract](spec_review_lifecycle.md#finalacceptance)
defines both sources for this planned REV-owned fact. One schema and atomic
operation serve human accept and authorized `task.post_submit.route` with the
exact current successful routing manifest, locked `human_review_required=false`
policy and originating AUTH decision event. Required-check success or raw checker
output alone cannot create FinalAcceptance. No separate automated decision entity
or synthetic Review is introduced.

Fields:

- `id`
- `project_id`
- `task_id`
- `submission_id`
- `source_review_id`
- `acceptance_source`: `human_review | task_post_submit_route`
- `source_routing_manifest_id`
- `authorization_decision_event_id`
- `accepted_submitter_id`
- `accepted_at`
- `recorded_by`
- `policy_context_ref`

Purpose:

This immutable REV-owned internal fact is created inside either authorized
trigger's shared acceptance transaction. Existing `Submission` is already the version
identity, so the stored FK is `submission_id`; no SubmissionVersion entity or
`submission_version_id` alias is introduced. `recorded_by` is the originating
AUTH actor: the actual reviewer or the admitted fixed TASK routing service.
`policy_context_ref` is a foreign key to the exact immutable `ReviewPolicy.id`
whose project and guide version match the reviewed Submission context.

PostgreSQL enforces `UNIQUE(task_id)`, `UNIQUE(submission_id)` and uniqueness
of each non-null source, closed/exclusive source shapes, plus the canonical
same-chain and immutable source constraints. There is no public/manual create API and no separate
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

The typed `LifecycleAuditParticipant` is the feature-neutral writer for new
REV/CON lifecycle evidence. It accepts only closed entity/reason/reference
types and UUID references, flushes through the caller's `AsyncSession`, and
uses the existing lifecycle-compatible `audit_events` representation without
adding another domain or ledger. Its persisted compatibility discriminator is
`legacy_lifecycle`; that storage token is not the name or ownership boundary of
the new typed interface. The participant supplies fixed internal provenance
markers required by the existing representation; callers cannot provide
external subjects, issuers,
roles, claims, authorization facts, credentials, provider references, or
arbitrary payload metadata. Exact event-ID replay returns only an identical
immutable row, while changed reuse fails closed. Caller rollback removes the
audit row with the rest of the product transaction. The nested `project_id`
reference is provenance evidence only: it must never be used as an
authorization scope or query filter. Every reader must reload the canonical
entity relationships to establish the event's project context.
Lifecycle event tokens are added only when an adopted feature contract defines
them, together with their closed primary-entity pairing and contract tests.

## Required Invariants

- a task must belong to a project
- a task records the project guide version used at creation
- a task cannot enter ready without passing screening; recovery uses only its
  registered scoped permission and cannot bypass missing task policy context
- a submission must belong to a task
- a review must belong to a submission
- an accepted task must have exactly one FinalAcceptance linked to its versioned
  Submission and exactly one accepting source: human accept Review or authorized
  locked-false TASK routing manifest
- every valid recorded human review must create one reviewer `completed_review`
  contribution
- an accepted task must additionally create one submitter
  `accepted_submission` contribution sourced from FinalAcceptance
- `needs_revision` and `reject` must not create FinalAcceptance or a submitter
  contribution
- FinalAcceptance is unique per task, Submission and each non-null source and has no
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
