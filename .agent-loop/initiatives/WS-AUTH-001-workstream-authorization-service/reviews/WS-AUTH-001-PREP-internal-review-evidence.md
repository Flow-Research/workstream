# WS-AUTH-001-PREP Internal Review Evidence

Reviewed code SHA: `38acb8f91d3ddd2edd4cc26fb1e36b67fa130fd9`

Reviewed implementation SHA: `38acb8f91d3ddd2edd4cc26fb1e36b67fa130fd9`

Reviewed against trusted main: `fe0e4492a7de8699c06a52921cbdaa8a1a22e567`

Reviewed at: `2026-07-20T16:07:03Z`

Reviewer run IDs: `rev_plan_core`, `rev_plan_security_qa`,
`rev_plan_ops_ci_docs`

Reviewer tracks: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, and test delta

## Deterministic Evidence

- Ruff passed for the complete backend application and test trees before the
  final test-only proof, then passed for the application and the changed
  `tests/test_authorization.py` module at the reviewed SHA.
- Eighteen focused non-database PREP cases passed locally. They cover every
  supported mutation action plus substitution, forgery, replay, context,
  transaction, rollback, and evidence-failure boundaries.
- Real-PostgreSQL tests cover participant success and rollback, authorization
  failure, evidence and commit failure, bounded timeout, cancellation at every
  transaction phase, concurrent double consumption, and supported lifecycle
  and administrative mutation races in both lock orders.
- A real-PostgreSQL regression proves that the active system-role uniqueness
  constraint rejects a second same-role `access_administrator` grant and that
  PREP selects the sole canonical grant. This closes the literal two-eligible-
  grant ambiguity without changing schema or policy.
- Stale authorization wording, general stale wording, Markdown links,
  loop-memory state, merge-intent validation, and diff integrity pass.
- Alembic remains at `0029_shared_transactional_outbox`; no migration or product
  mutation consumer is included.
- The local environment has no `WORKSTREAM_TEST_DATABASE_URL`. The unchanged
  GitHub Backend workflow remains the authoritative full-suite and coverage
  proof, preserving the 78 percent repository baseline and 90 percent coverage
  requirement for the materially changed authorization subsystem.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| senior engineering | PASS AFTER FIXES | none | The kernel owns lock acquisition, sealed authority, registered consumption, and bounded lifecycle cleanup. |
| QA/test | PASS AFTER FIXES | none | Added cancellation-phase assertions and real database proof that duplicate same-role eligible grants are structurally impossible. |
| security/auth | PASS AFTER FIXES | none | Opaque handles cannot inject authority, cross service/session/context boundaries, or be reused after any terminal path. |
| product/ops | PASS | none | PREP changes authorization infrastructure only; it activates no action and mutates no product resource. |
| architecture | PASS AFTER FIXES | none | Preparation and consumption remain kernel-owned and transaction-bound; the dependency is composition only. |
| CI integrity | PASS | none | No workflow, threshold, exclusion, dependency, or full-suite command was weakened. |
| docs | PASS | none | The contract now records the sole-grant invariant and the exact future expansion obligation. |
| reuse/dedup | PASS | none | The implementation reuses canonical action plans, locks, decision completion, evidence, and repositories. |
| test delta | PASS | none | No assertion, test, threshold, or database coverage was removed or weakened. |

## Findings Resolved

Valid findings addressed: yes

Open sub-agent sessions: none

Early candidates lacked complete race/failure proof, allowed an insufficiently
sealed prelocked boundary, and did not bind consumption to the issuing service
and exact context. The repaired implementation makes prelocked entry points
require a service-private registered token, derives authority only through the
kernel and binds sealed authority to the root transaction. Exact consume
attempts tombstone before evaluation; pre-consume cancellation or rollback
invalidates the issuance through transaction binding and cleanup. The final
QA retry added real-database proof for the unique active system-role grant
invariant. All nine tracks passed the reviewed SHA with no remaining finding.

## Remaining Risk And Gate

GitHub Backend, Agent Gates, CodeRabbit, and explicit human review remain. This
chunk deliberately stops before any product consumer or migration; consumer
integration requires a separately approved same-initiative chunk.
