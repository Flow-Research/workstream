# PR Trust Bundle: WS-ARCH-001-CP01B

## Chunk

WS-ARCH-001-CP01B — AUTH ContributionPolicy Registration

## Goal

Register the five canonical `contribution.policy.*` authorization actions and
typed resource facts while keeping every action planned and unavailable.

## Human-approved intent

Establish only the ContributionPolicy AUTH boundary, then return ownership to
CP02 for hidden adapter-binding behavior. Do not begin the broader CON lifecycle.

## What changed and why

- Added five closed ActionIds under `WS-ARCH-001-CP01B`, mapped only to the
  existing `compensation.policy.manage` PermissionId.
- Added dependency-free immutable read/create/update/publish/retire facts and a
  domain-separated canonical digest helper.
- Bound publish facts to the exact draft, canonical rules/definitions digest,
  and sorted unique adapter-binding identities.
- Added focused behavior tests, ownership evidence, lane custody, catalogue
  parity, structural-debt reconciliation, and current documentation/status.

## Design chosen

The implementation follows the existing AUTH public-facts and planned-action
pattern. It does not import CON internals or create another PREP protocol.

## Alternatives rejected

- No `compensation.policy.*` aliases.
- No generic resource dictionary.
- No evaluator, identity, grant, matrix row, route, migration, or activation.
- No CON behavior bundled into AUTH registration.

## Scope and product behavior

The five actions remain `PLANNED`; runtime product behavior is unchanged.
CP02 is the next boundary.

## Acceptance evidence

- Five exact actions map only to `compensation.policy.manage`.
- Catalogue totals are 73 permissions, 111 actions, 57 active, and 54 planned.
- All actions fail closed through executable-action resolution.
- Typed facts are frozen and lifecycle-bound; publish lineage is canonical.
- No legacy action alias or service assignment exists.

## Tests and CI integrity

Local focused evidence:

- Ruff: passed.
- CP01A/CP01B registration tests: 10 passed.
- Closed catalogue parity: passed.
- CI lane and behavior-ownership tests: 140 passed.
- Structural-debt, behavior-ownership, lane collection, docstring coverage,
  stale wording, Markdown links, chunk-state sync, and diff checks: passed.

No test, coverage, lint, preflight, or branch-protection gate was weakened.
Hosted CI owns the full repository suite and coverage proof.

## Test delta

One focused CP01B module covers registration denial, immutability, lifecycle
state, publish digest/binding canonicalization, cross-action rejection, API
exports, and collection scope. Existing catalogue assertions were strengthened.

## Reviewer results

- Architecture: pass.
- Security/auth: pass.
- Senior engineering and QA/test delta: pass.
- Product/ops: pass.
- Reuse/dedup: pass.
- Documentation: pass.

## External review

CodeRabbit and hosted CI are pending on the PR exact head.

## Remaining risks and follow-up

The identifiers are deliberately unusable until hidden owner behavior and a
separate AUTH activation merge. CP02 implements hidden adapter-binding behavior;
CP03 owns its later activation.

## Human review focus

Confirm the exact five-action manifest, canonical publish binding lineage,
absence of executable authority, and CP02 as the next boundary.

## Human merge ownership

Only an authorized human maintainer may approve and merge this PR.
