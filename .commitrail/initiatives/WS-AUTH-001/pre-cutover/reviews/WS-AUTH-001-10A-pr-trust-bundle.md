# WS-AUTH-001-10A PR Trust Bundle

## Chunk

`WS-AUTH-001-10A` — Project Role Grant Data And Evidence Foundation

## Goal and approved intent

Establish immutable, privacy-bounded qualification snapshots and independent
submitter/reviewer/adjudicator grant truth before shipping reads or mutations.
The user approved the sequential 10A/10B/10C design and explicitly started 10A.

## What changed and why

- Migration `0031` creates qualification-snapshot and exact-role grant history.
- PostgreSQL enforces bounded opaque evidence, composite ownership, manual-only
  issuance, database timestamps, exact active-v1/revoked-v2 lifecycle, and
  immutable history.
- Typed and SQL audit vocabularies remove `both` and replacement evidence while
  retaining captured/issued/revoked events.
- Five future project-role actions and two denial codes are registered; every
  action remains planned and non-executable under its 10B/10C owner.
- The dormant authority mutation evidence matcher now accepts issued-only
  project-role success with no prior matched grant.
- Operator docs provide exact upgrade/downgrade preflight and lock/recovery
  guidance.

## Design and alternatives

One immutable row represents one actor/project/exact-role grant. Multiple roles
coexist; revocation never replaces another role, and regrant creates a new row.
Automatic inference, combined roles, replacement conversion, free-form evidence,
and shipping routes together with schema were rejected.

## Scope and product behavior

All changed files are contract-allowed. No route/OpenAPI, active action,
candidate/read API, mutation service, kernel/PREP, or product lifecycle behavior
was added. Current runtime behavior is unchanged.

## Acceptance proof and tests

Focused PostgreSQL proof covers fresh/previous-head migration, clean downgrade,
each and combined refusal predicate, exact no-mutation preservation, unrelated
history preservation, evidence bounds, composite ownership, role coexistence,
uniqueness, timestamps, immutable update/delete/truncate, lifecycle transitions,
five action pairs, and two denial codes. Typed schema/catalogue and complete
audit-event tests pass. Ruff, stale wording, Markdown links, and diff integrity
pass. Full coverage and E2E run in GitHub Actions per the approved fast-CI policy.

## Test delta and CI integrity

The generic Alembic round-trip test remains intact. Tests are additive; none are
skipped, deleted, or weakened. No workflow, package script, dependency, shard,
or coverage threshold changed.

## Reviewer and external results

Senior, architecture, reuse, security, QA, test-delta, product/ops, CI, and docs
all pass reviewed SHA `e8d9c37e`. GitHub Actions, CodeRabbit, and human review
remain external gates.

## Remaining risks and follow-up

The migration takes ACCESS EXCLUSIVE authority-table locks and refuses ambiguous
legacy evidence; operators must use the documented maintenance preflight.
AUTH-10B owns reads, and AUTH-10C owns PREP-bound mutations. Neither starts from
this merge without its explicit protected start event.

## Human review focus and merge ownership

Review privacy shapes, composite snapshot ownership, independent-role
uniqueness, immutability, refusal predicates, and the absence of exposed
behavior. The user retains approval for this specific PR and merge.
