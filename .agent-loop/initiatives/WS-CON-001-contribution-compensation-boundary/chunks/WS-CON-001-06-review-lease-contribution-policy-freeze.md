# Chunk Contract: WS-CON-001-06 - ReviewLease Contribution-Policy Freeze Participant

## Goal

Deliver the narrow CON policy lookup/freeze participant that REV invokes inside
the review-claim transaction. Reviewer award eligibility is frozen before
review work begins.

## Risk

L1 economic/review lifecycle/authorization; SLA P1.

## Allowed files

```text
backend/app/modules/contributions/{ports,service}.py
backend/tests/{test_contributions,test_authorization}.py
docs/spec_contribution_compensation.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/**
.agent-loop/merge-intents/WS-CON-001-06.json
```

## Not allowed

```text
review queue/lease policy, model, migration, service, route, or composition
AUTH catalogue/grant/kernel changes; review decision or award creation
task assignment changes; provider/artifact/adapter calls
```

## Acceptance criteria

- [ ] Port accepts caller AsyncSession and canonical locked project/claim facts,
  locks one active ContributionPolicy and published version plus referenced
  definitions/bindings, returns the exact version ID, and never commits.
- [ ] Missing/inactive/invalid policy or binding returns stable failure with no
  CON/audit/outbox partial state.
- [ ] REV-owned ReviewLease has immutable non-null
  `reviewer_contribution_policy_version_id` and REV owns its write/wiring.
- [ ] review.claim uses exact active same-project reviewer ProjectRoleGrant;
  unrelated project/admin grants do not substitute. No-self-review and REV
  lifecycle guards remain REV-owned; no adjudication behavior or dependency is
  introduced.
- [ ] AUTH-PREP locks reviewer authority and prepares its exact bound handle;
  REV locks queue/lease/Submission facts; CON locks policy dependencies and
  returns the version; REV recomposes final facts; AUTH consumes/evaluates once
  before REV writes the lease freeze. CON flushes only and never commits.
- [ ] CON hidden port and REV hidden composition merge while review.claim
  remains planned; AUTH later integrates the evaluator and alone activates.
- [ ] Policy publish and binding state versus claim pass both lock orders;
  changed modules stay at least 90 percent and global floor stays 78.

## Verification

Execute the exact clean isolated CON-06 row in `../RUNTIME_VERIFICATION.md`,
then run:

```bash
(cd backend && .venv/bin/python -m pytest -q tests/test_contributions.py tests/test_authorization.py -k '(review or lease or claim or policy) and (freeze or lock or race or rollback or authorization or deny or no_self_review)')
(cd backend && .venv/bin/python -m coverage report --include='app/modules/contributions/*' --fail-under=90)
(cd backend && .venv/bin/ruff check app/modules/contributions tests/test_contributions.py tests/test_authorization.py)
```

Pass requires a non-empty selected test set, caller-session flush-only freeze,
both publish/claim and binding/claim race orders, missing-policy rollback,
same-project reviewer authorization with unrelated-grant and self-review
denials, repository coverage at least 78 percent in the same clean run, and
focused contribution coverage at least 90 percent.

## Review and stop

Required tracks: senior, QA, security, product, architecture, docs, reuse, and
test-delta. Stop if REV lease schema/caller facts or review.claim authority are
not merged. CON owns no review composition.
