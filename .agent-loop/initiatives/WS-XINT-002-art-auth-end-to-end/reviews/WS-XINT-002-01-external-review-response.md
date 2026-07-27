# WS-XINT-002-01 External Review Response

## Comments addressed

- GitHub Backend: updated the expected public-schema fingerprint for migration 0036.
- GitHub Backend: restored the historical permission and action ordering before crossing migration 0034's digest guard, and extended the round-trip test through revision 0033.
- GitHub Backend: updated three integration assertions that still expected the pre-reconciliation 76-permission total; the exact affected lifecycle test now passes against the closed 71-permission catalogue.
- GitHub Backend: kept 0036-only action owners out of migration-0021/0022 stage assertions; both exact historical-stage tests now pass while current-head 0036 coverage remains intact.
- CodeRabbit: marked the complete superseded AUTH–ART handoff as historical rather than leaving later sections phrased as live direction.
- CodeRabbit: corrected the 06B checker-output action-to-permission mapping.
- CodeRabbit nits: centralized obsolete upload identifiers, tightened migration refusal assertions, asserted removed SQL tokens are absent, and qualified evidence predicates without string rewriting.
- Internal corrective security review: kept the direct immutable-audit predicate over every audit row, including orphaned non-null idempotency references, and added unchanged-state regression coverage.

## Comments deferred

- CodeRabbit's suggestion that `_replace` uses physical rather than logical constraint names was not applied. Alembic's repository naming convention expands these logical names to the `ck_audit_events_*` physical names; migrations 0035 and 0036 use the established pattern, and the DB-backed migration proof executes the replacement.

## Human decisions needed

None.

## Commands rerun

- Ruff format and lint over the changed migration and tests.
- Focused isolated PostgreSQL migration round-trip, refusal-shape, and predecessor-downgrade tests.
- Stale authorization and artifact-contract scans, Markdown link checks, and lightweight repository gates.
- Exact-head GitHub Actions and CodeRabbit checks after the corrective commit.

## Remaining risks

- The PR is not merge-ready until the new exact head passes hosted Backend, Agent Gates, and CodeRabbit checks.
