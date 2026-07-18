# Chunk Contract: WS-CON-001-03C - Contribution And Award Persistence

## Goal and risk

Persist immutable contribution/award truth against exact merged
FinalAcceptance, Review, ReviewLease, TaskAssignment, and Submission targets.
L1 history/economic risk.

## Allowed files

```text
backend/app/modules/contributions/{__init__,models,schemas,repository}.py
backend/app/modules/compensation/{models,schemas,repository}.py
backend/app/db/models.py
backend/alembic/versions/<next>_contribution_award_truth.py
backend/tests/{test_contributions,test_compensation,test_alembic}.py
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/**
.agent-loop/merge-intents/WS-CON-001-03C.json
```

## Not allowed

```text
review model/service/composition edits
service, route, background executor, receipt, artifact, reputation or legacy accepted-work settlement row behavior
mutable/void/delete/adjust path, dependency or CI weakening
```

## Acceptance criteria

- [ ] Existing Submission is the version identity. Project/task/submission/
  FinalAcceptance/Review/lease/assignment/contributor and stabilized
  artifact_hash lineage are same-chain and non-null as applicable. No
  SubmissionVersion entity or `submission_version_id` alias is added.
- [ ] Reviewer rows are completed_review and bind source Review + ReviewLease +
  reviewer + reviewer-frozen policy, with FinalAcceptance/assignment sources
  null. Submitter rows are accepted_submission and bind source FinalAcceptance
  + TaskAssignment + submitter + submitter-frozen policy, with direct Review/
  lease sources null; they are impossible for needs_revision/reject.
- [ ] Partial uniqueness enforces one completed_review per source Review and one
  accepted_submission per source FinalAcceptance. Contributor identity is a
  validated lineage field, never part of either uniqueness key. Checks reject
  mixed, incomplete, or wrong-type source shapes.
- [ ] `source_final_acceptance_id` references REV's immutable record; the exact
  FinalAcceptance task/project/submission/submitter/source-Review chain matches
  the contribution, but CON does not infer acceptance from that Review.
- [ ] Each award references the exact ContributionRecord, its frozen
  ContributionPolicyVersion, matching rule/definition, same project/contributor/
  contribution type, and same-project/instrument adapter binding.
- [ ] Unique `(contribution_record_id, instrument_type)` enforces at most one
  money and one project_points award; quantity is exact and positive.
- [ ] Database enforces immutability/at-most-one but does not require a
  contribution child during staged Review persistence before CON-07 flushes.
- [ ] At-least-one per valid Review is deferred to CON-07 + REV-10 + preflight.
- [ ] At-least-one accepted_submission per FinalAcceptance is deferred to
  CON-07 + REV hidden composition + preflight.
- [ ] No mutable/void/delete/adjust path or legacy accepted-work settlement row/reputation schema.

## Verification and reviewers

Execute CON-03C in `../RUNTIME_VERIFICATION.md`; changed subsystems are at least
90 percent. Senior engineering, QA/test, security/auth, product/ops,
architecture, docs, reuse/dedup and test-delta are required. Stop if exact
REV-04 runtime FinalAcceptance/Review/ReviewLease targets are not merged. Merged
REV PR #128 is planning authority only and does not satisfy that runtime gate.
