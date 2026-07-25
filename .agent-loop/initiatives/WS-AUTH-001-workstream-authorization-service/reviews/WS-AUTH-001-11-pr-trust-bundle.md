# WS-AUTH-001-11 PR Trust Bundle

## Chunk

`WS-AUTH-001-11` — Project Read Cutover Planning Parent

Merge intent: `.agent-loop/merge-intents/WS-AUTH-001-11.json`

## Goal and human-approved intent

Replace token-role authority on the project read surface with local grants as a
hard cutover. The user explicitly rejected backward compatibility and approved
starting AUTH-11. Signed explicit-start workflow run `30167274426` succeeded.

## What changed and why

- D34 makes AUTH-11 planning-only and assigns one complete surface family to
  each of 11A, 11B, 11C1, and 11C2.
- The inventory matches all ten current project GET routes and the deferred
  self authorization-context route, including project/guide/child bindings.
- 11A registers eleven actions and adds two read-only permissions plus role and
  evidence parity in migration `0035`, without route activation.
- 11B cuts over project identity and self authorization context.
- 11C1 cuts over six setup/draft diagnostic reads.
- 11C2 cuts over three effective-policy/active-guide reads.

## Design chosen

Project identity continues to use `project.read`. Setup diagnostics and
effective policy receive distinct read-only permissions so Project Manager,
system Operator, and covered Audit Authority can inspect through safe API
projections without gaining mutations. Finance Authority, Access Administrator,
and contributors do not receive those sensitive permissions. Contributors may
receive only minimal exact-project identity unless 11C2 later proves a safe
active-guide schema.

## Alternatives rejected

- One combined runtime cutover was too broad for L1 review.
- Token-role fallback or dual authorization would violate the hard cutover.
- Mapping sensitive reads to generic `project.read` would overexpose data.
- Reusing management permissions for inspection would conflate reads and writes.
- Denying Operator/Audit inspection would force unsupported database access.

## Scope and product behavior

This PR changes planning/process artifacts and one merge intent only. It adds no
runtime behavior, migration, route, action activation, test, workflow, or
dependency. Signed automation remains canonical live state.

## Acceptance criteria proof

The plan records literal routes, exact ActionIds, resource targets, permission
mappings, role/scope projections, concealment requirements, migration custody,
coverage floors, documentation ownership, child sequencing, and stop rules.
Only 11A is named as successor, and it remains inactive.

## Tests/checks run

- Merge-intent validator: local PASS.
- Stale authorization and Workstream wording scans: local PASS after wording
  repair; the original hosted stale-authorization run failed.
- Markdown link scan: local PASS for twelve changed Markdown files.
- Agent gates: 100 local tests PASS; repaired hosted rerun remains required.
- Diff integrity: local PASS.

No local four-hour backend suite was run for this documentation-only parent.
Every runtime child requires the hosted GitHub `Backend / test` full suite,
semantic lanes, API E2E, 78 percent repository coverage, and applicable 90
percent subsystem reports before merge.

## Test delta and CI integrity

No tests, workflows, package scripts, dependencies, skips, or thresholds
changed. QA and test-delta reviewers confirmed that future role, scope,
cross-project, cross-guide, child-binding, concealment, OpenAPI, migration, and
live API proof is explicit.

## Reviewer results and external review

All nine required internal tracks passed the repaired exact planning SHA
`81e470306f81edafb8cb592dd53d036ee07ba7e7` after fixes: senior engineering,
QA/test, security/auth, product/ops, architecture, CI integrity, docs,
reuse/dedup, and test delta. GitHub Agent Gates then identified stale legacy
authorization vocabulary in the new prose; the wording was repaired without
changing design or weakening the scanner, and the response is recorded in
`WS-AUTH-001-11-external-review-response.md`. CodeRabbit and repaired hosted
checks remain external gates.

## Remaining risks and follow-up

The principal risk is accidental projection broadening during runtime work.
Each child therefore needs a separate signed start and exact-head L1 review.
11A must land before 11B; 11B before 11C1; and 11C1 before 11C2.

## Human review focus and merge ownership

Review the eleven-action inventory, two read-only permissions, Operator/Audit
inspection boundary, contributor minimal projection, literal resource binding,
and absence of token-role fallback. The user retains final approval authority
for this specific PR and merge.
