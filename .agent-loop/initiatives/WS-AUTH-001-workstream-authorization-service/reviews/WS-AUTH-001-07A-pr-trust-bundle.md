# WS-AUTH-001-07A PR Trust Bundle

## Chunk

`WS-AUTH-001-07A` - Closed Permission And Action Catalogue

## Goal

Install one closed typed source for all 74 approved PermissionIds and exactly 50
planned ActionIds, then preserve exact typed/PostgreSQL audit parity without
making any action executable.

## What Changed

- Added a dependency-free authorization catalogue containing the exact 49
  historical and 25 new permissions plus 50 four-field planned action rows.
- Reserved canonical `submission.create` plus 19 review actions. Revision
  submission reuses `submission.create`; no revision-specific permission exists.
- Made authority audit validation consume the catalogue, enforce exact action-
  permission mapping, reject planned allowed decisions, and bound hostile input.
- Added nullable `audit_events.action_id` and PostgreSQL constraints for exact
  registry, mapping, decision-event, and new-permission evidence parity.
- Added guarded rollback custody under an exclusive table lock for action IDs
  and new permissions stored as decisions, target references, or invalidation
  references.
- Added exhaustive typed and PostgreSQL behavior tests and updated the canonical
  specification, operations runbook, and future owner contracts.

## Design Boundaries

All actions remain `planned`. This PR does not implement a decision evaluator,
grants, principals, resource loaders, composers, guards, caches, route cutovers,
artifact operations, or public permission APIs. AUTH-07B later owns only actor
self-read/self-update kernel activation after this PR merges and a separate
human start. AUTH-08 and AUTH-10 remain the authority prerequisites for admin
and project contexts.

## Acceptance Proof

- The independent runtime test literals prove the exact 74-value permission set
  and its exact 49/25 historical/new partition.
- Catalogue startup rejects missing, duplicate, extra, unknown, invalid-owner,
  invalid-availability, and metadata-mismatched rows.
- Planned ActionIds cannot resolve as executable and cannot be recorded as
  allowed decisions through the typed audit boundary.
- Direct SQL proves every exact pair, every wrong pair, every new permission
  without action evidence, unknown actions, and non-decision action use.
- Migration proof preserves populated historical evidence, restores the exact
  historical registry on downgrade, and blocks every forward-evidence path
  before destructive DDL.

## Tests And Coverage

- 37 focused authorization/audit behavior tests passed on isolated PostgreSQL.
- Authorization branch-aware coverage: 95 percent.
- Audit branch-aware coverage: 93 percent.
- Full isolated Alembic suite: 16 passed in 503.16 seconds at reviewed runtime
  SHA `3365e67e7b44195069a5c7645fdee0af1d4e0180`.
- Targeted exhaustive migration proof: 1 passed in 43.53 seconds.
- Catalogue/startup matrix: 10 passed.
- Ruff, stale wording, authorization-doc consistency, Markdown links,
  loop-memory state, and diff integrity passed.

GitHub Backend remains authoritative for the repository-wide 78 percent floor;
this PR does not change any coverage threshold or exclusion.

## Reviewer Results

Reviewed exact merged head `6f1b7ce5171d763cff2b5d6393784f80d4248187`
and runtime amendment `3365e67e7b44195069a5c7645fdee0af1d4e0180` passed
senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test-delta review with no remaining findings.

## Remaining Risks

- Database-owner credentials can bypass normal constraints and triggers;
  production runtime credentials must remain non-owner.
- Downgrade is intentionally unavailable after any forward action or new-
  permission evidence exists; recovery must proceed forward.
- Availability changes are typed-code owner decisions. PostgreSQL deliberately
  remains availability-neutral so later owner chunks do not rewrite migration
  `0021`.

## Human Review Focus

Review the exact 74/50 catalogue, planned-only typed behavior, exact SQL mapping,
historical audit preservation, four downgrade refusal paths, exclusive locking,
and the absence of kernel/grant/resource activation.

## Human Merge Ownership

Only the human may approve and merge this PR. GitHub checks, CodeRabbit, and
internal review do not authorize merge.
