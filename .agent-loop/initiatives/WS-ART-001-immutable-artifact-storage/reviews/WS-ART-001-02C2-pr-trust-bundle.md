# PR Trust Bundle: WS-ART-001-02C2

## Chunk

`WS-ART-001-02C2` - Verification Publication And Fencing

Reviewed implementation SHA: `e59a6dfc977fa63ad7177ab9adb8338333aa1daf`

Trusted base: `42a89b2d`

Merge intent: `.agent-loop/merge-intents/WS-ART-001-02C2.json`

## Goal And Human-Approved Intent

Resolve committed artifact puts, publish bounded pending work, verify complete
provider reads, and fence every terminal transition without activating product
callers, recovery, Operator routes, or background write replay.

## What Changed And Why

- Added caller-only provider write execution and read-only ambiguous-result
  observation so acknowledgement loss cannot cause a second write.
- Added durable verification jobs and separate operation, observation, and
  verification receipts for auditable outcomes.
- Added PostgreSQL executor UUID/generation leases and same-transaction
  authority revalidation so stale or revoked work cannot commit terminal facts.
- Added bounded post-commit publication scanning and total complete-read
  deadlines.
- Integrated current main and linearized migrations as outbox 0029 followed by
  artifact verification 0030, eliminating the duplicate-head collision.

## Design And Alternatives

The orchestrator owns provider execution through `ArtifactStore`; product
services do not receive raw provider access. Background resolution observes
only and never retries writes. Production tasks remain deny-only with no Beat
schedule. Ad hoc provider factories, a second AUTH evaluator, background write
replay, and dual scanner/outbox publication were rejected.

## Scope Control And Product Behavior

No task, submission, checker, review, revision, contribution, compensation,
reputation, deletion, recovery, Operator API, R2, Flow Node, or product-cutover
behavior changed. Review decisions remain `accept`, `needs_revision`, and
`reject`. The three ART internal actions remain planned and inactive.

## Acceptance Criteria Proof

- [x] One linear Alembic head after trusted main integration.
- [x] Provider writes occur only in the caller-owned orchestrator path.
- [x] Acknowledgement loss resolves through read-only observation.
- [x] Missing, mismatch, conflict, unavailable, and verified outcomes are typed
  and fenced.
- [x] Stale executor/generation or authority drift writes zero terminal facts.
- [x] Verification reads have a total deadline and lease safety margin.
- [x] Publication is bounded, duplicate-safe, post-commit, and not scheduled in
  production.
- [x] Exactly one schema-v2 merge intent names inactive successor `02C3` and
  requires a separate explicit start.

## Tests And Checks

```text
Alembic heads: 0030_artifact_verification (single head)
Fresh isolated migration integration: 3 passed
Agent gates: 88 passed
Focused ART matrix: 342 passed, 1 transient failure, coverage 92.75% (floor 90%)
Exact failed parameter rerun: 1 passed
Paired denial matrix rerun: 2 passed
Reviewer repeated denial matrix: 12/12 passed
Verification + architecture smoke: 15 passed
Ruff: PASS
Stale wording/contracts: PASS
Markdown links: PASS
git diff --check: PASS
```

The transient failure is disclosed, not converted into a green aggregate. It
is non-reproduced and reviewers found no assertion weakening or fixture defect.

## CI Integrity And Test Delta

No workflow, threshold, ignore, skip, xfail, retry, or failure-bypass change was
introduced. The 90 percent affected-subsystem floor and 78 percent repository
floor remain intact. Thirty-two named tests were added and none removed or
skipped.

## Reviewer Results

All nine exact-SHA tracks completed: senior engineering PASS; security PASS;
product/ops PASS; reuse PASS; CI integrity PASS; docs PASS; architecture, QA,
and test delta PASS WITH LOW RISKS. No required fix remains and no reviewer
session is open.

## External Review

| Source | Status | Notes |
|---|---:|---|
| GitHub Agent Gates | Pending | Must run on the published evidence head. |
| GitHub Backend | Pending | Must prove final isolated suite and coverage floors. |
| CodeRabbit | Pending | Fresh current-head review required after publication. |
| Human review | Pending | Only the user may approve this PR for merge. |

## Remaining Risks And Follow-Up

- Monitor the non-reproduced denial-test observation in hosted CI.
- AUTH-owned action activation, 02C3 recovery, 02D Operator/readiness work, and
  product cutover remain separate, explicitly started chunks.

## Human Review Focus

- Can any stale generation, changed resource fact, or revoked identity persist
  terminal state?
- Can acknowledgement loss cause a second provider write?
- Does migration 0030 safely compose after main's outbox 0029?
- Are hidden tasks still deny-only, unscheduled, and unreachable by products?

## Human Merge Ownership

- [ ] I can explain what changed and why.
- [ ] I understand the disclosed transient-test risk.
- [ ] GitHub CI and external review pass on the final head.
- [ ] I explicitly approve this PR for merge.
