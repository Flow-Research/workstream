# Chunk Contract: WS-CON-001-PLAN2 - Final Acceptance Reconciliation

## Goal

Adopt the human-approved v0.1 `Review(accept) -> FinalAcceptance ->
accepted_submission` boundary in WS-CON planning and shared product wording,
without implementing runtime behavior or introducing adjudication.

## Risk

L0 architecture/economic/lifecycle specification; P1.

## Allowed files

```text
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/**
README.md only exact review/final-acceptance/contribution wording
docs/architecture_brief/workstream_architecture_brief.md only contribution principle wording
docs/architecture_data_model.md only FinalAcceptance/contribution lineage and non-mutating reviewer-quality event tokens
docs/architecture_lifecycle_state_machine.md only accepted transition facts and no-adjudication invariant
docs/architecture_lockdown.md only v0.1 acceptance/contribution invariants
docs/architecture_system_architecture.md only replace second-review flags with non-mutating post-decision quality-audit observations
docs/glossary.md only FinalAcceptance/ContributionRecord definitions and exact no-adjudication clarification
docs/operations_reviewer_workflow.md only exact decision effects and non-mutating quality audit
docs/operations_operator_workflow.md only acceptance sequence
docs/operations_payment_reputation.md only contribution/award trigger wording and non-mutating reviewer-quality event tokens
docs/operations_queue_policy.md only accepted-lane required facts
docs/product_first_user_flows.md only reviewer decision effects
docs/risk_register.md only reviewer-quality mitigation wording that could imply a second lifecycle decision
docs/template_project_guide.md only replace mandatory second-review gating with non-mutating quality-audit sampling
docs/template_review_packet.md only replace second-review gating fields with non-mutating quality-audit fields
```

## Not allowed

```text
backend application, migrations, runtime tests, workflows, dependencies
REV/AUTH/ART initiative or runtime edits
reference-spec/PDF byte edits, restoration, rename, or replacement
SubmissionVersion entity or submission_version_id compatibility alias
adjudicator grant/action implementation; adjudication policy, queue, lease,
state, decision, contribution type, branch, readiness gate, or initiative dependency
new authorization action for FinalAcceptance creation
manual/public FinalAcceptance creation API
rewriting historical docs/review_* internal-review evidence
```

## Acceptance criteria

- [x] REV owns immutable `FinalAcceptance`, creates it only as an internal
  consequence of an authorized `Review(accept)`, and exposes no independent
  create action or API.
- [x] Existing immutable `Submission` remains the version identity. The
  external `submission_version_id` shorthand maps to canonical `submission_id`;
  no duplicate entity or alias is introduced.
- [x] FinalAcceptance has exact task/project/submission/Review/submitter/
  reviewer/time/policy-context lineage and unique task, Review, and Submission
  constraints. REV must type the policy-context reference against its canonical
  immutable review-policy fact before its persistence chunk starts.
- [x] `completed_review` remains directly sourced from every valid human Review
  and ReviewLease. `accepted_submission` is sourced only from FinalAcceptance
  plus TaskAssignment and never inferred directly from Review.decision.
- [x] One completed_review exists per Review and one accepted_submission per
  FinalAcceptance; needs_revision/reject create no FinalAcceptance or submitter
  contribution.
- [x] Outcome effects match REV's canonical lifecycle exactly: accept sets Task
  `accepted` and Assignment `completed`; needs_revision sets Task
  `needs_revision` and keeps Assignment `active`; reject sets Task `rejected`
  with a bounded human reason and blocks only the same-task Assignment with its
  source Review. No `closed/review_rejected` token, grant mutation, or unrelated
  task effect is introduced.
- [x] The REV request owns one transaction. REV creates Review and optional
  FinalAcceptance, invokes CON flush-only contribution/award behavior, stages
  shared audit/outbox records, and commits once.
- [x] Any CON failure rolls back Review, FinalAcceptance, task/assignment
  effects, contributions, awards, audit, and outbox together. External
  fulfillment starts only after commit.
- [x] Core contribution creation copies stabilized Submission artifact-hash
  lineage and makes zero ART/provider calls.
- [x] WS-CON has no adjudication lifecycle, action, state, queue, contribution,
  authorization, or release dependency. Existing unrelated AUTH role catalogue
  state is neither expanded nor implemented here.
- [x] Required internal reviewers pass the exact final snapshot; no sub-agent
  session remains open.

## Verification

```bash
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_agent_gates.py
git diff --check
test -z "$(git diff --name-only -- backend)"
```

## Reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, and test-delta. CI integrity is N/A only if no script, workflow,
dependency, test, threshold, or runner changes.

## Stop

Stop after reviewed specification reconciliation. Do not implement
FinalAcceptance, start CON-01/03C/07, push, or open a PR automatically.
