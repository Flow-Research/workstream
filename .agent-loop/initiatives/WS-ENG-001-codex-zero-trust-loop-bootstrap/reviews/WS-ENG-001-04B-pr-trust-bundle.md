# WS-ENG-001-04B PR Trust Bundle

## Chunk and goal

`WS-ENG-001-04B` records protected human start/cancel authority in the signed
loop ledger and regenerates canonical projections without a bookkeeping PR or
automatic successor activation.

## Human-approved intent

The user approved the reviewed L1 plan and this single implementation chunk.
Merge remains human-owned.

## Changes and design

- Adds typed cutover, start, and cancel events with immutable run, dispatcher,
  approver, main, prior-tip, reason, initiative, and chunk evidence.
- Separates coherent global merge state from per-initiative authority lifecycle
  and validates every transition against its preceding signed basis.
- Adds a protected main-only dispatch workflow and one shared repository-owned
  exact-tree fast-forward publisher used by both loop workflows.
- Seals exact pre-cutover AUTH, ART, and MCP exemptions and consumes each once.
- Adds independent validator, workflow-structure, tamper, collision, stale-tip,
  two-active, active-merge, cancel/retry, and push-failure tests.
- Adds required hash-pinned CI coverage tooling and operator policy/runbook.

## Scope and product behavior

No backend/frontend runtime, API, database schema, Workstream product lifecycle,
payment, reputation, PR approval, or automated merge behavior changes.

## Proof, test delta, and CI integrity

- 151 relevant tests pass; the repair-focused suite passes 134 tests.
- Updater/checker independent branch coverage: 90.16/91.07 percent.
- Ruff, compilation, merge intent, links, stale wording, dependency hashes, and
  diff integrity pass.
- Tests are additive; no assertion, skip, required check, or threshold weakened.

## Reviewer results

All nine required tracks pass final exact head `da9b2291` after valid findings
were repaired: senior, QA, security, product/ops, architecture, CI, docs,
reuse/dedup, and test delta.

## Remaining risk and external review

Hosted checks and human review passed on pre-repair PR head `e8ade1f8`.
CodeRabbit identified replay wording and mutable cutover-inventory risks; both
are repaired and independently reviewed. Fresh hosted checks, incremental
CodeRabbit review, and any branch-policy-required renewed approval remain after
push. The protected live environment requires review, disables self-review/admin
bypass, and allows protected branches only. The workflow reuses the existing
repository-managed loop-memory signing identity; no second key was created or
transferred.

## Human review focus

Review authority-to-basis linkage, global versus initiative reduction, exact
environment approval provenance, prior-tip/main freshness, typed cutover and
one-use exemptions, shared fixed-branch publication, and the no-rotation safety
boundary.

## Follow-up and human merge ownership

Key rotation continuity requires a separate reviewed design. No successor chunk
is declared. Only the user may approve and merge the eventual PR.
