# WS-AUTH-001-ART-CUSTODY Internal Review Evidence

Reviewed code SHA: `a20ab6b2004e2f7a13e1e0d600595f0af7d67985`

Reviewed implementation SHA: `abb3fb1a035f544f5ee07b7d725451dfa2d90864`

Reviewed pre-CI status SHA: `125e018b8fa13b38a0cc66dfa9c724c040d84ae1`

Reviewed against trusted main: `42a89b2deac8fc7672556a567a6124f8a4e5d423`

Reviewed at: `2026-07-20T10:49:58Z`

Reviewer run IDs: `plan_product`, `plan_qa`, `plan_security`

Reviewer tracks: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, and test delta

## Deterministic Evidence

- Ruff passed for the complete backend application and test trees.
- Forty-five focused catalogue, fixed-service matrix, fail-closed construction,
  documentation-parity, and real-kernel custody cases passed. The 25 ART
  actions each deny as sensitive `action_unavailable` evidence with exact
  action and permission and cannot reach revalidation or administrative grant
  dependencies.
- The literal test fixture independently freezes all 25 action, permission,
  owner, and `planned` values. Exact documentation parsing rejects missing,
  extra, duplicate, or wrong-custodian rows and checks owner cardinalities,
  spec mappings, counts, and operations invariants.
- Stale Workstream and authorization wording scans, Markdown links, loop-memory
  state, merge-intent validation, Alembic `0029_shared_transactional_outbox`
  head, migration-directory no-diff, and diff integrity pass.
- No workflow, dependency, ActionId, PermissionId, mapping, availability,
  evaluator, grant, route, service identity, matrix membership, persistence,
  audit schema, or migration changed.
- The unchanged GitHub Backend workflow remains the mandatory hosted full-suite
  proof for the 78 percent repository-wide and 90 percent authorization
  subsystem coverage floors. No local full-suite result is claimed.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| senior engineering | PASS AFTER FIXES | none | Exact bounded documentation parsing replaced permissive substring proof. |
| QA/test | PASS AFTER FIXES | none | Literal fixtures, exact docs parity, and exploding downstream dependencies close self-derived proof gaps. |
| security/auth | PASS | none | All 25 actions stay planned and unavailable; no database, audit, grant, or runtime path changes. |
| product/ops | PASS | none | `OPERATOR` is custody-only, retry stays independent, and ART -> REV sequencing remains human-gated. |
| architecture | PASS | none | AUTH changes activation custody metadata while ART retains feature facts, guards, and behavior. |
| CI integrity | PASS | none | No CI weakening; hosted full coverage remains mandatory. |
| docs | PASS | none | Spec, operations, custody, state, queue, map, and contract wording are consistent. |
| reuse/dedup | PASS | none | Existing catalogue/kernel helpers are reused; the sole literal fixture and parser remain test-only. |
| test delta | PASS | none | No test removal, skip, xfail, deselection, assertion relaxation, or threshold change. |

## Findings Resolved

Valid findings addressed: yes

Open sub-agent sessions: none

Initial candidate `e7c2602e` used production enum members as expected owner
truth and only checked documentation substring presence. Repaired exact code
SHA `abb3fb1a` uses literal action/permission/owner/availability truth, parses
the bounded canonical tables exactly, asserts operations invariants, and fails
if any planned ART action reaches a downstream authorization dependency. All
nine implementation tracks pass with no remaining finding. Final candidate
`125e018b` adds only deterministic status/review-log updates; all nine tracks
confirmed that exact SHA without a remaining finding. GitHub Agent Gates then
exposed a trusted-main fixture invariant for four authored status files. Repair
`a20ab6b2` restores those files byte-for-byte to `origin/main` without changing
the gate or implementation; all 88 agent-gate regression tests and all nine
exact-SHA repair tracks pass.

## Remaining Risk And Gate

GitHub Backend, Agent Gates, external review, and explicit human review remain.
All 25 ART actions remain planned and unavailable. REV custody remains a
separate successor requiring signed memory and an explicit human start.
