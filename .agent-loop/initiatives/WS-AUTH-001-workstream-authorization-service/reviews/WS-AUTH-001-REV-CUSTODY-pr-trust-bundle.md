# WS-AUTH-001-REV-CUSTODY PR Trust Bundle

## Chunk

`WS-AUTH-001-REV-CUSTODY` - REV Activation Custody Transfer (L1).

## Goal And Human-Approved Intent

Transfer exactly 19 planned REV action-owner labels to seven exact AUTH
activation custodians without changing permission mappings, availability, or
REV behavior. The user explicitly started this chunk after ART custody merged
and signed memory stopped at the REV gate.

## What Changed And Why

- Removes seven historical REV `ActionOwner` enum values and adds seven exact
  AUTH activation-custodian values.
- Changes only the owner field of the 19 canonical REV definitions.
- Preserves 74 PermissionIds, 65 ActionIds, 17 active and 48 planned actions,
  every ActionId-to-PermissionId pair, all non-REV owners, and the exact
  seven-identity/eleven-membership service matrix.
- Adds one literal independent 19-row fixture, exact docs parity, mutation
  rejection, and all-19 real-kernel denial proof.

The owner-only typed-catalogue transfer was chosen because AUTH owns activation
custody while REV continues to own resources, facts, guards, jobs, and hidden
behavior. Registration, runtime activation, a migration, or a combined PREP
change were rejected as boundary violations.

## Scope And Product Behavior

No migration, database or audit rewrite, availability change, evaluator,
resource composer, route, job, grant, service identity, matrix membership, or
REV lifecycle behavior is included. Custodian labels create no reviewer,
Operator, or service entitlement. All 19 actions remain planned and unavailable;
the four proposed lifecycle actions remain unregistered.

## Acceptance Proof And Test Delta

- Ruff passed for `app` and `tests`.
- 63 focused catalogue/kernel/documentation cases passed after review repair.
- Stale wording, stale authorization docs, Markdown links, loop-memory state,
  merge intent, Alembic-head/no-migration, and diff checks passed.
- No test or assertion was removed or weakened; no skip, xfail, deselection,
  exclusion, workflow, script, dependency, or threshold changed.
- The local environment has no test database; GitHub Backend remains the
  authoritative full-suite gate for global coverage at or above 78 percent and
  authorization coverage at or above 90 percent.

## Internal Review And CI Integrity

Final reviewed CI-repair SHA `438c2bcf6a91b97f46264a1b6e5d0110a28f16d5`, containing
reviewed implementation `baa86dfe94015f66570844ce81ed1310729cded1`, against
trusted main `be2a79a243ec50049c37f1f634322a9b3ab895ba` passes senior engineering,
QA/test, security/auth, product/ops, architecture, CI integrity, docs,
reuse/dedup, and test-delta review after two documentation findings were fixed.
No CI, coverage configuration, package command, workflow, or migration file
changed.
The repair only normalizes the PREP contract heading delimiter required by the
schema-v2 successor parser; it does not start or change PREP.

## External Review And Remaining Risks

GitHub Backend, Agent Gates, and CodeRabbit remain pending until publication.
The remaining risk is exact metadata/docs drift, bounded by literal independent
fixtures, exact table parsing, frozen whole-catalogue expectations, and hosted
full-suite proof.

## Follow-Up And Human Review Focus

The sole merge-intent successor is `WS-AUTH-001-PREP`, which must not start
until this PR merges, signed memory succeeds, and the user explicitly starts it.
Human review should verify the exact 19-row/seven-custodian owner-only delta,
`2/5/3/1/1/5/2` cardinalities, unchanged ART/non-REV rows, mappings, counts,
matrix and availability, absent lifecycle registration, and zero migration.

## Human Merge Ownership

The agent may publish and repair this branch but may not merge it. Only the
human may approve this PR for merge. Trusted-main automation owns signed
post-merge memory generation.
