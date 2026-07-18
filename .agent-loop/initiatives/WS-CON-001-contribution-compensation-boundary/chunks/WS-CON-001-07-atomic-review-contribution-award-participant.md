# Chunk Contract: WS-CON-001-07 - Atomic Review Contribution And Award Participant

## Goal

Implement the mandatory flush-only participant that creates reviewer and
FinalAcceptance-sourced submitter contributions, evaluates frozen
ContributionRules, creates applicable awards, and returns typed audit/outbox
inputs in the caller-owned Review transaction. It performs no evidence
projection or ART work.

## Risk

L1 economic/canonical-judgment/cross-domain transaction; SLA P1.

## Allowed files

```text
backend/app/modules/contributions/{schemas,repository,service,ports}.py
backend/app/modules/compensation/{repository,service}.py
backend/tests/{test_contributions,test_compensation,test_authorization,test_outbox}.py
docs/spec_contribution_compensation.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/**
.agent-loop/merge-intents/WS-CON-001-07.json
```

## Not allowed

```text
Review policy/model/service/route/composition wiring or commit
public route registration; optional/no-op participant
AUTH catalogue/grant/kernel edits or materialize actions
ART capability/repository/provider call or evidence projection row/event
mutable/delete/void/adjust contribution/award path; reputation scoring
```

## Participant operations

One mandatory typed participant uses the caller AsyncSession and exposes two
ordered operations rather than an omnibus nullable request.

The reviewer operation receives exact locked Review, ReviewLease, versioned
Submission, project/task, reviewer ActorProfile, lease-frozen reviewer
ContributionPolicyVersion, originating `review.decision`
AuthorizationDecision, request/correlation references, and server-derived
stabilized `Submission.artifact_hash`. It never receives FinalAcceptance,
TaskAssignment contribution-source lineage, submitter, or submitter policy.

The submitter operation exists only after REV creates FinalAcceptance and
applies accepted task/assignment effects. It receives exact locked
FinalAcceptance, TaskAssignment, versioned Submission, project/task, submitter
ActorProfile, assignment-frozen submitter ContributionPolicyVersion, the same
authorization/request/correlation lineage, and stabilized artifact hash. It
never uses direct Review/ReviewLease contribution-source fields.

## Acceptance criteria

- [ ] Every valid committed Review creates exactly one reviewer
  `completed_review`. Accept requires exactly one same-chain FinalAcceptance and
  creates one submitter `accepted_submission` from it; needs_revision/reject
  require no FinalAcceptance and create no submitter record.
- [ ] REV calls the reviewer operation after appending Review/findings/
  resolutions, consuming the lease, and closing the queue but before any
  decision branch. It therefore validates Review/ReviewLease lineage without
  requiring branch effects. REV then applies the exact outcome. Accept creates
  FinalAcceptance, sets Task `accepted`, and completes the Assignment before the
  submitter operation. Needs revision keeps the Assignment active and reject
  blocks only the same-task Assignment; neither invokes the submitter operation.
  CON owns none of those lifecycle effects.
- [ ] Repeated idempotent decision returns the same rows; a later revision
  Review creates a distinct reviewer contribution; automated outcomes create
  none.
- [ ] Reviewer uses lease-frozen policy; submitter uses assignment-frozen
  policy. Matching explicit unpaid rule creates no award; compensated rule
  creates at most one money and one project-points award copied from immutable
  definitions.
- [ ] CON copies the supplied stabilized digest exactly into
  ContributionRecord.artifact_hash. It does not load/rederive it or call ART.
- [ ] Each operation validates only its exact source shape and frozen policy.
  Both receive the allowed review.decision reference whose actor, action,
  resource digest, matched reviewer grant/project, request, and correlation
  match the locked transaction; CON does not re-evaluate it.
- [ ] Both operations use caller AsyncSession, stage contribution/award rows,
  return canonical typed audit/outbox inputs, flush, and never commit. REV
  collects results from the reviewer operation and, on accept, the later
  submitter operation, then stages shared audit/outbox rows before the single
  caller commit. CON creates no evidence projection or evidence-request event.
- [ ] CON never reads REV/AUTH repositories or evaluates review.decision. REV
  owns canonical composition and the single route commit.
- [ ] AUTH registration -> CON participant -> REV hidden composition -> AUTH
  evaluator/activation order is proven. Real kernel denies while planned.
- [ ] Fault injection after the reviewer operation, after every branch effect,
  after FinalAcceptance, after the submitter operation, and at every later REV
  audit/outbox step rolls back Review/FinalAcceptance/task/assignment/
  contribution/award/audit/outbox together. The reviewer operation never
  commits independently and no post-commit repair path exists.
- [ ] No FinalAcceptance create action/API exists. Static/runtime proof finds no
  adjudication policy, grant/action, queue/lease, state, decision, contribution,
  conditional branch, readiness check, or initiative dependency.
- [ ] Static/runtime spies prove zero ART capability, repository, preparation,
  provider, or evidence calls in every decision path.
- [ ] PostgreSQL uniqueness, replay, changed-fact conflict, and concurrency tests
  pass; changed code is at least 90 percent and repository floor at least 78.

## Verification

Execute the exact clean isolated CON-07 row in `../RUNTIME_VERIFICATION.md`,
then run:

```bash
(cd backend && .venv/bin/python -m pytest -q tests/test_contributions.py tests/test_compensation.py tests/test_authorization.py tests/test_outbox.py -k '(review or final_acceptance or contribution or award) and (fault or rollback or replay or idempotency or uniqueness or conflict or concurrency or no_art)')
(cd backend && .venv/bin/python -m coverage report --include='app/modules/contributions/*' --fail-under=90)
(cd backend && .venv/bin/python -m coverage report --include='app/modules/compensation/*' --fail-under=90)
(cd backend && .venv/bin/ruff check app/modules/contributions app/modules/compensation tests/test_contributions.py tests/test_compensation.py tests/test_authorization.py tests/test_outbox.py)
```

Pass requires a non-empty selected test set, fault injection after every
reviewer/branch/FinalAcceptance/submitter/audit/outbox stage with total
rollback, exact replay idempotency, changed-fact conflict, database uniqueness
under concurrency, all three decision branches, zero ART/provider calls,
repository coverage at least 78 percent in the same clean run, and both focused
reports at least 90 percent.

## Review and stop

Required tracks: senior, QA, security, product, architecture, docs, reuse, and
test-delta. Stop after the participant. REV, not CON-07, owns integration and
production execution.
