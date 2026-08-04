# Workstream PR Trust Bundle

## Chunk

`WS-AUTH-001-12E` - Activate guide-sufficiency mutations

## Goal

Activate exactly manual sufficiency-report creation, agent-run requests, and
warning acknowledgement. Keep public mutation Project Manager-only and grant
the fixed `workstream.project.setup` service only the internal run command.

## Intent And Planning Context

- Intent: close the guide-sufficiency durable authorization boundary without
  introducing another authorization protocol.
- Chunk contract: `chunks/WS-AUTH-001-12E-guide-sufficiency-mutations.md`.

## What Changed

- Added the three active catalogue actions and exact human/fixed-service guards.
- Added prepared authorization and final locked revalidation to all durable
  sufficiency mutations.
- Added migration 0054 for immutable replay custody and complete authorization
  provenance.
- Connected the setup worker through fresh deterministic service authority.
- Made the Project Manager recovery route asynchronous: human PREP evidence,
  stable replay response, and deterministic `dispatch_pending` custody commit
  atomically before broker publication.
- Reconciled ART-03C so automatic readiness and authorized human recovery
  requests converge on one deterministic asynchronous setup task. HTTP returns
  setup custody only; the fixed service alone creates authoritative reports.
- Added the exact-generation terminal fence so completed sufficiency or policy
  output rejects redundant requests before queue, material, or agent work.
- Kept manual diagnostic reports separate from the single authoritative
  verified-report slot.
- Added runtime, migration, API, replay, transaction, and coverage proof.

## Why It Changed

The former guide-sufficiency mutations could not safely become live until the
actor, identity link, grant/service identity, guide lineage, material, request,
transaction, and idempotency facts were bound and revalidated atomically.

## Design Chosen

- Reuse the opaque, process-local, single-use, transaction-bound
  `PreparedAuthorizationHandle`.
- Run external agent work without an open prepared handle, then reload and lock
  canonical facts before the protected write.
- Commit replay completion, product mutation, and allowed evidence atomically.
- Carry identifiers only through Celery and acquire fresh service authority in
  the worker.

## Alternatives Rejected

- Raw `AuthorizationContext` as durable authority: not transaction-bound.
- Serializing prepared handles into Celery: violates process/session custody.
- ART- or project-local authorization evaluators: duplicate AUTH policy paths.
- Preserving legacy mutation behavior: no backward compatibility is required.

## Scope Control

### Allowed Files Changed

- AUTH catalogue, runtime, PREP, kernel, migration, and tests.
- Project sufficiency mutation/queue/worker integration and tests.
- Exact operations, specification, roadmap, and initiative records.
- Narrow CI coverage assertions for the new subsystem files.

### Files Outside Stated Scope

- ART fixed-service authorization composition was narrowed to the shared AUTH
  principal resolver; its focused adapter tests prove behavior is unchanged.

## Product Behavior

- [x] Product behavior changed: Project Managers can create reports, request an
  agent run, and acknowledge warnings under exact project authority; only the
  fixed project-setup service can execute the internal run command.

## Evidence

### Commands Run

```bash
cd backend && .venv/bin/ruff check .
cd backend && .venv/bin/pytest -q <focused AUTH/ART/API/audit selectors>
cd backend && .venv/bin/alembic upgrade head
git diff --check
```

### Result Summary

```text
Ruff: passed
Project sufficiency selector before hosted review: 31 passed
Async manual/automatic custody, terminal fence, wrong task identity, and stale
dispatch recovery: 5 passed
Stable pre-publish custody exact replay regression: 1 passed after fixture repair
Authorization selector: 144 passed
Migration 0054 selector: passed
API contract E2E: passed
Semantic collection: 2,928 tests across five hosted lanes
External-review shared-foundation selectors: passed
Canonical schema fingerprint and reset custody: passed
```

The repository-wide suite and authoritative coverage gates run in GitHub
Actions; the user's machine is not used for the roughly four-hour local suite.

## Acceptance Criteria Proof

- [x] Exactly three sufficiency actions become active.
- [x] Human and fixed-service authority remain disjoint.
- [x] Final decisions bind exact actor/link, authority, lineage, material,
  operation, request, idempotency, session, and transaction facts.
