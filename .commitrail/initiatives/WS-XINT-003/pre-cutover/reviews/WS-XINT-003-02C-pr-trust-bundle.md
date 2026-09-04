# PR Trust Bundle: WS-XINT-003-02C

## Intent and scope

Register the complete unavailable REV authorization vocabulary and exact fixed
service principals before REV implementation begins. This chunk adds four
planned actions, six closed identities, six static matrix rows, and database
parity only.

## Design and safety

- Catalogue totals become 71 permissions, 100 actions, 45 active, and 55 planned.
- The fixed-service registry becomes fourteen rows with twenty-two memberships.
- Two separate reconciliation identities share only `review.reconcile.run`;
  future REV code must derive their modes server-side.
- Evidence-ingest actions remain planned, outside the service matrix, and
  protected by `FUTURE_INTENT_REQUIRED_ACTIONS`.
- Migration 0049 seeds no principal or authority and refuses unsafe downgrade
  after direct/linked action evidence or use of any new identity.

## Exclusions

No REV queue, lease, finding, decision, revision, recovery, projection,
lifecycle behavior, PREP protocol, route, worker, provider I/O, or action
activation is included.

## Evidence

- Ruff: pass.
- Mypy: pass.
- Focused tests: 33 passed.
- Changed-module coverage: 100.00 and 97.89 percent.
- Exact DB/API collection: 16 tests collected.
- Internal architecture, security, product, QA, senior, CI, test-delta, reuse,
  and docs review: pass; valid findings resolved.
- Markdown links, stale review contracts, and diff whitespace: pass.

Hosted GitHub Actions must provide PostgreSQL schema/API execution, full-suite
coverage (repository 78 percent and changed authorization/actor subsystems 90
percent), and the final exact-head merge evidence.

## Human review focus

Verify the four action/permission/owner triples, the six identity-to-action
rows, the exact 0048-to-0049 constraint transformation, and that no availability
or product behavior changed.
