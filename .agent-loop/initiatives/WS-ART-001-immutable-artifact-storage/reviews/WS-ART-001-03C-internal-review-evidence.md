# WS-ART-001-03C Internal Review Evidence

## Scope

Guide-source v2 clean cut, verified ART-only guide material, and automatic
same-generation setup continuation.

## Final reviewer results

- Architecture: pass; project continuation retains a closed ART capability.
- Security/auth: pass; exact authorization facts and provider reads remain in
  the same transaction-held lock window and candidate changes fail closed.
- Product/ops: pass; continuation evidence is operator-visible.
- Senior engineering: pass with low risk after durable stale-dispatch claiming.
- CI integrity: pass; the 78% global floor remains and focused 90% gates were added.
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
- Lightweight agent gates: 7 passed.
- Markdown link check: passed for changed Markdown files.
- Non-database focused project tests: 4 passed.
- Database-backed focused tests were not run locally because
  `WORKSTREAM_TEST_DATABASE_URL` is not configured; hosted Backend/Agent Gates
  remain required.