- [x] Replay, copied/wrong handles, stale context, cross-resource use, and
  mid-flight terminal transitions fail closed.
- [x] Celery stores deterministic task custody before enqueue and never carries
  handles, bytes, credentials, or authorization contexts.
- [x] Product write, replay completion, and allowed evidence commit atomically.

## Test Delta

### Tests Added

- Prepared handle integrity, denial, replay, and service-custody tests.
- Human routes, worker execution, stale lineage/material, transaction rollback,
  mid-flight terminal race, and deterministic broker identity tests.
- Migration upgrade/downgrade, append-only replay, provenance-only rollback
  refusal, schema parity, and API contract tests.
- Focused service-boundary coverage for successful human create and warning
  acknowledgement plus replay, mismatch, duplicate, stale-lineage, pending,
  and wrong-state denials.

### Tests Modified

- Active-action, OpenAPI, audit, operations-count, ART principal-composition,
  and project setup fixtures were updated for the exact activated surface.

### Tests Removed Or Skipped

- None.

## Internal Reviewer Results

Reviewed code state: current pre-commit WS-AUTH-001-12E correction diff

Reviewed at: 2026-08-04

Reviewer run IDs: `12e_arch_final`, `12e_impl_qa`, `12e_impl_senior`,
`12e_product_final`, `12e_security_final`, `12e_test_delta`, plus the final
`12e_async_*` architecture, security, product, QA, and CI-integrity correction
reviews and the recorded docs/reuse tracks.

| Reviewer | Result | Blocking Findings | Notes |
|---|---:|---|---|
| Senior engineering | PASS | None | Final implementation review |
| QA/test | PASS | None | Async custody and exact replay proof reviewed |
| Security/auth | PASS | None | Atomic replay/dispatch lease and immutable lineage verified |
| Product/ops | PASS | None | Automatic trigger, manual recovery, and terminal token fence verified |
| Architecture | PASS | None | Human request and fixed-service execution remain separate |
| CI integrity | PASS | None | No gate weakening |
| Docs | PASS | None | Canonical surfaces aligned |
| Reuse/dedup | PASS | None | Shared PREP/service resolver reused |
| Test delta | PASS WITH LOW RISKS | None | No skipped or weakened tests |
| CI integrity repair | PASS WITH LOW RISKS | None | Focused coverage append preserves the 78/90 percent gates and disables ambient plugin autoload |
| QA coverage repair | PASS WITH LOW RISKS | None | Real service boundary and fail-closed branches exercised; hosted exact-head proof remains pending |
| Test delta coverage repair | PASS WITH LOW RISKS | None | Exact selector, no skipped tests, and no weakened assertions or thresholds |

## External Review

| Source | Status | Notes |
|---|---:|---|
| CodeRabbit | Re-review pending | Correction will be pushed for exact-head review |
| GitHub checks | Rerun pending | Hosted full suite and coverage will run on the correction head |

## CI And Gate Integrity

- [x] No workflow weakening.
- [x] No lint/test/docstring gate weakening.
- [x] No coverage threshold weakening.
- [x] No package script weakening.
- [x] No unpinned new GitHub Action.
- [x] Checkout credential persistence remains disabled.

## Remaining Risks

- The exact corrected head still requires all hosted lanes, aggregate and
  per-file coverage, Agent Gates, and fresh CodeRabbit review.
- Large legacy `ProjectService` sufficiency helpers remain a low-risk future
  retirement item; live routes and workers use the new orchestrator.

## Follow-Up Work

- Add PR `#263` to the capability ledger only after human merge.
- Retire or quarantine legacy commit-owning sufficiency helpers in a separately
  bounded cleanup chunk.

## Human Review Focus

- The three-action activation boundary and human/service separation.
- Migration 0054 replay/provenance constraints and downgrade refusal.
- External-agent transaction break and final locked revalidation.
- Deterministic task identity, terminal fencing, and atomic evidence.

## Human Merge Ownership

- [ ] I can explain what changed.
- [ ] I can explain why it changed.
- [ ] I know what could break.
- [ ] I accept the remaining risks.
- [ ] The user explicitly approved this specific PR for merge.
