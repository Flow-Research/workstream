# WS-QUAL-001-05M PR Trust Bundle

## Chunk

`WS-QUAL-001-05M` — Blocking Changed-Scope Behavior Mutation Gate (L1).

## Goal and human-approved intent

Turn the accepted `04M` observational calibration into a bounded required gate:
eligible changed behavior must have exact ownership, owning tests, and no
meaningful surviving selected mutant. The user explicitly accepted calibration
and started this chunk.

## What changed and why

- Replaced mutable static mutation configuration with exact selection-derived
  disposable configuration.
- Added exact claim discovery, merge-base callable mapping, AST existence, and
  fail-closed status reconciliation.
- Made the stable `pilot` check always emit and block meaningful survivors.
- Kept evaluator, helper, mutation toolchain, and backend dependency authority
  at protected base after the explicit one-time bootstrap.
- Added contributor claim/schema/example guidance, local discovery, evidence
  interpretation, focused tests, and 90-percent subsystem coverage proof.

Coverage alone does not prove assertions detect wrong behavior. This gate adds
that proof only for the changed, explicitly owned callable scope; it does not
introduce a global mutation score.

## Design chosen and alternatives rejected

The protected evaluator derives every eligible changed target and callable.
One exact claim supplies owning tests, observable outcomes, and real boundaries
but cannot narrow the derived scope. Mutmut runs in an archived disposable tree
with a hash-locked runner and runtime/test dependencies resolved from the
protected backend lock. Exact policy-owned strong/weak controls calibrate the
engine. All meaningful selected survivors and unsafe/incomplete statuses block.

Rejected: full-repository mutation, score thresholds, PR-head evaluator or
dependencies, free-form survivor exemptions, workflow path filters, and
running candidate tests with repository/CI credentials.

## Scope control and product behavior

No application behavior, migration, Workstream product lifecycle,
authorization, payment, reputation, Backend lane, or coverage threshold
changed. Review decisions remain `accept`, `needs_revision`, and `reject`;
mutation findings are engineering evidence only. Existing global 78-percent
and protected 90-percent floors remain blocking.

## Acceptance proof and test delta

- Exact discovery: applicable `05M`, one claim, exact changed-callable ownership.
- Mutation policy: 58 passed; 91.97-percent focused coverage.
- Policy/CI/coverage contract suites: 263 passed.
- Repository workflow invariants: 11 passed.
- Locked disposable environment replay: backend imports and policy suite passed.
- Ruff, Markdown links, stale wording, and diff checks passed.
- No test was removed, skipped, xfailed, deselected, or weakened.
- Enforced selected-survivor failure and the complete generated mutmut table
  now have behavioral regression tests.

## CI integrity and reviewer results

The workflow retains stable job id `pilot`, read-only permissions, pinned
Actions, no path filters, preflight before installation, protected-base
authority, 15-minute job/720-second command/700-second engine limits, and
exact-head evidence. Architecture, senior engineering, QA, security,
product/ops, CI integrity, docs, reuse/dedup, and test-delta tracks pass after
valid findings were fixed. Detailed results are in the internal review evidence.

## External review

CodeRabbit's first review produced four substantive findings. They were fixed:
plain class headers now fail closed, capability detection uses an explicit
marker, deleted eligible targets fail closed, and generated-TOML reparse
failures are typed. GitHub Actions and CodeRabbit must rerun on the exact final
head. The bootstrap PR is nonblocking for mutation outcomes because merged
`04M` lacks the new evaluator and locked `uv` runner; the first protected-main
run establishes `05M` authority for later PRs.

## Remaining risks and follow-up

Hosted dependency/runtime timing must remain within the accepted limits. The
stable internal job id `pilot` is retained to avoid breaking required-check
configuration. Shared diff-line parsing may be deduplicated later; neither is a
merge blocker. Do not start another QUAL chunk from this PR.

## Human review focus and merge ownership

- Confirm protected-base evaluator and dependency custody after bootstrap.
- Confirm exact callable ownership cannot omit changed behavior.
- Inspect hosted `selection.json`, `executed-selection.json`, and
  `evidence.json`, especially calibration and `verdict.blockers`.
- Confirm Backend, Agent Gates, CodeRabbit, and this required gate pass on the
  exact final head.

Only the user may approve and merge this specific PR.
