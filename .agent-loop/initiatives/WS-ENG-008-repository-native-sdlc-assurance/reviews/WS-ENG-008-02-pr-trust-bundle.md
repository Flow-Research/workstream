# PR Trust Bundle: WS-ENG-008-02

## Chunk

`WS-ENG-008-02` — Scheduled Signed-State Drift Audit

Merge intent: `.agent-loop/merge-intents/WS-ENG-008-02.json`

## Goal

Detect later signed loop-memory custody or semantic drift independently, without
granting the audit repair, signing, dispatch, publication, or write authority.

## Human-approved intent

The signed contract is
`.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/chunks/WS-ENG-008-02-scheduled-signed-state-drift-audit.md`.

## What changed and why

- Added a daily and default-branch-only manually requestable drift workflow.
- Added a read-only audit entry point that reuses canonical signature, exact-tree,
  semantic, ledger, projection, ancestry, and active-contract validation.
- Added bounded diagnostics that distinguish advancement from corruption.
- Added fourteen focused failure fixtures and an Agent Gate workflow regression.
- Documented operation and added one successor intent for `WS-ENG-008-03`.

## Design chosen

The workflow captures immutable branch tips through the read-only GitHub API,
checks out exact main and state commits with pinned actions and non-persisted
credentials, runs canonical validators, then rechecks both tips. It never imports
or invokes reducer, signer, event, recovery, repair, or publication commands.

## Alternatives rejected

- `workflow_dispatch`: callers can select feature-ref workflow code.
- Unauthenticated Git clones/tip reads: fail for private/internal repositories.
- Scheduled repair: would create a second write and authority path.
- Reimplementation of signed-state validators: would fork canonical security logic.

## Scope control and product behavior

Eight authorized repository-assurance files changed. Backend, frontend, API,
database, authorization grants, payments, artifacts, product review decisions,
coverage thresholds, start/cancel authority, signing, and branch protection are
unchanged.

## Acceptance criteria proof

- Default-branch code, pinned actions, read-only permissions: workflow assertions pass.
- Signature, manifest, closed tree, semantics, ledger/projections, ancestry and
  active contracts: canonical validators plus live audit pass.
- Advancement/corruption distinction and bounded diagnostics: focused tests pass.
- Private repository compatibility: transient read API and pinned state checkout.
- Failure matrix: canonical mutation suites plus concrete audit-level binding and
  shallow-history fixtures pass.
- Successor control: one schema-v2 intent names `WS-ENG-008-03` with explicit start.

## Tests/checks run

Fourteen focused tests and 105 Agent Gate regressions passed. Machine scope,
merge intent, Ruff, compilation, Markdown links, stale wording/authorization/
artifact scans, live signed-state audit, and diff checks passed.

## Test delta and CI integrity

No test was removed, skipped, deselected, or weakened. No dependency, package
script, coverage floor, existing workflow, permission, or required check was
weakened. New actions are commit-pinned and both checkouts disable credential
persistence.

## Reviewer results

Reviewed code SHA: `9c04beb154ef316307ef3f3896d006ccd87f6e8a`

All nine required internal tracks passed: senior engineering, QA/test,
security/auth, product/ops, architecture, CI integrity, docs, reuse/dedup, and
test delta. Earlier High/Medium findings about feature-ref dispatch,
unauthenticated private-repository reads, preflight diagnostics, and concrete
contract fixtures were repaired and re-reviewed.

## External review

CodeRabbit and hosted GitHub checks remain pending until publication. They
supplement, rather than replace, the completed internal review.

## Remaining risks and follow-up work

Scheduled execution still depends on GitHub Actions and GitHub API availability.
Failures remain visible and non-mutating. `WS-ENG-008-03` is only the declared
same-initiative successor and requires a separate explicit signed start.

## Human review focus

- `repository_dispatch` default-branch trust boundary.
- Read-only token use and non-persisted credentials.
- Advancement versus corruption classification.
- Reuse of canonical validators and absence of mutable commands.

## Human merge ownership

The user owns approval and merge of the exact PR. Merge automation will stop
ENG-008 and will not start `WS-ENG-008-03` automatically.
