# Data Model

## Implementation Stack

The v0.1 persistence layer uses SQLAlchemy 2.x async models, Alembic migrations, and Pydantic schemas.

## Entity Overview

```text
Actor
  WorkerProfile
  ReviewerProfile

Project
  ProjectGuide
  SubmissionArtifactPolicy
  EffectiveSubmissionArtifactPolicy
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

## Actor

Fields:

- `id`
- `external_subject`
- `external_issuer`
- `email`
- `display_name`
- `role`
- `claim_snapshot`
- `auth_source`
- `created_at`
- `last_seen_at`
- `status`

Actor identity comes from external Flow authentication. `external_subject` plus `external_issuer` is the stable identity binding. Email is profile metadata and must not be treated as the primary identity.

Workstream can keep actor/profile records for permissions, assignments, reputation, and audit display, but it does not own password authentication or primary login sessions.

Roles:

- admin
- project_manager
- worker
- reviewer
- finance
- auditor

`Operator` is a product persona, not a separate v0.1 permission role. In the application model, operator actions are performed by project managers, workers, reviewers, admins, or finance users depending on the action.

## WorkerProfile

Fields:

- `actor_id`
- `display_name`
- `skill_tags`
- `accepted_count`
- `needs_revision_count`
- `rejected_count`
- `paid_total`
- `pending_payout_total`
- `reputation_score`
- `status`

## ReviewerProfile

Fields:

- `actor_id`
- `skill_tags`
- `reviews_completed`
- `accept_count`
- `needs_revision_count`
- `reject_count`
- `overturned_count`
- `average_turnaround_hours`
- `review_quality_score`
- `status`

## Project

Fields:

- `id`
- `name`
- `slug`
- `description`
- `status`
- `base_amount`
- `currency`
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
- `content_markdown`
- `required_task_fields`
- `required_submission_fields` (legacy display summary)
- `task_instructions`
- `output_requirements`
- `acceptance_criteria`
- `rejection_criteria`
- `reviewer_rubric`
- `forbidden_actions`
- `required_skills`
- `difficulty_scale`
- `estimated_time_policy`
- `common_rejection_reasons`
- `unacceptable_work_policy`
- `approved_by`
- `effective_at`
- `change_summary`
- `created_by`
- `created_at`
- `superseded_at`

The guide is versioned and human-facing. It contains project instructions, quality bar, examples, rubric, common rejection reasons, and links or summaries for approved policies. It may be markdown, an imported document, or a URL-backed guide.

Runtime enforcement uses machine-readable policies attached to the guide version. Workstream does not parse guide prose at submission time to decide which artifact checks to run.

Every task records the guide version active at creation or screening time before the task enters `READY`. Later source adapters must also lock the guide version during normalization before workers see the task.

When a task is claimed or moved to `IN_PROGRESS`, its locked guide and policy context does not change silently. A newer upstream guide version can only affect unclaimed work or a controlled revision path when policy allows it and the audit log records the reason.

Material changes require a new guide version or policy version. Material changes include acceptance criteria, rejection criteria, reviewer rubric, output requirements, submission artifact policy, pre-submit checker generation rules, post-submit checker policy, review policy, revision policy, and payment policy.

Implementation note: the current v0.1 database has `ProjectGuide.evidence_policy`. That field is a transitional storage location for submission artifact requirements. The architecture source of truth is `SubmissionArtifactPolicy`.

Implementation note: `ProjectGuide.required_submission_fields` is a legacy display summary. Submission validity is enforced by `EffectiveSubmissionArtifactPolicy`, not by project guide fields.

## SubmissionArtifactPolicy

Fields:

- `id`
- `project_id`
- `guide_version`
- `version`
- `required_artifacts`
- `required_evidence`
- `artifact_manifest_required`
- `artifact_hash_required`
- `artifact_hash_algorithm`
- `allowed_storage_schemes`
- `forbidden_artifacts`
- `required_attestation_terms`
- `packaging_rules`
- `created_by`
- `approved_by`
- `created_at`

Example:

```json
{
  "version": "v1",
  "required_artifacts": [
    "submission.zip",
    "task.toml",
    "static_guard.txt",
    "review_packet.md"
  ],
  "required_evidence": [
    "oracle_test.log",
    "starter_m1_test.log"
  ],
  "artifact_manifest_required": true,
  "artifact_hash_required": true,
  "artifact_hash_algorithm": "sha256",
  "allowed_storage_schemes": ["local", "s3", "r2"],
  "forbidden_artifacts": ["secrets/**", ".env"],
  "packaging_rules": {
    "archive_required": true
  }
}
```

Project admins approve this policy. Workers do not supply it.

Project policy can add stricter requirements, but it cannot weaken Workstream's default submission artifact policy.

## EffectiveSubmissionArtifactPolicy

Generated server-side from:

```text
WorkstreamDefaultSubmissionArtifactPolicy
+ ProjectSubmissionArtifactPolicy
```

Fields:

- `project_id`
- `guide_version`
- `policy_hash`
- `required_artifacts`
- `required_evidence`
- `artifact_manifest_required`
- `artifact_hash_required`
- `artifact_hash_algorithm`
- `allowed_storage_schemes`
- `forbidden_artifacts`
- `required_attestation_terms`
- `generated_at`

This policy is deterministic. It preserves Workstream defaults first and adds project-approved requirements. Duplicate rules collapse by canonical key. Any project rule that conflicts with Workstream defaults is a project setup defect.

## PreSubmitCheckerPolicy

Generated server-side from `EffectiveSubmissionArtifactPolicy`.

Fields:

- `project_id`
- `guide_version`
- `policy_hash`
- `checker_names`
- `checker_configs`
- `blocking_severities`
- `generated_at`

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

Blocking pre-submit failures prevent submission creation. A failed blocking pre-submit check creates no submission row, no submission version, no task transition to `submitted`, and no submission-created audit event.

## PostSubmitCheckerPolicy

Fields:

- `id`
- `project_id`
- `guide_version`
- `required_checkers`
- `warning_checkers`
- `blocking_severities`
- `created_at`

Example:

```json
{
  "required_checkers": [
    "check_policy_context_present",
    "check_submission_packet",
    "check_evidence_present"
  ],
  "blocking_severities": ["high"]
}
```

Post-submit checker policy governs durable internal checker runs after a submission is locked. It does not replace the generated pre-submit checker policy.

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
- `locked_submission_artifact_policy_version`
- `locked_effective_submission_artifact_policy_hash`
- `locked_pre_submit_checker_policy_hash`
- `locked_post_submit_checker_policy_version`
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
- `required_files` (derived snapshot)
- `required_evidence` (derived snapshot)
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
- auto_checking
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

The task id points to the locked task contract. That contract includes the guide version, submission artifact policy version, effective submission artifact policy hash, generated pre-submit checker policy hash, post-submit checker policy version, review policy version, revision policy version, payment policy version, acceptance criteria, derived required artifacts and evidence references, base payout, and skill tags. Workers submit against the task id; they do not restate policy versions.

Implementation note: current v0.1 code uses `locked_checker_policy_version` for the post-submit checker policy version. The architecture target splits this into `locked_post_submit_checker_policy_version` and explicit submission artifact/pre-submit provenance fields.

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
- `locked_submission_artifact_policy_version`
- `locked_effective_submission_artifact_policy_hash`
- `locked_pre_submit_checker_policy_hash`
- `locked_post_submit_checker_policy_version`
- `locked_review_policy_version`
- `locked_revision_policy_version`
- `locked_payment_policy_version`
- `submitted_at`
- `locked_at`
- `supersedes_submission_id`

The worker submission packet supplies the task id, summary, outputs, artifact hashes, evidence references, and worker attestation. Workstream assigns the submission version, creates evidence ids, and stamps locked guide, submission artifact, pre-submit checker, post-submit checker, review, revision, and payment policy provenance from trusted task/project state. The worker does not provide submission version, evidence ids, checker results, checker run ids, guide versions, submission artifact policy versions, post-submit checker policy versions, review policy versions, revision policy versions, or payment policy versions.

Implementation note: current v0.1 code uses `locked_checker_policy_version` on submissions for post-submit checker policy provenance. The architecture target adds explicit submission artifact and pre-submit policy provenance.

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
- `locked_post_submit_checker_policy_version`
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

`pre_review_gate` is a checker phase, not a task status. The v0.1 task status during this phase is `auto_checking`.

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
- `prior_locked_submission_artifact_policy_version`
- `next_locked_submission_artifact_policy_version`
- `prior_locked_pre_submit_checker_policy_hash`
- `next_locked_pre_submit_checker_policy_hash`
- `prior_locked_post_submit_checker_policy_version`
- `next_locked_post_submit_checker_policy_version`
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
- `actor_id`
- `external_subject`
- `external_issuer`
- `actor_role`
- `claim_snapshot`
- `auth_source`
- `event_type`
- `before`
- `after`
- `reason`
- `locked_guide_version`
- `submission_id`
- `checker_run_id`
- `review_id`
- `contribution_record_id`
- `override_id`
- `created_at`

Audit events are append-only.

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
