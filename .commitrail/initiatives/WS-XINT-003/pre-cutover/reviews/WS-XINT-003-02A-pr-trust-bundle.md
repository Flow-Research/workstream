# PR Trust Bundle: WS-XINT-003-02A

## Chunk

`WS-XINT-003-02A` — Immutable Policy Identity And Lineage.

## Goal and result

ReviewPolicy and RevisionPolicy are now immutable, append-only identities.
ProjectGuide selects exact versions, Task locks those exact facts, and
Submission and CheckerRun copy and database-chain them without treating guide
version as policy version. Both policy mutation actions remain planned and
unavailable.

## Design

- Complete policies carry typed semantics, generation, canonical digest,
  readiness status, and predecessor lineage.
- Historical policies migrate deterministically as readable
  `legacy_incomplete` records; missing lease or preference meaning is never
  invented and readiness denies their future activation.
- Draft guide selections are all-or-none; activation requires complete
  selections and freezes them.
- Exact project, guide, policy ID, generation, and digest tuples are enforced
  through downstream foreign keys.
- PostgreSQL rejects policy update, delete, truncate, cross-resource lineage,
  active-selection mutation, and populated downgrade.
- No compatibility aliases, route, PREP consumer, grant, or ActionId
  activation was added.

## Proof

- Focused migration and lineage tests: 10 passed, 74 deselected.
- Policy-lineage branch coverage: 9 passed, 100 percent.
- Direct isolated cross-Task CheckerRun mismatch: 1 passed.
- Hosted-lane regression corrections for activation, immutable work-context,
  and checker admission: 5 focused cases passed in isolated databases.
- Ruff, Python compilation, stale contract/wording scans, Markdown links, and
  `git diff --check`: passed.
- Hosted GitHub Actions retains the full-suite 78-percent gate and the existing
  targeted 90-percent subsystem gate; no threshold or failure behavior changed.
- The new policy-lineage test module has explicit `shared_foundations` semantic-
  lane custody; the initial fail-closed missing-inventory result was corrected.

## Review

Architecture, security/auth, product/operations, QA/test, docs, test-delta, and
CI integrity passed. Senior engineering and reuse/dedup passed with only low,
non-blocking review observations. Every blocking first-round finding was fixed
and re-reviewed.

## External review

GitHub Actions and CodeRabbit must review the exact final PR head. Every valid
comment or failing check must be resolved before human merge.

CodeRabbit's reviews produced five valid points: policy identity metadata,
scoped row locking, fixture activation ordering, shared test semantics, and
post-merge migration-test cleanup. All are fixed and recorded in
`WS-XINT-003-02A-external-review-response.md`. Exact-head Agent Gates, Backend,
and CodeRabbit remain required external checks.

## Remaining risk and follow-up

This chunk establishes identity and lineage but deliberately activates no
policy writer. WS-XINT-003-02B installs the sole authorized mutation path only
after 02A merges and the user explicitly starts that next chunk.

## Human review focus

Confirm deterministic legacy handling, immutable exact identity selection,
complete downstream FK chaining, absence of invented semantics, and zero
runtime policy-action activation.

## Human merge ownership

Only the human may merge this PR.
