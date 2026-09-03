# PR Trust Bundle: WS-ART-001-02A1

## Chunk

`WS-ART-001-02A1` - External Service Adapter Foundation

Merge intent: `.agent-loop/merge-intents/WS-ART-001-02A1.json`

## Goal

Install ADR 0014's small typed construction convention for external service
adapters without migrating ArtifactStore or any other capability.

## Human-Approved Intent

The user explicitly started 02A1 on 2026-07-15 after approving the AWS-first
object-storage plan. This chunk standardizes only adapter identity, shared root
errors, and explicit typed construction. Later capability migration remains in
separate chunks, and only the user may approve merge.

## What Changed

- Added immutable canonical adapter identity and stable shared root errors.
- Added an instance-local generic factory with explicit provider registration.
- Added fail-closed duplicate, unknown, mismatch, malformed identity, and
  provider-construction handling.
- Added focused adversarial tests and an exact scoped CI coverage gate.
- Updated only directly related chunk memory and the schema-v2 merge intent.

## Why It Changed

Without one small construction convention, each external capability can grow
an ad hoc factory, leak provider selection into product services, or retain
provider exceptions and credentials at the shared boundary.

## Design Chosen

The common protocol exposes only immutable capability/provider identity.
Capability-specific ports will extend it later. Registration remains explicit
and instance-local at a composition root. Construction accepts only exact
canonical identity and remaps provider failures into fresh bounded root errors
without retaining original exception chains.

## Alternatives Rejected

- Global registration, import scanning, or runtime discovery: implicit and
  difficult to audit.
- One universal `execute` adapter: removes capability type safety.
- Capability migration in this chunk: violates ownership and review scope.
- Compatibility aliases or fallback constructors: forbidden in the current
  pre-production clean-cut architecture.

## Scope Control

The production foundation is 158 lines and the focused test module is 339
lines. No provider SDK, concrete adapter, route, Celery task, schema migration,
product service, or existing capability factory changed.

## Product Behavior

None. Operator, contributor, reviewer, checker, revision, payment, reputation,
and artifact runtime behavior remain unchanged.

## Acceptance Criteria Proof

- Identity is immutable, bounded, canonical, and exact-type checked.
- Root errors expose stable code/category/retryability plus sanitized identity.
- Constructor exceptions, malicious equality, identity subclasses, and Python
  exception chains fail closed under focused regression tests.
- Registration is typed, explicit, instance-local, and rejects duplicate or
  unknown providers.
- CI preserves the artifact 90 percent gate and global 78 percent floor while
  adding the exact external-service foundation 90 percent gate.

## Tests And Test Delta

- 15 focused tests passed at 100 percent foundation coverage.
- Ruff, 94.5 percent docstring coverage, 71 agent gates, stale scans, links,
  merge-intent validation, and diff hygiene passed.
- No test was removed, skipped, weakened, or excluded.
- The local full suite was stopped after passing beyond 79 percent because of
  workstation contention; GitHub Backend CI is the authoritative exact-head
  global suite and 78 percent coverage proof.

## CI Integrity

- [x] Existing full-suite and scoped coverage commands remain present.
- [x] Agent gates assert exact command, source set, threshold, order, and
  cumulative retention.
- [x] No conditional, continue-on-error, shell, environment, or exclusion
  bypass was added to the scoped gates.
- [ ] GitHub Backend CI must pass the published exact head.

## Reviewer Results

| Reviewer group | Result | Blocking findings |
|---|---:|---|
| Senior engineering, architecture, QA, security | PASS | None |
| Product/ops, reuse/dedup, docs | PASS | None |
| CI integrity, test delta | PASS WITH LOW RISKS | None |

All nine final reviewer sessions are closed. Earlier valid findings around
branch freshness, canonical identity, malicious equality, subclass state, and
exception-chain retention were repaired and independently re-reviewed.

## External Review

PR #127 is open. Agent Gates and Backend passed published head `7c8da61`;
Backend completed the repository-wide suite and 78 percent floor in 16m18s.
CodeRabbit's one valid consistency nit was fixed in `05d667a`: both
constructor-error branches now suppress provider exception context explicitly.
Eight technical and operational tracks passed the exact delta; the docs track
passed the completed evidence provenance separately. GitHub checks and
CodeRabbit must rerun on the updated head before the human merge checkpoint.
External checks supplement the internal review and do not replace it.

## Remaining Risks

- The convention has no capability consumer until later approved chunks.
- GitHub Backend CI remains required because the local global run was
  intentionally interrupted under host contention.
- Later capability factories must preserve explicit composition-root
  registration and remove their old paths atomically when migrated.

## Follow-Up Work

`WS-ART-001-02A2` may add committed-source preparation only after this PR
merges and the user explicitly starts it. It does not start automatically.

## Human Review Focus

Inspect whether the common abstraction is truly smaller than every capability,
whether error sanitization is complete without obscuring stable categories,
and whether the diff avoids migrating any existing capability.

## Human Merge Ownership

Only the user may approve and merge this PR. Publication is not merge approval.
