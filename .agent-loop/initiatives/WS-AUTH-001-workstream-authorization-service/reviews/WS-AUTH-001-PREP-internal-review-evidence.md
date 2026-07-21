# WS-AUTH-001-PREP Internal Review Evidence

Reviewed code SHA: `8d9436f2f76c81a37b0b5f17271789099da714b2`

Reviewed implementation SHA: `38acb8f91d3ddd2edd4cc26fb1e36b67fa130fd9`

Reviewed pre-sync status SHA: `5e190aae142c354bf4293041d2375f124d4a51ce`

Reviewed sync SHA: `6c1e296fca8390aeeed9f5bdf63b649a783c5030`

Reviewed CI-repair SHA: `eaa7073d45fa4a8382f2b44401b93cae7df34744`

Reviewed trusted-main CI-acceleration sync SHA:
`9e926d04511e04122beeb1f88110f80b88c34907`

Reviewed external-response SHA: `11a64da9406d0be5fb35ab32ce3ff742d105c648`

Reviewed PostgreSQL shard repair SHA: `349ac3130c61c76ccfec1bdb723d5ca614d44fe2`

Reviewed trusted-main ENG explicit-start sync SHA:
`57ee7a30586ad69c02d23d4e6069bcd129e0ec01`

Original implementation entry base: `fe0e4492a7de8699c06a52921cbdaa8a1a22e567`

Reviewed against trusted main: `58d0514aa5f6751a310d750f8dab8a946ca08fa5`

Reviewed at: `2026-07-21T06:08:29Z`

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
- Thirteen focused PostgreSQL PREP and authority-race cases pass after repairing
  the fixture's bootstrap state, canonical audit assertions, and teardown.
- A real-PostgreSQL regression proves that the active system-role uniqueness
  constraint rejects a second same-role `access_administrator` grant and that
  PREP selects the sole canonical grant. This closes the literal two-eligible-
  grant ambiguity without changing schema or policy.
- Stale authorization wording, general stale wording, Markdown links,
  loop-memory state, merge-intent validation, and diff integrity pass.
- Alembic remains at `0029_shared_transactional_outbox`; no migration or product
  mutation consumer is included.
- The local environment has no `WORKSTREAM_TEST_DATABASE_URL`. The trusted-main
  sharded GitHub Backend workflow, unchanged by PREP, remains the authoritative
  full-suite and coverage proof, preserving the 78 percent repository baseline
  and 90 percent coverage requirement for the materially changed authorization
  subsystem.

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
invariant. After hosted shard 2 exposed fixture drift, the repair established
one valid bootstrap administrator, restored the authority-control singleton,
used canonical audit fields and tokens, and retained the privacy-safe
`permission_not_granted` mutation-first result. All nine tracks passed exact
reviewed SHA `8d9436f2f76c81a37b0b5f17271789099da714b2` with no remaining finding.

## Remaining Risk And Gate

GitHub Backend, Agent Gates, CodeRabbit, and explicit human review remain. This
chunk deliberately stops before any product consumer or migration; consumer
integration requires a separately approved same-initiative chunk.
