# WS-ARCH-001-CP01C PR Trust Bundle

## Chunk

`WS-ARCH-001-CP01C` — AUTH Adapter-Binding Fact Correction (L1).

## Goal

Make the still-unavailable adapter-binding authorization facts match the exact
CON resource identity and lifecycle generation before CP02 implements hidden
behavior.

## Human-approved intent

The user approved a clean correction with no backward compatibility: remove
the unrelated compensation unit, bind the server-selected adapter-binding ID,
and bind exact lifecycle versions for suspend/resume before proceeding to CP02.

## What changed

- Create facts now contain project, binding ID, instrument, adapter actor, and
  non-secret route key.
- Suspend/resume facts require an exact positive lifecycle version.
- Digest tests prove binding-ID and lifecycle-version sensitivity.
- The retired create shape containing `unit` is rejected.
- Active planning records insert CP01C between CP01B and CP02.

## Why it changed

The binding aggregate is project/instrument scoped and does not own a unit.
Omitting its selected ID and lifecycle generation would make the AUTH resource
digest less precise than the product mutation CP02 must eventually protect.

## Design chosen

Correct only immutable AUTH fact dataclasses and their canonical digest inputs.
Keep the four existing action identifiers, permission mapping, owner, and
planned/unavailable state unchanged.

## Alternatives rejected

- Keeping `unit`: it belongs to `ProjectCompensationUnit`, not the binding.
- Deferring correction into CP02: CON must not edit AUTH internals or build
  against a known incorrect digest.
- Compatibility constructors or dual digests: no action is active and v0.1
  preserves no obsolete contract.

## Scope control

No CON code, database schema, migration, trigger, catalogue row, evaluator,
grant, identity, service matrix, route, activation, retirement, callback,
fulfillment, or delivery behavior changed.

## Product behavior

None. All four adapter-binding actions remain planned and unavailable.

## Acceptance criteria proof

All CP01C contract criteria are checked. Tests cover immutable facts, invalid
UUID/version inputs, retired-shape rejection, digest separation/sensitivity,
catalogue mappings, and planned denial.

## Tests/checks run

- Focused Ruff: pass.
- Focused adapter-binding tests: 5 passed.
- Behavior-ownership and test-structure validation: pass.
- Stale authorization docs, chunk-state sync, Markdown links, and diff check:
  pass.
- Hosted CI will run PostgreSQL-backed semantic lanes and full coverage.

## Test delta

No test was removed, skipped, or weakened. Existing CP01A tests were renamed
and strengthened for CP01C; one retired-shape behavior test was added.

## CI integrity

No workflow, dependency, test runner, coverage threshold, or gate changed.

## Reviewer results

Plan, architecture, security/auth, senior engineering, QA, product/ops,
reuse/dedup, test-delta, and documentation reviews all pass. The valid
suspend/resume symmetry and verification-prerequisite findings were fixed.

## External review

Hosted CI passed on exact head `8e3e5563`. CodeRabbit completed as
rate-limited, and every actionable comment from its earlier review was fixed;
no unresolved live review threads remain.

## Remaining risks

The production actions remain unavailable, so CP02 and CP03 are still required
before any adapter-binding command can be used.

## Follow-up work

After merge, review and execute CP02 hidden CON binding behavior. CP03 later
integrates the exact evaluator and activates only the proven actions.

## Human review focus

Confirm that create has binding identity and no unit, mutations bind lifecycle
generation, no compatibility path exists, and action availability is unchanged.

## Human merge ownership

Only an authorized human may approve and merge this PR.
