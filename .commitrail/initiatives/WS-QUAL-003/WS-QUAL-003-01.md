# WS-QUAL-003-01 — Remove duplicated proof and exercise real authority defaults

- Initiative: WS-QUAL-003
- Durable disposition: Planned
- Intended merge outcome: Remove proven AUTH/CON duplication while strengthening
  service-default denial and prepared-fact binding without changing production.

## Intent

Start the full suite audit with a small, inspectable example of fewer redundant
executions and stronger critical assertions. This is not the completed suite
audit or the decomposition of the existing monoliths.

## Current behavior

- Policy draft quantity tests repeat the same five invalid money strings;
  two required-rule tests call the same pure validator with the same missing rule.
- Publish's alleged default-denial test repeats injected prepare denial. Retire
  likewise installs an exception fake instead of using constructor defaults.
  Another publish test already reaches the real default; consolidate rather
  than claiming this behavior is globally untested.
- AUTH's system suspend/resume success tests duplicate the existing scope/action
  matrix. Its combined read/create/replay test repeats successful read proof.
- Adapter-binding consume tests lack a validly shaped changed-fact matrix at
  the actual in-process PREP adapter. In-process proof is not PostgreSQL proof.

## Bounded change

### Allowed

- This record, `OVERVIEW.md`, and `.commitrail/INDEX.md`.
- `backend/tests/authorization/test_adapter_binding_authorization.py`.
- `backend/tests/contributions/test_policy_draft_rules.py`.
- `backend/tests/contributions/test_policy_publication_authorization.py`.
- `backend/tests/contributions/test_policy_publish.py`.
- `backend/tests/contributions/test_policy_negative_scope.py`.
- `backend/tests/contributions/policy_test_support.py`.
- `.ci/behavior-contracts/contribution-policy-draft-behavior.md` only to map
  a removed duplicate's criterion to its retained exact test.

### Not allowed

- Production code, migrations, dependency/config/workflow changes, skips,
  weakened coverage thresholds, historical files, live authority activation.
- Removing distinct parameter values, SQL/concurrency tests or unrelated tests.
- Pretending the fake repository proves rollback, database locking or isolation.

## Design and decisions

Keep the separately named non-positive and non-canonical quantity matrices;
remove only the aggregate that repeats both. Retain the exact missing-rule
test `test_update_requires_exactly_one_completed_review_rule`, remove
`test_update_rejects_missing_required_rule_without_effect`, and remap that
criterion to the surviving exact test in the current behavior contract.

Keep `test_cp04b_exposes_only_hidden_policy_commands` as one exact static
service API-shape assertion; remove its 13 subsumed presence/absence probes.
This proves exposed attribute shape, not absence of downstream runtime effects.

Keep injected prepare/consume failures as service port-contract tests. Separately
construct the production service without mutation authorization, allowing other
fixture dependencies to remain controlled. Ensure valid policy state reaches
the real default-authority boundary. Publish/retire must deny without changing
policy/version state or calling custody/event persistence. Replacing the default
with permissive authority must make that denial assertion fail.
Strengthen the canonical `test_publish_denies_without_composed_authority` and
remove `test_policy_publish.py::test_publish_is_hidden_deny_default`, whose
weaker default-denial/custody assertions are thereby preserved.

Keep AUTH's existing two-scope/three-action success matrix. Remove its redundant
system-transition subset. Make the read/create/replay test focus on replay with
no extra evidence; initial consumption remains necessary setup.

For new consume substitutions use valid fact shapes: operation/request digest,
project, binding, instrument, target adapter actor and route. Exercise the actual
AUTH adapter/PREP implementation, not a fake raising a matching error label.
Each mismatch denies without new allowed evidence. A separate fresh valid
control succeeds once; close the rejected handle before issuing the fresh
control. Test replay before close, then close after observing no extra evidence.
Use temporary in-memory normalization of the substituted field in the real
adapter's `_mutation_context` to verify the mismatch assertion fails when
consumption incorrectly succeeds. Bypassing only a later matching helper is
insufficient because PREP checks the rebound binding earlier. This mutation is
out-of-tree verification, not a committed fake or production bypass.

## Acceptance criteria

- Every removed node has an exact surviving behavioral assertion, including
  all five invalid quantities and all system/project mutation success cases.
- Publish and retire use real constructor-default authority and reject with no
  service-level product effect; injected prepare failure remains separately tested.
- Changed-fact consume denial reaches real PREP with valid facts, produces no
  allowed evidence, and is distinguished from a successful control.
- Replay rejects without adding evidence; unrelated read proof is retained.
- Changed test files remain below 500 lines; no new test-module import coupling.
- Hosted full execution and current global/subsystem coverage floors pass.

## Risk and review routing

- Risk class: L1 (test-only authorization/contribution proof).
- Required reviewers: plan review before edits; QA/test-delta, security and
  CI-integrity on the bounded implementation. Combine related tracks, no fanout
  to unaffected architecture or product lifecycle implementation.
- Human review focus: retained protection and genuine missing-proof replacement,
  not the raw amount of test deletion.

## Evidence

Run focused pytest for all five changed test modules, Ruff on changed Python,
Markdown links, Commitrail checks, and `git diff --check`. Full coverage and
database lanes run only in hosted CI. Record precise baseline/new node counts,
surviving assertions, targeted mutation observations and limits in the PR.
Only service/in-process custody is claimed for these fixtures.

## Reconciliation

- Baseline: main `12c58431`; no open PR overlapped at discovery.
- Next usable boundary: PROJECT and AUTH oversized test decomposition from the
  initiative overview, after this bounded change is reviewed and merged.
- Remaining risk: most of the 4,352-case suite is not yet semantically audited.
