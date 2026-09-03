# Workstream PR Trust Bundle

## Chunk

`WS-AUTH-001-12F2` - Manual Submission Policy Drafts

## Goal

Activate only human Project Manager manual create/update for submission-policy
drafts, with exact sufficiency lineage, non-bypassable Workstream defaults,
append-only replacement, PREP evidence, and replay custody.

## What changed

- Activated create/update under child owner 12F2; derive/approve remain planned.
- Added a dedicated human/key/PREP API boundary with service concealment.
- Added exact system-or-project Project Manager admission before protected
  lookups and exact locked PREP before mutation.
- Replaced in-place updates with a deterministic successor row and atomic
  predecessor supersession.
- Added replay-first pending/committed handling that reauthorizes stored facts
  without depending on later guide/setup lineage.
- Removed obsolete self-committing manual create/update service entry points.
- Expanded focused, fault-injection, OpenAPI, and real API contract coverage.
- Added the required bounded behavior-mutation claim for the activating writer.

## Scope and behavior

- Project Managers may create or replace a manual draft only for a covered
  project and its current authoritative sufficiency lineage.
- Warning-bearing sufficiency requires exact 12E acknowledgement custody.
- Agent-derived rows remain immutable through the manual route.
- Derivation, approval, effective/pre-submit compilation, Celery, submission,
  review, revision, payment, and reputation behavior are unchanged.
- No migration is introduced by this chunk.

## Local evidence

```text
Ruff app/tests/scripts: passed
AUTH exact selector: 7 passed
Non-database boundary/schema/replay checks: passed
Project exact selector: 27 tests collected
Hosted replay/service selector: 2 tests collected
CI lane contract: 33 passed
Python compileall: passed
Stale authorization docs: passed
Markdown links: passed
Stale Workstream wording: passed
git diff --check: passed
Branch versus origin/main: 0 ahead / 0 behind before commit
```

Database-backed project tests and the roughly four-hour full suite are not run
on the user's slow local machine. GitHub Actions must run the PostgreSQL-backed
focused coverage, API E2E, repository-wide 78 percent floor, and changed-
subsystem 90 percent floor on the exact pushed head.

## Acceptance proof

- [x] Only manual create/update are active under 12F2.
- [x] System and exact-project PM grants admit; wrong-project, contributor,
      service, and role-claim-only callers deny.
- [x] Exact locked lineage and warning acknowledgement bind PREP and replay.
- [x] Update is append-only and CAS-bound; agent rows cannot use this path.
- [x] Exact committed replay returns stored response after later lineage drift.
- [x] Matching pending replay is retryable; changed/cross-action reuse denies.
- [x] Named create and update fault boundaries roll back product, replay, and
      allowed evidence together.
- [ ] Hosted PostgreSQL, full coverage, Agent Gates, API E2E, and CodeRabbit
      pass on the exact pushed head.

## Human review focus

- Concealment-only PM admission versus exact durable PREP authority.
- Stored-fact replay independence from later guide/setup changes.
- Append-only predecessor/successor identity and transaction atomicity.
- Default-floor preservation and manual/agent provenance isolation.

## Human merge ownership

- [ ] The user explicitly approved this specific PR for merge.
