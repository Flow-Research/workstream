# WS-ART-001-03B4 PR Trust Bundle

## Chunk

`WS-ART-001-03B4` — Guide Sufficiency Continuation (L1).

## Goal and human-approved intent

Feed only complete, verified, same-generation canonical guide material into
the existing asynchronous sufficiency workflow and persist the exact ART
lineage consumed. Keep the behavior hidden and binding/read AUTH actions
planned and unavailable until AUTH-04B.

## What changed and why

- Added an artifact-owned material port that validates complete binding,
  content, classification, extraction, setup-run, and generation lineage.
- Added a hidden verified sufficiency continuation and identifier-only Celery
  generation payload.
- Canonically serializes and caps the complete agent prompt at 12 MiB, labels
  every source item as untrusted, and sends the exact hashed bytes.
- Persists setup/material identity on reports and one normalized provenance row
  per consumed extraction usage.
- Maps artifact incidents and bounded extraction failures to setup outcomes
  without misclassifying them as guide insufficiency.

## Design chosen and alternatives rejected

ART owns persistence joins behind `GuideSufficiencyMaterialPort`; project code
consumes typed immutable DTOs. The worker reloads durable identifiers and exact
generation facts. Rejected alternatives include ART model imports in project
services, raw binaries or caller excerpts in prompts, prepared AUTH handles in
Celery, generic download authority, incomplete source sets, and live legacy
cutover before AUTH-04B.

## Scope control and product behavior

This is hidden guide setup behavior only. It does not activate AUTH actions,
replace the live legacy path, remove legacy identity, parse provider objects,
or change submission, review, contribution, compensation, or reputation flows.
ART-03C owns the later clean cut.

## Acceptance criteria proof

- Every snapshot item requires one current verified binding and successful,
  policy-current extraction usage.
- Exact project/guide/snapshot/run/generation and ART provenance are checked
  before invocation and again before atomic report commit.
- Canonical sorted-key UTF-8 prompt bytes are identical at hashing and runtime;
  12 MiB passes and one byte over fails before invocation.
- Replay returns the one existing report without a second agent call or
  provenance row; stale and crossed lineage fails closed.
- Reports bind to exact material hash/size and normalized source usages.
- Celery carries identifiers and setup generation only.

## Tests and checks run

- Ruff — pass.
- Focused architecture/router/prompt/limit suite — 23 passed.
- Isolated PostgreSQL exact-provenance/replay test — pass after full migration.
- Migration round trip, D46 worker matrix, stale generation, artifact incident,
  canonical prompt, and queue/router tests passed in focused runs.
- Stale artifact contract scan, Markdown links, and `git diff --check` — pass.
- Full repository and coverage gates are assigned to hosted Backend/Agent Gates
  to avoid the user's slow local machine.

## Test delta and CI integrity

Tests add exact provenance, replay, generation, prompt-boundary, incident, and
migration proofs. No tests, assertions, workflows, lanes, or coverage floors
were removed or weakened. Repository 78 percent and changed-subsystem 90
percent requirements remain intact.

## Reviewer results

Architecture, security, product/ops, QA, senior engineering, CI integrity, and
test-delta reviews pass with no blockers. Docs and reuse findings were repaired:
the data model/chunk map now match the schema, and canonical JSON rejects
non-finite values. Final rereviews are recorded before merge readiness.

## External review

Hosted Backend/Agent Gates and CodeRabbit have not yet run on the final PR head.
Their valid findings will be addressed before merge readiness.

## Remaining risks and follow-up work

The hidden continuation intentionally coexists with the legacy live path.
AUTH-04B must activate only fixed-service binding/read authority after this
chunk merges; ART-03C then performs the separate legacy cutover.

## Human review focus and merge ownership

Review the all-items-required query, transaction/generation fences, exact
prompt identity and ceiling, normalized provenance constraints, replay behavior,
and absence of AUTH activation or legacy cutover. A human owns merge approval;
the agent will not merge this PR.
