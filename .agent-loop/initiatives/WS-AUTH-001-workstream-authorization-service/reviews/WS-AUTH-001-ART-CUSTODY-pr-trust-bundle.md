# WS-AUTH-001-ART-CUSTODY PR Trust Bundle

## Goal

Transfer exactly 25 planned ART action-owner labels to eight exact AUTH
activation custodians without changing permission mappings, availability, or
ART behavior.

## Changes And Design

- Removes seven historical ART `ActionOwner` enum values and adds eight exact
  AUTH activation-custodian values.
- Changes only the owner field of the 25 canonical ART definitions and the
  matching closed fixed-service metadata expectations.
- Preserves 74 PermissionIds, 65 ActionIds, 17 active and 48 planned actions,
  every ActionId-to-PermissionId pair, all non-ART owners, and the exact
  seven-identity/eleven-membership service matrix.
- Adds literal independent catalogue truth, exact documentation parity, and
  all-25 real-kernel denial proof.

## Scope Control

No migration, database or audit rewrite, availability change, evaluator,
resource composer, route, command, grant, service provisioning, identity,
matrix membership, or ART runtime behavior is included. `OPERATOR` denotes
future activation custody only and creates no entitlement. Verification retry
remains planned and independently gated.

## Proof And CI Integrity

- Ruff passed for `app` and `tests`.
- 45 focused catalogue/kernel/documentation tests passed.
- Stale wording, stale authorization docs, Markdown links, loop-memory state,
  merge intent, Alembic-head/no-migration, and diff checks passed.
- No tests or assertions were removed or weakened; no skips, xfails,
  deselection, exclusions, workflows, scripts, or thresholds changed.
- GitHub Backend remains the authoritative full-suite gate for global coverage
  at or above 78 percent and authorization coverage at or above 90 percent.

## Internal Review

Final reviewed SHA `a20ab6b2004e2f7a13e1e0d600595f0af7d67985`, containing
reviewed implementation `abb3fb1a035f544f5ee07b7d725451dfa2d90864`, against
trusted main `42a89b2deac8fc7672556a567a6124f8a4e5d423` passes senior engineering,
QA/test, security/auth, product/ops, architecture, CI integrity, docs,
reuse/dedup, and test-delta review after all valid proof findings were repaired.
The final CI repair preserves four authored trusted-main status fixtures
byte-for-byte rather than weakening their gate; all 88 agent-gate regression
tests pass. Canonical live state remains automation-owned.

## Remaining Risk And Follow-up

Hosted Backend CI, Agent Gates, CodeRabbit, and human review remain. The merge
intent names only `WS-AUTH-001-REV-CUSTODY`, which remains inactive until this
PR merges, signed memory succeeds, and the user explicitly starts it.

## Human Review Focus

Verify the exact 25-row/eight-custodian owner-only delta, unchanged non-ART and
REV owners, unchanged mappings/counts/matrix/availability, custody-only
`OPERATOR` meaning, independent retry gating, and absence of a migration.

## Human Merge Ownership

The agent may publish and repair this branch but may not merge it. Only the
human may approve this PR for merge. Trusted-main automation owns post-merge
schema-v2 memory generation when the workflow succeeds.
