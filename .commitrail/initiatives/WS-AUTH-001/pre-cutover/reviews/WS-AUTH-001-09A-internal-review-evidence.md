# WS-AUTH-001-09A Internal Review Evidence

Reviewed code SHA: `fe61df64fbf82a1f6871c380e6fc1986a4f12205`

Reviewed implementation SHA: `fe61df64fbf82a1f6871c380e6fc1986a4f12205`

Reviewed against trusted main:
`d541521790a0441cfd2193f466e00ef81248ec31`

Reviewed at: `2026-07-17T10:10:00Z`

Reviewer run IDs: `auth_xint_roles`, `auth_xint_art_service`,
`auth_xint_rev_con`

Reviewer tracks: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, and test delta

## Deterministic Evidence

- The catalogue imports as exactly 74 PermissionIds, 65 ActionIds, nine active
  actions, and 56 planned actions. AUTH-09A adds exactly eight planned actions.
- The fixed registry contains exactly seven service identities and eleven exact
  identity-to-ActionId memberships. No generic identity or broader membership
  exists.
- Every matrix row validates its current PermissionId, historical pre-custody
  ActionOwner, and planned availability. Adversarial tests reject missing,
  extra, duplicate, swapped, or metadata-drifted rows.
- The targeted catalogue, matrix, and audit suite passed 10 tests. A broader
  frozen-custody, mapping, and catalogue selection passed 54 tests.
- The exact revision `0023` PostgreSQL upgrade, confidential mapping, guarded
  downgrade, and re-upgrade path passed against an isolated database. The
  complete isolated selection passed three tests in 32.01 seconds.
- Branch-aware coverage is 94 percent for
  `actors/service_identity_migration.py`, 92 percent for
  `authorization/catalogue.py`, and 93.41 percent combined. Each materially
  changed subsystem remains above 90 percent.
- The operator tool and the frozen Alembic contract are two deliberately
  separate, parity-tested custody contracts. The mutable tool produces bounded
  canonical evidence; the packaged migration contract independently verifies
  and consumes it without importing application modules.
- Revision `0023` is location-independent, receives its repository root
  explicitly, disposes its async engine on the same event loop, and preserves
  the original bounded failure if cleanup also fails.
- Ruff, merge-intent validation, loop-state validation, stale Workstream,
  authorization, and artifact scans, Markdown links, all 80 agent-gate tests,
  91.9 percent docstring coverage, and diff integrity pass.
- No workflow, dependency, skip, exclusion, or coverage threshold changed.
  GitHub Backend remains authoritative for the repository-wide 78 percent
  floor.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| senior engineering | PASS | none | The bounded identity, catalogue, migration, and evidence foundation is coherent and reviewable. |
| QA/test | PASS | none | Behavior tests cover exact rows, inertness, metadata drift, private mapping, SQL guards, downgrade, and re-upgrade. |
| security/auth | PASS | none | Fixed local identity remains separate from the external credential link; no authority path activates. |
| product/ops | PASS | none | Internal services never become Contributors and receive no human or project-role grant. |
| architecture | PASS | none | AUTH owns identity, matrix, future evaluator integration, and activation; feature owners supply hidden behavior and typed manifests. |
| CI integrity | PASS | none | No workflow, dependency, threshold, skip, exclusion, or failure behavior was weakened. |
| docs | PASS AFTER FIXES | none | Pre-XINT activation language and successor omissions were reconciled with PR #140. |
| reuse/dedup | PASS AFTER FIXES | none | Evidence now describes the mutable operator tool and frozen migration verifier as separate parity-tested contracts. |
| test delta | PASS | none | Tests are additive and assert failure plus unchanged-state behavior, not coverage-only execution. |

## Findings Resolved

The convergence preserves the binding XINT sequence
`09A -> 09B -> 09C -> 09D -> 09E -> custody -> PREP`. Feature initiatives own
their hidden facts, guards, behavior, and typed manifests. Only the dedicated
AUTH activation custodian may later integrate evaluators and change action
availability.

AUTH-09A adds no route, provisioning, service-token admission, evaluator,
dynamic assignment, service grant, compatibility alias, fallback authority, or
feature runtime behavior. The 25 ART and 19 REV owner values remain historical
pre-custody metadata until their separate availability-neutral transfers.

Valid findings addressed: yes

Open sub-agent sessions: none

## Remaining Risk And Gate

Direct `O_EXCL` private-envelope publication does not fsync the parent
directory. A host crash may require regenerating the envelope; missing,
partial, or unverifiable evidence cannot pass migration or activate authority.

Replacement GitHub Backend, Agent Gates, CodeRabbit, and explicit human merge
approval remain. Do not start `WS-AUTH-001-09B` automatically.
