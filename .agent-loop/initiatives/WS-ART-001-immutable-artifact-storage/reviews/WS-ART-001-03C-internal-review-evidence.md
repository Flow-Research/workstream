# WS-ART-001-03C Internal Review Evidence

## Scope

Guide-source v2 clean cut, verified ART-only guide material, and automatic
same-generation setup continuation.

## Final reviewer results

Earlier reviewers evaluated the implementation through `312e57c5` and the
focused shared-foundations reconciliation at `de2ae8b8`. After merging current
`main`, the focused migration-scope repair and updated trust evidence were
reviewed through `79d2fdfd`; the follow-up evidence-only correction records
those results. The review tracks used the changed ART/project/task tests, Ruff,
Python compilation, `git diff --check`, stale ART contracts, Markdown links,
and the lightweight agent gates identified below.

- Architecture: pass; project continuation retains a closed ART capability.
- Security/auth: pass; exact authorization facts and provider reads remain in
  the same transaction-held lock window and candidate changes fail closed.
- Product/ops: pass; continuation evidence is operator-visible.
- Senior engineering: pass with low risk after durable stale-dispatch claiming.
- CI integrity: internal pass; the 78% global floor remains and focused 90%
  gates were added. Hosted Backend run `30767889658` completed with failure and
  initiated the fixture-reconciliation sequence recorded in the external review
  response. Agent Gates pass; final hosted Backend proof remains pending after
  reconciliation with the distributed lanes merged from `main`.
- Docs: pass after guide-source v2 and diagnostic/verified report corrections.
- Reuse/dedup: pass with low risk after candidate, AUTH-fact, and read-path reuse.
- Test delta: pass with low risk after verified route, visibility, and dispatch
  retry replacement coverage.
- QA: pass after downstream project/task fixtures were reconciled with verified
  activation and existing setup-generation semantics.

## Resolved findings

- Removed the legacy caller-controlled guide byte identity and excerpt path.
- Separated diagnostic and verified sufficiency report slots.
- Replaced fabricated test provenance with the full constrained ART lineage.
- Reused the existing setup run instead of creating a duplicate generation.
- Centralized verified replica selection and binding authorization facts.
- Shared authorized provider-read preparation between classification and extraction.
- Added a committed `dispatch_pending` claim, deterministic task id, 60-second
  stale cutoff, and explicit claim timestamp advancement before retry publish.

## Local evidence

- Ruff and Python compilation: passed for changed backend code/tests.
- `git diff --check`: passed.
- Stale artifact contract scan: passed at `guide_source_cutover`.
- Lightweight agent gates: 10 passed after the distributed-lane CI merge.
- Distributed lane evidence/merge validators: 44 passed.
- Markdown link check: passed for changed Markdown files.
- Non-database focused project tests: 4 passed.
- The focused database-backed migration test was attempted through the
  canonical isolated runner after current-main reconciliation. The local runner
  reached migration `0049` and then failed in its database-operation wrapper
  before executing the test assertion; hosted Backend/Agent Gates remain
  required.
