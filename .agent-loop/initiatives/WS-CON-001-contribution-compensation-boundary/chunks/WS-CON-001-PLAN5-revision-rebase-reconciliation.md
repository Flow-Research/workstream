# Chunk Contract: WS-CON-001-PLAN5 - Revision Rebase Reconciliation

## Goal and risk

Adopt the human-confirmed rule that a human-review `needs_revision` transition
is the only in-progress synchronization boundary for all changed applicable
Project Guide and policy versions. Preserve frozen context during assignment,
submission, and an active ReviewLease; atomically prepare the next attempt from
the complete current valid context; and never mutate completed history.

This is an L1 product-policy and cross-subsystem specification change. It
changes no runtime, schema, migration, API, authorization registration, or
workflow behavior.

## Human intent ledger

### Problem being solved

Canonical documents already rebase Project Guide context after a human
`needs_revision`, but explicitly keep submitter ContributionPolicy terms frozen
for the lifetime of the TaskAssignment. That mixes old and new governing
context in the next revision attempt.

### Why this matters

The contributor and next reviewer must use one coherent current project
context after revision preparation, while the completed Review and every prior
Submission, ContributionRecord, and CompensationAward remain auditable and
immutable.

### Target behavior and design chosen

- Publication or activation alone never mutates active work.
- `accept` and `reject` finish under the exact assignment, Submission, and
  ReviewLease context already frozen for that attempt.
- A human `needs_revision` creates the current reviewer contribution under the
  completed lease-frozen version, then revision preparation compares the
  complete applicable current context: Project Guide/source activation,
  submission-artifact policy, pre-submit and post-submit checker policies,
  review policy, revision policy, task-template/task-execution context, and
  ContributionPolicyVersion.
- The next-attempt context keeps unchanged components and atomically replaces
  every changed component with the complete current valid version, forward or
  backward where reactivation is allowed.
- The TaskAssignment stores the authoritative rebased submitter
  ContributionPolicyVersion for the next attempt; the next ReviewLease
  independently freezes the then-current reviewer ContributionPolicyVersion.
- Missing, incomplete, inconsistent, crossed-project, revoked, or unsafe
  current context blocks preparation; no mixed context may be published.
- Checker-caused remediation remains distinct and does not perform this human
  revision rebase.

### Alternatives rejected

- Lifetime assignment freeze: rejected because revised work could use an old
  economic policy while every other project contract has moved.
- Silent publication-time mutation: rejected because it changes active work
  without a lifecycle checkpoint.
- Retroactive history rewrite: rejected because completed work and earned
  awards must remain immutable.

### Boundaries and non-goals

REV/task owns revision preparation and TaskAssignment/Submission/ReviewLease
lineage. CON owns ContributionPolicy selection/freeze validation and consumes
the authoritative frozen version. This chunk adds no runtime implementation,
new state, public route, permission/action, compensation calculation, or ART
provider behavior.

### Proof strategy

Contradiction scans, Markdown links, stale wording gates, exact diff review,
and focused security, product/ops, architecture, and docs review must pass.

## Allowed files

```text
docs/decision_0010_revision_context_rebase.md
docs/decision_0003_project_guides_are_first_class.md
docs/decision_0016_contribution_compensation_boundary.md
README.md
docs/glossary.md
docs/architecture_lockdown.md
docs/architecture_data_model.md
docs/product_principles.md
docs/principles.md
docs/risk_register.md
docs/product_first_user_flows.md
docs/roadmap_implementation_backlog.md
docs/spec_review_lifecycle.md
docs/spec_contribution_compensation.md
docs/architecture_lifecycle_state_machine.md
docs/architecture_system_architecture.md
docs/operations_revision_replay.md
docs/operations_queue_policy.md
docs/operations_reviewer_workflow.md
docs/operations_project_operating_manual.md
docs/operations_payment_reputation.md
docs/template_project_guide.md
docs/template_review_packet.md
docs/template_submission_packet.md
docs/template_revision_replay.md
docs/template_task.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/{INTENT.md,PLAN.md,CHUNK_MAP.md,STATUS.md,RISKS.md,DECISIONS.md,CONFORMANCE_MATRIX.md,SOURCE_MANIFEST.md}
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/chunks/WS-CON-001-PLAN5-revision-rebase-reconciliation.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/chunks/WS-CON-001-05A-legacy-economic-terms-cutover-and-task-freeze.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/chunks/WS-CON-001-06-review-lease-contribution-policy-freeze.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/chunks/WS-CON-001-07-atomic-review-contribution-award-participant.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/reviews/WS-CON-001-PLAN5-*.md
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/{PLAN.md,CHUNK_MAP.md,STATUS.md,DECISIONS.md,RISKS.md,CONFORMANCE_MATRIX.md}
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/chunks/WS-REV-001-09A-revision-context-resubmission.md
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/chunks/WS-REV-001-10-contribution-integration-hidden-composition.md
.agent-loop/REVIEW_LOG.md only WS-CON-001-PLAN5 result
```

## Not allowed

```text
backend or frontend runtime and tests
migrations, schemas, APIs, workflows, dependencies, CI, or coverage controls
AUTH/ART runtime contracts or service identities
archival/imported reference specifications
roadmap spreadsheet or CSV exports
the user-owned local PDF deletion
```

## Acceptance criteria

- [x] ADR 0010 is the authoritative complete-context human revision-rebase
  decision, ADR 0016 agrees with it, and neither contains a contribution-policy
  exclusion.
- [x] Assignment/Submission/ReviewLease context remains immutable until a
  human `needs_revision`; publication alone causes no drift.
- [x] Accept/reject use frozen current-at-attempt context.
- [x] The completed needs-revision Review and reviewer contribution use the
  completed lease-frozen version.
- [x] Revision preparation compares the complete applicable active context:
  Project Guide/source activation, submission-artifact policy, pre-submit and
  post-submit checker policies, review policy, revision policy, task-template/
  task-execution context, and ContributionPolicyVersion. It publishes one
  atomic kept/rebased/blocked next-attempt context.
- [x] The human `needs_revision` Review, reviewer contribution/award, task and
  assignment effects, initial preparation or blocked outcome, audit/outbox
  effects, and contributor-visible state commit once or roll back together.
- [x] The next submitter attempt uses the rebased ContributionPolicyVersion and
  the next ReviewLease independently freezes the then-current reviewer version.
- [x] Prior Submissions, Reviews, ContributionRecords, and Awards are never
  rebased or rewritten.
- [x] Checker-caused remediation remains a distinct no-human-rebase path.
- [x] Canonical docs contain no contradictory lifetime TaskAssignment freeze or
  contribution-terms-never-rebase instruction.

## Verification

```bash
git diff --check
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 -m unittest -v scripts.test_lightweight_agent_gates
rg contradiction scan for revision rebase and frozen contribution terms
```

## Review and stop

Required focused review: security/auth, product/ops, architecture, and docs.
CI-integrity and test-delta are unrelated because no CI or test file may
change. Human review should focus on the atomic
rebase boundary, immutable historical economic truth, and cross-subsystem
ownership. Stop at the planning/specification PR checkpoint; do not implement
runtime behavior or begin 03B automatically.
