# WS-AUTH-001-09E PR Trust Bundle

## Goal

Admit only explicitly provisioned fixed service actors into central AUTH while
keeping every feature action unavailable and every human authority path
separate.

## Changes And Design

- Introduces structurally distinct human and service authorization contexts.
- Resolves service tokens through the existing exact actor lookup with no first
  access, human rate control, role grant, or fallback path.
- Dispatches services before human/admin evaluation, checks exact ActionId
  matrix membership before availability, and revalidates locked actor rows in
  the caller transaction.
- Stages timestamps only for initially active service rows and rolls them back
  on denial, cancellation, or persistence failure.
- Adds focused unit, PostgreSQL, and real HTTP lifecycle/drift proof plus current
  specification and operations guidance.

## Scope Control

No service feature action, ART/REV/CON call site, migration, schema, role,
grant, payment, review, revision, or reputation behavior is activated. ART PR
#154 and its owned `0028_artifact_admission` are already merged; AUTH-09E adds
or allocates no migration.

## Proof And CI Integrity

- 312 focused actor/auth/API-control tests passed on isolated PostgreSQL.
- 10 repair tests passed for inactive observation suppression and real
  revalidation drift.
- Real isolated API contract E2E passed.
- Ruff, 90.3 percent docstring coverage, stale scans, Markdown links, diff
  integrity, and 88 agent gates passed.
- No tests, assertions, skips, xfails, workflows, exclusions, or coverage
  thresholds were weakened.
- GitHub Backend remains the authoritative mandatory proof for the full 78
  percent repository floor and actor/authorization 90 percent subsystem gates.

## Internal Review

Candidate `881ac7fc` and docs repair `d859af3d`, against trusted main
`8d5eb15b`, pass senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, and test-delta review after all
valid findings were repaired. Integrated candidate `98376fd1`, against trusted
main `44f2467c`, passes the same nine tracks after repairing ART admission's
stale exact-type check for the new closed human/service context union.

## External Review

CodeRabbit raised one wording issue and one post-lock human-kind drift issue.
Both are repaired: the specification wording is clear, and human administrative
revalidation now denies actor-kind drift before context reconstruction or grant
lookup. The focused repair suite passes 11 tests; fresh external and hosted CI
checks remain required on the repair head.

## Remaining Risk And Follow-up

Hosted Backend CI and external review remain. The same-initiative
`WS-AUTH-001-ART-CUSTODY` successor is only a recorded next gate; it must not
start until this PR and signed memory are complete, its own contract
prerequisites pass, and the user explicitly starts it.

## Human Review Focus

Review service-before-human dispatch, exact matrix-before-availability order,
active-only observation staging, lock-time drift denial, bounded evidence, and
the absence of feature activation or migration changes.

## Human Merge Ownership

The agent may publish and repair this branch but may not merge it. Only the
human may approve this PR for merge. Trusted-main automation owns post-merge
schema-v2 memory generation when the workflow succeeds.
