# WS-ART-001-03C PR Trust Bundle

## Chunk

`WS-ART-001-03C` — Guide Source Cutover And Continuation (L1).

## Goal

Make verified ART bindings and canonical extraction usages the only
authoritative guide content, remove legacy caller byte identity, and continue
the same setup generation automatically after verification.

## Human-approved intent

Project Manager guide uploads may be PDF, DOCX, PPTX, CSV, XLSX, Markdown,
plain text, JSON, or supported images in v0.1. They are distinct from the
submitter's required outer ZIP. ART preserves original bytes, and setup agents
consume only verified, bounded extracted content. No audio/video support,
retention worker, manual resume action, or submission work belongs here.

## What changed

- Added guide-source snapshot v2 with server-owned item identity/order and
  sanitized non-authoritative labels; removed hash/CID/ref/excerpt authority.
- Added migration 0048 with a fail-closed populated-namespace refusal.
- Removed the legacy sufficiency-agent route and separated diagnostic and
  verified report uniqueness.
- Required complete exact extraction usage provenance for agent derivation and
  activation.
- Added hidden verified binding/materialization/extraction preparation and a
  project-owned Celery continuation using identifiers/generation facts only.
- Added durable continuation evidence and safe dispatch recovery semantics.
- Updated API E2E, docs, stale-contract checks, tests, and focused CI coverage.

## Why it changed

Caller metadata cannot prove which bytes Workstream checked. Policy derivation
and activation must instead follow exact verified content and extraction
lineage while preserving the existing project setup generation fence.

## Design chosen

`GuideSourceSnapshot` declares ordered items. ART owns content identity through
`ArtifactContent`, verified replicas, exact bindings, classifications,
extractions, and usages. The project continuation receives only a closed
`prepare_generation` capability. AUTH-04B prepared handles are fresh,
transaction-bound, never serialized, and consumed before provider reads or
binding mutations.

## Alternatives rejected

- Caller hashes, CIDs, excerpts, durable locators, or direct provider reads.
- A second authorization protocol or inherited Project Manager authority.
- Prepared handles, bytes, scratch paths, or credentials in Celery payloads.
- A manual resume/finalize route or a new setup-generation concept.
- Fabricated migration backfill for legacy rows.

## Scope control

No task/submission/checker/review cutover, generic download permission,
provider/factory change, AUTH catalogue activation, or Project Manager resume
command is included.

## Product behavior

Creating a snapshot records queued setup but produces no agent output until
every declared item has verified same-generation ART material. Verification
continues setup automatically. Missing, changed, stale, cross-context, or
incomplete content fails closed as artifact/setup failure, not guide
insufficiency.

## Acceptance criteria proof

- Schema/API/stale scans reject the legacy fields and route.
- Migration refuses populated legacy guide-source data.
- Verified report validation requires one ordered exact usage per source item.
- Binding and read paths consume fixed-service AUTH facts before protected work.
- Dispatch recovery has a committed claim, deterministic id, stale cutoff, and
  late-worker status backstep guard.
- Tests cover v2 shape, exact provenance, hidden failures, verified derivation
  replay, queued-before-material behavior, and fresh/stale dispatch behavior.

## Tests/checks run

- Ruff, compilation, and `git diff --check`: passed.
- Stale artifact contracts: passed.
- Lightweight agent gates: 7 passed.
- Markdown links: passed.
- Non-database focused project tests: 4 passed.
- Local database-backed suite: not run; the required database URL is absent and
  the user requested hosted sharded CI rather than a full local suite.

## Test delta

Legacy route/automatic-output tests were replaced by verified-source waiting,
real constrained ART provenance, live derivation route replay, visibility, and
dispatch recovery tests. No skip or xfail was introduced.

## CI integrity

The repository-wide 78% floor remains unchanged. The backend workflow adds 90%
coverage reports for the project subsystem and project-agent boundary without
weakening lint, E2E, semantic-lane, skip/deselect, or existing subsystem gates.

## Reviewer results

Architecture, security, product/ops, senior engineering, CI integrity, docs,
reuse/dedup, test-delta, and QA passed after findings were resolved.

## External review

Agent Gates pass after one stale-vocabulary correction. Three Backend runs
progressively exposed stale setup-run, verified-report, warning-acknowledgement,
and direct-service fixture assumptions. A fourth run established the exact
combined AUTH+ART schema fingerprint after migration reconciliation. A fifth
run left one synthetic generation mismatch, now reconciled. A sixth run passed
the project lifecycle and identified one task-fixture helper that deleted an
immutable ART-bound setup run; it now preserves that lineage. A seventh run
passed both project and task lifecycle lanes and isolated the remaining
shared-foundations failures to merged OpenAPI inventory and migration-revision
test expectations; those tests now use the exact revision schema and the
outermost populated-lineage downgrade guard, while direct tests retain coverage
of the superseded `0039`, `0040`, and `0042` guards. The repairs are recorded in the
external-review response and require a fresh hosted rerun.
All earlier CodeRabbit inline findings were resolved, and its latest
incremental fixture-architecture finding is resolved through one shared
verified-lineage fixture. A full comment audit also closed the remaining valid
stale-contract and maintainability items; intentional transaction-held reads
and v0.1 operational settings are documented in the external-review response.

## Remaining risks

The broad PostgreSQL integration and migration matrix is delegated to hosted
CI because no local test database is configured. The implementation depends on
the already-merged AUTH-04B exact fixed-service actions and fails closed if
their live grants or identities are unavailable.

## Follow-up work

After merge and hosted evidence, the next planned ART sequence is submission
bundle work beginning with ART-04A. It starts only with human direction and its
own bounded chunk contract.

## Human review focus

Review migration refusal semantics, exact report-usage completeness, the
transaction-held AUTH/read boundary, dispatch claim recovery, and the removal
of all legacy guide-content authority.

## Human merge ownership

The human owner decides whether and when to merge this PR. This bundle does not
authorize merge.
