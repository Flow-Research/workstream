# PR Trust Bundle: WS-SEC-001-01

## Chunk

`WS-SEC-001-01` - Patch dependency alerts

## Goal And Context

Patch the six open Dependabot findings without changing Workstream product
behavior. The bounded contract is
[`WS-SEC-001-01-patch-dependency-alerts.md`](../chunks/WS-SEC-001-01-patch-dependency-alerts.md).

## What Changed And Why

- Upgraded `cryptography` and the approved `pypdf` artifact to patched lines.
- Upgraded backend pytest/pytest-asyncio and retained mutation pytest/uv
  tooling to mutually compatible patched lines.
- Preserved exact artifact and mutation-manifest hashes.
- Synchronized the parser approval manifest, normative specification, and
  durable initiative state.

## Scope Control

Only dependency declarations, generated locks, dependency approval records,
the matching normative version declarations, and WS-SEC-001 loop evidence
changed. No product behavior, API, persistence, migration, authorization,
workflow, test, coverage, or CI gate changed.

## Acceptance Proof

- Backend lock resolves `cryptography` 50.0.0, `pypdf` 6.15.0, pytest 9.1.1,
  and pytest-asyncio 1.4.0.
- Mutation requirements hash-install pytest 9.0.3 and uv 0.11.15.
- The direct PDF pin, approval manifest, lock, and normative specification
  agree on the approved version and artifact identity.
- Focused dependency/parser/mutation tests and real-PostgreSQL authorization
  tests passed before publication; the exact-head GitHub workflow supplies the
  complete semantic-lane and coverage proof.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| Security | PASS WITH LOW RISKS | None | Stale normative pypdf references fixed |
| CI integrity | PASS WITH LOW RISKS | None | No CI files or gates changed |
| Test delta | PASS WITH LOW RISKS | None | No tests or thresholds changed |
| Senior engineering | PASS WITH LOW RISKS | None | Resolver-marker churn noted as non-blocking |
| CodeRabbit | Addressed | None open after fixes | Three threads triaged; valid findings fixed |

## CI Integrity And Remaining Risks

No workflow, test, lint, coverage, or package-script gate was weakened. Backend
dev ranges may resolve later compatible minor releases in future fresh pip
installs; the exact PR head must pass GitHub Backend before merge.

## Human Review And Merge Ownership

Review the dependency versions, exact hashes, synchronized pypdf records, and
green exact-head checks. Only the user may approve and merge this PR.
