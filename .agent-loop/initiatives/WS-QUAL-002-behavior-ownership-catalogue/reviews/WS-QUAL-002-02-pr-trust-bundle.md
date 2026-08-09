# PR Trust Bundle: WS-QUAL-002-02

## Chunk

`WS-QUAL-002-02` — Local Coverage-Context Evidence.

## Intent

Provide bounded local evidence showing which exact pytest nodes execute which
callable lines, without treating inference as reviewed ownership and without
adding hosted CI cost.

## What Changed

- Added manual `context-evidence` generation and validation commands.
- Reused the semantic-lane pytest plugin for exact collection, completion,
  skip, and deselection custody.
- Added coverage.py per-test contexts mapped to exact callable spans.
- Added digest, Git-head, clean-tree, runtime, size, path, overwrite, and
  non-authoritative-schema controls.
- Sanitized both collection and execution environments so branch-controlled
  pytest imports cannot inherit unrelated local secrets.
- Documented operation and recorded the chunk status and evidence limits.

## Scope And Non-Goals

No workflow, required check, catalogue record, application module, migration,
coverage threshold, test selection, mutation activation, product lifecycle,
authorization, payment, reputation, or `ContributionRecord` behavior changed.

## Verification

- 82 focused behavior-ownership tests pass.
- `scripts.behavior_ownership` remains above the required 90 percent focused
  coverage floor.
- 33 semantic-lane contract tests pass.
- Ruff, Markdown links, stale-wording checks, and diff integrity pass.
- A real clean-tree probe remains below the 120-second and 10-MiB adoption
  limits and passes standalone validation.

## Internal Review

- Architecture: PASS WITH LOW RISKS.
- QA: PASS after complete-callable evidence enforcement.
- Security: PASS after collection privacy and evidence-integrity repairs.
- CI integrity: PASS WITH LOW RISKS.
- Reuse/deduplication: PASS WITH LOW RISKS.
- Test delta: PASS.

Detailed review evidence is in
`WS-QUAL-002-02-internal-review-evidence.md` in this directory.

## Remaining Risk

This evidence is deliberately local and candidate-only. It does not establish
reviewed ownership and no authoritative catalogue consumer accepts it. Private
lane-helper coupling should be revisited only if a second consumer appears.

## Human Review Focus

Confirm the non-authoritative boundary, secret-free pytest subprocesses,
complete exact-head/callable custody, and absence of hosted-CI changes.

## Human Merge Ownership

- [x] Intent, scope, and non-goals are explicit.
- [x] Deterministic local evidence passes.
- [x] Required internal reviewer tracks pass.
- [ ] External review findings are addressed.
- [ ] Exact-head GitHub checks pass.
- [ ] The user explicitly approves this PR for merge.
