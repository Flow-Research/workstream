# Chunk Contract: WS-ART-001-05B — Submission API And Dispatch Cutover

Parent initiative: `WS-ART-001` | Risk: L1 | Status: Superseded/non-executable;
replaced by WS-ARCH-001-02I after 02A-02H establish owner APIs, hidden atomic
composition, and exact AUTH activation

## Goal

Make verified admission consumption the only contributor Submission path while
TASKS owns the Submission API/lifecycle, ART owns admission/binding, and the
composition root wires the atomic command. Dispatch post-submit work using
immutable identifiers and remove the complete legacy standalone/internal
precheck path once and for all.

## Allowed Files

None. Use WS-ARCH-001-02A through 02I; this file authorizes no implementation.

## Not Allowed Changes

ZIP inspection, admission production, checker execution, review/contribution,
generic artifact download, AUTH catalogue/availability, or compatibility paths.
No ART ownership of TASK routes/services/Submission mutation and no private
cross-module imports.

## Acceptance Criteria

- the public request accepts an admission identity, not URI/hash/manifest facts;
- caller-owned package identity fields are unreachable and removed safely;
- `/api/v1/tasks/{task_id}/submission-precheck`, its OpenAPI schemas, and its
  public service entry point are absent and return canonical not-found;
- the legacy internal `TaskService.create_submission` precheck guard is removed
  in the same cutover because Submission creation can consume only an exact
  verified ready admission;
- no alias, redirect, fallback, private compatibility service, caller-owned
  manifest input, or second checker registry survives;
- pending, failed, expired, stale, consumed, cross-task, cross-project, and
  otherwise non-ready admissions cannot create a Submission or dispatch work;
- mixed admission-plus-legacy package requests fail closed rather than choosing
  one authority source;
- concurrent consumption of one ready admission creates exactly one Submission,
  one binding, one admission transition, and one downstream dispatch;
- exact idempotent replay returns the original business effect while conflicting
  replay fails with the stable domain conflict;
- response exposes immutable Submission/binding identities without provider URLs;
- Celery payloads contain durable identifiers/version facts only;
- old and new paths cannot coexist or create duplicate business effects.

## Verification Commands

- focused API/schema tests prove admission-only creation and reject legacy
  `package_uri`, `package_hash`, `artifact_hash_manifest`, and mixed requests;
- PostgreSQL state-matrix and concurrency tests prove non-ready/cross-resource
  rejection, exact replay, one consumption, one Submission, and one dispatch;
- route/OpenAPI/import-reachability tests prove the removed
  `/api/v1/tasks/{task_id}/submission-precheck` route, schemas, public service
  method, aliases, redirects, fallbacks, compatibility path, and second registry
  are absent;
- migration, stale-field, focused 90 percent subsystem coverage, repository 78
  percent coverage, and hosted Backend/Agent Gates pass.

## Required Reviewers

Architecture, security/auth, product/ops, QA, senior engineering, CI integrity,
reuse/dedup, test delta, and docs.

## Human Review Focus And Stop Conditions

Review the complete clean cut, proof that unchecked Submission creation is
impossible, and API compatibility impact. Do not change authoritative catalogue
definitions or checker semantics in this cutover. This file must not start
implementation.
