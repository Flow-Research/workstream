# PR Trust Bundle: WS-XINT-002-01

## Chunk

`WS-XINT-002-01` — ART Catalogue Reconciliation.

## Goal and human-approved intent

Front-load the complete v0.1 ART authority catalogue before more ART runtime
work, while keeping every new action planned and unavailable. This removes the
unused multi-step upload design without compatibility aliases.

## What changed and why

- Replaced six obsolete upload actions/permissions with planned submission
  bundle preparation, reviewer packet materialization, and review evidence
  binding authority.
- Added only the distinct review-packet permission and assigned exact
  `WS-XINT-002-05A` / `WS-XINT-002-07` activation custody.
- Reconciled fixed services: scheduler loses expiry; materializer gains review
  packet; binding gains review evidence. No identity or grant was added.
- Added migration `0036` to keep PostgreSQL authority evidence constraints
  exactly aligned with the typed catalogue.

## Design and alternatives

The chosen design is a clean catalogue cutover with planned-only replacements.
Retained aliases, a second upload path, premature activation, and feature facts
inside catalogue metadata were rejected.

## Scope and product behavior

Changed only catalogue/admin schema, audit-constraint migration parity, tests,
and live AUTH/ART/REV handoffs. No route, evaluator, command, worker behavior,
grant, service identity, submission, review, or artifact lifecycle changed.

## Acceptance proof

- Closed totals: 71 permissions, 78 actions, 22 active, 56 planned.
- Fixed-service totals: seven identities and twelve exact memberships.
- All three added actions remain planned/unavailable.
- Migration refuses before mutation for direct, permission-registry target,
  invalidation, and idempotency-linked evidence; refusal preserves revision,
  constraints, and evidence counts.
- Current SQL rejects every removed pair and permission reference after clean
  upgrade and downgrade/re-upgrade.
- Deterministic repository scan permits obsolete identifiers only in named
  immutable historical artifacts and migration deletion proof.

## Tests and checks

- Ruff over `app`, `tests`, and `scripts`: passed.
- Focused catalogue/custody/stale tests: passed.
- Isolated PostgreSQL `0036_art_auth_catalogue` tests, including independent
  refusal predicates and round trip: passed with owned-database cleanup.
- Focused hosted-failure reproduction proves the refreshed schema fingerprint
  and exact downgrade through migration `0034` before re-upgrade to head.
- Stale authorization docs, stale artifact contracts, markdown links, and
  `git diff --check`: passed.
- A broader local AUTH/Alembic coverage run reached the 20-minute local runner
  ceiling; the complete suite and coverage gates are intentionally delegated to
  GitHub Actions on the exact PR head.

## Test delta and CI integrity

No test was removed, skipped, or weakened. New tests independently cover each
destructive migration predicate and negative post-head SQL acceptance. No CI,
coverage, lint, or runner configuration changed. Hosted gates remain the 78%
repository and 90% authorization-subsystem coverage floors.

## Reviewer results

Senior, QA, security, product/ops, architecture, CI integrity, docs,
reuse/dedup, and test-delta tracks all passed after valid findings were fixed.
See `WS-XINT-002-01-internal-review.md`.

## External review

The first hosted Backend run exposed a stale public-schema fingerprint and
non-canonical downgrade ordering across migration `0034`'s digest guard. Both
are corrected with focused `0036 -> 0033 -> head` proof. A later hosted run
exposed three integration assertions that still expected 76 permissions; they
now prove the closed 71-permission response. CodeRabbit's valid
documentation, mapping, and maintainability comments are addressed; the
constraint-name suggestion was rejected against the executed Alembic naming
convention. See `WS-XINT-002-01-external-review-response.md`. The corrective
exact head must still pass hosted Backend, Agent Gates, and CodeRabbit checks.

## Remaining risks and follow-up

Migration `0036` takes an access-exclusive audit lock for an atomic vocabulary
rewrite; deploy it as a bounded schema migration. `WS-XINT-002-02` is the next
same-initiative explicit-start gate. Later ART activation still requires exact
hidden feature evidence; this chunk grants no executable authority.

## Human review focus and merge ownership

Review the exact six-to-three clean cut, planned-only availability, fixed-service
least privilege, and evidence-preserving migration refusal. Only the user may
approve this specific PR for merge.
