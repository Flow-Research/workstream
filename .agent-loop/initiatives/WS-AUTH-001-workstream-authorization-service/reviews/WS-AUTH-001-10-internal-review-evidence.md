# WS-AUTH-001-10 Internal Review Evidence

Reviewed code SHA: `1623e5b2dd85cc65df92af89989fda2ce7881bd0`

Reviewed planning SHA: `ca52fd6a6c51f78b3e3a10faf77f4ab235843ad2`

Reviewed against trusted main: `5a8a924d9b3b347d4cc74b4682865518539c837e`

Reviewed at: `2026-07-21T11:10:59Z`

Reviewer run IDs: `auth10_plan_core`, `auth10_plan_security_qa`,
`auth10_plan_ops_ci_docs`

Reviewer tracks: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, and test delta

## Deterministic Evidence

- `python3 scripts/check_stale_authorization_docs.py`: PASS.
- `python3 scripts/check_markdown_links.py`: PASS for all changed Markdown.
- `python3 scripts/update_post_merge_memory.py validate-merge-intent --base-ref origin/main`:
  PASS for `WS-AUTH-001-10`, with same-initiative successor
  `WS-AUTH-001-10A` and explicit start required.
- `git diff --check`: PASS.
- This parent changes planning/specification artifacts only. No runtime,
  migration, test, CI, dependency, threshold, or product behavior changed.
- The exact external-gate repair restores `STATUS.md` to trusted-main state and
  uses the canonical evidence provenance label. All three reviewer groups
  passed repair SHA `1623e5b2dd85cc65df92af89989fda2ce7881bd0` with no
  remaining finding; 88 Agent Gate regression tests pass locally.
- GitHub remains the owner of the full sharded suite, aggregate 78 percent and
  changed-authorization 90 percent coverage gates, API E2E, and Agent Gates for
  each implementation child.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| senior engineering | PASS AFTER FIXES | none | The parent and three children are executable and correctly sequenced. |
| QA/test | PASS AFTER FIXES | none | Exact migration predicates, API schemas, replay states, and proof obligations are frozen. |
| security/auth | PASS AFTER FIXES | none | Privacy, lock ordering, replay reauthorization, disclosure, and fail-closed behavior are explicit. |
| product/ops | PASS AFTER FIXES | none | Independent roles, project lifecycle availability, and downstream consumer deferrals are coherent. |
| architecture | PASS AFTER FIXES | none | 10A owns data and planned catalogue registration; 10B/10C exclusively activate their rows. |
| CI integrity | PASS | none | No workflow, threshold, command, dependency, or hosted-test ownership was weakened. |
| docs | PASS AFTER FIXES | none | Parent, children, D32, plan, and canonical reference specification agree. |
| reuse/dedup | PASS AFTER FIXES | none | The design reuses the closed catalogue, PREP, repositories, evidence, and idempotency conventions. |
| test delta | PASS | none | No test was changed, removed, skipped, or weakened. |

## Findings Resolved

The initial combined runtime contract was rejected as too broad and split into
10A data/evidence, 10B reads, and 10C mutations. Review then closed stale
combined-role specification language, privacy and pagination ambiguity,
migration refusal predicates, action/evidence migration custody, PREP lock
ordering, strict request/response schemas, and issue/revoke replay states. The
final planning repair places all five future actions in the existing closed catalogue as
planned rows with exact 10B/10C owners; no parallel allowlist or active surface
is created. The later external-gate repair changes no approved plan semantics.

Valid findings addressed: yes

Open sub-agent sessions: none after evidence publication review

## Remaining Risk And Gate

GitHub Agent Gates, CodeRabbit, and explicit human review remain. This parent
does not authorize migration or runtime work. After merge and signed memory
generation, 10A still requires a separate exact-main explicit start event.
