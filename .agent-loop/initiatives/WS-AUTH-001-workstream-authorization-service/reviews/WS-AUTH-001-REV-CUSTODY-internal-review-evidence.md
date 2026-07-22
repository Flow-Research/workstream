# WS-AUTH-001-REV-CUSTODY Internal Review Evidence

Reviewed code SHA: `438c2bcf6a91b97f46264a1b6e5d0110a28f16d5`

Reviewed implementation SHA: `baa86dfe94015f66570844ce81ed1310729cded1`

Reviewed pre-CI status SHA: `9150960ce1f4fdd1f7a02129401f97f43a5ec667`

Reviewed CI-repair SHA: `438c2bcf6a91b97f46264a1b6e5d0110a28f16d5`

Reviewed against trusted main: `be2a79a243ec50049c37f1f634322a9b3ab895ba`

Reviewed at: `2026-07-20T12:42:54Z`

Reviewer run IDs: `rev_plan_core`, `rev_plan_security_qa`,
`rev_plan_ops_ci_docs`

Reviewer tracks: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, and test delta

## Deterministic Evidence

- Ruff passed for the complete backend application and test trees.
- Sixty-three focused catalogue, fail-closed construction, documentation
  parity, and real-kernel custody cases passed after review repair. The 19 REV
  actions each deny as sensitive `action_unavailable` evidence with exact
  action and permission and cannot reach revalidation or administrative grant
  dependencies.
- The literal test fixture independently freezes all 19 action, permission,
  owner, and `planned` values. Exact documentation parsing checks both canonical
  tables, mappings, seven owner cardinalities, counts, and operations invariants.
- Stale Workstream and authorization wording scans, Markdown links, loop-memory
  state, merge-intent validation, Alembic `0029_shared_transactional_outbox`
  head, migration-directory no-diff, and diff integrity pass.
- No workflow, dependency, ActionId, PermissionId, mapping, availability,
  evaluator, grant, route, service identity, matrix membership, persistence,
  audit schema, or migration changed. The four proposed REV lifecycle actions
  remain unregistered.
- A broader local authorization/auth command passed 288 non-database cases and
  then failed closed because `WORKSTREAM_TEST_DATABASE_URL` is absent; its
  coverage output is not claimed. The unchanged GitHub Backend workflow remains
  the mandatory database/full-suite proof for the 78 percent repository-wide
  and 90 percent authorization-subsystem coverage floors.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| senior engineering | PASS AFTER FIXES | none | Restored the retained ART no-migration invariant before exact-SHA re-review. |
| QA/test | PASS AFTER FIXES | none | Corrected one broken ART docs regression and one stale REV-pending statement. |
| security/auth | PASS | none | All 19 actions stay planned and unavailable; no grant, runtime, audit, or persistence path changes. |
| product/ops | PASS AFTER FIXES | none | Custody labels grant no reviewer, Operator, or service authority; PREP remains human-gated. |
| architecture | PASS | none | AUTH changes activation-custody metadata while REV retains facts, guards, and behavior. |
| CI integrity | PASS AFTER FIXES | none | No CI weakening; focused proof is green and hosted full coverage remains mandatory. |
| docs | PASS AFTER FIXES | none | Spec, operations, custody plan, and exact parsed tables now agree. |
| reuse/dedup | PASS | none | Existing catalogue validator, parser pattern, kernel helpers, and evidence abstraction are reused. |
| test delta | PASS AFTER FIXES | none | No removal, skip, xfail, deselection, assertion relaxation, or threshold change. |

## Findings Resolved

Valid findings addressed: yes

Open sub-agent sessions: none

Initial candidate `c95239b9` replaced the exact retained sentence `The ART
transfer adds no migration` and left a stale spec statement claiming REV
custody was still pending. Repair candidate `baa86dfe` restores the independent
ART invariant, separately records the REV no-migration truth, and states that
all 19 REV rows now have AUTH custody while remaining planned. All nine tracks
passed exact-SHA re-review with no remaining finding.
Status candidate `9150960c` adds only the canonical review-log chronology; all
nine tracks confirmed that exact SHA without a remaining finding.
GitHub Agent Gates then found that the existing PREP successor heading used an
em dash while the canonical schema-v2 parser requires ` - `. Repair
`438c2bcf` normalizes only that delimiter, starts no PREP work, and passes exact
merge-intent validation plus all nine exact-SHA repair tracks.

## Remaining Risk And Gate

GitHub Backend, Agent Gates, external review, and explicit human review remain.
All 19 REV actions remain planned and unavailable. PREP is the only declared
successor and requires signed merge memory plus a separate explicit human start.
