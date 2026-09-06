# WS-QUAL-003-02 — Decompose PROJECT readiness proof and prune retired-route duplication

- Initiative: WS-QUAL-003
- Durable disposition: Planned
- Intended merge outcome: Reduce the PROJECT test monolith while preserving its
  readiness matrix and strongest retired-route isolation proof.

## Intent

Begin actual PROJECT file decomposition, not just a test-count reduction.
Separate one cohesive readiness boundary, remove proven duplicate route setup,
and add direct composition proof for the retired endpoint.

## Current behavior

`backend/tests/test_projects.py` has 15,700 lines. Its activation-ready bundle
helper is itself frozen structural debt (118 lines). The readiness matrix has
distinct lineage/status/provenance cases that must survive. Five database-heavy
retired derivation-route tests ultimately repeat 404; the strongest existing
test additionally proves zero runtime calls and no derived policy rows.

## Bounded change

### Allowed

- This record and `OVERVIEW.md` for the next usable boundary.
- `backend/tests/test_projects.py`: remove only the five named duplicates and
  relocate the readiness bundle, field setter, matrix and success test below;
  preserve live warning-status translation in the existing report-coexistence test.
- `backend/tests/projects/test_activation_readiness.py`: cohesive relocated
  readiness proof, with small dependency-focused fixture builders.
- `backend/tests/projects/test_retired_submission_derivation_route.py`: actual
  app route registration and OpenAPI absence assertions, no database setup.
- `backend/scripts/run_test_lanes.py`: register the two new modules in the
  existing project lane only; preserve execution and collection integrity.
- `backend/tests/test_ci_test_lanes.py`: add only the two corresponding expected
  paths in `test_measured_hotspots_have_explicit_semantic_owners`.
- `.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json`: reconcile exact inventory;
  remove the extracted oversized helper debt and shrink the monolith entry.

### Not allowed

- Production, migration, runtime activation, policy semantic or API changes.
- New imports from `test_projects`, new shared global fixtures, compatibility
  exports, skips, lower coverage floors, or CI selection weakening.
- Removing a distinct readiness parameter, SQL race, or provenance assertion.
- Claiming this completes PROJECT or the whole-suite audit.

## Design and decisions

Move `_activation_ready_bundle`, `_set_activation_fact`,
`test_activation_readiness_rejects_broken_chain_fact`, and
`test_activation_readiness_accepts_complete_chain_without_payment` into the
new readiness module. Split the long fixture by policy dependency, keeping its
exact facts and hashes. Preserve settings-cache cleanup and monkeypatch lifetime.
The existing parser/merge stubs remain explicit: this proves service readiness
guards, not parser correctness, database locking or guide activation end to end.

Remove only these `test_submission_artifact_policy_` suffixes:

- `public_agent_derivation_route_and_service_seam_removed`
- `removed_agent_derivation_route_discloses_no_state`
- `removed_agent_route_cannot_read_verified_sources`
- `removed_agent_route_cannot_reuse_existing_policy`
- `human_cannot_invoke_removed_agent_route`

Retain `test_submission_artifact_policy_removed_agent_route_performs_no_runtime_calls`
(two concurrent 404 responses, runtime call count zero, no derived policy rows),
`test_submission_policy_derivation_has_no_public_project_service_seam`, and
`test_agent_derived_policy_approval_revalidates_server_owned_provenance` unchanged.
Setup observations in removed tests are not evidence that the absent route can
process warnings, read bytes, or reuse a policy. Preserve the separate sufficiency,
source-usage and approval tests that actually own those behaviors.

Before deleting the two warning-bearing route setups, change the existing
`test_sufficiency_agent_coexists_with_manual_diagnostic_report` to use their
hostile guide input and assert the live result status is `passed_with_warnings`.
Keep all its existing coexistence and persisted-report assertions. This retains
the otherwise-unique mapping from agent `guide_sufficient_with_warnings` to
report `passed_with_warnings`; manually seeded warning reports do not prove it.

Add distinct registration and OpenAPI tests: a hidden registered route must fail
registration proof even though it remains absent from OpenAPI. Temporarily adding
the route in memory must break the relevant assertion. Do not ship a fake route.

## Acceptance criteria

- Every readiness parameter and its expected rejection message survives; the
  valid control survives with the same controlled dependencies.
- Relocated tests import no test module. New files stay below 500 lines; fixture
  helpers below 100, with one primary responsibility per builder.
- The old helper debt disappears because it was decomposed, not merely renamed
  or moved beyond the inventory's scope. Remaining ledger changes are exact spans
  and hashes; no new or increased structural debt.
- Strongest runtime/database route proof and independent approval proof remain.
- Live warning-status translation remains asserted in the report-coexistence
  journey, not inferred from manually seeded report states.
- Real app registration/OpenAPI absence are each discriminating.
- The project lane collects every new module and full hosted coverage passes.

## Risk and review routing

- Risk class: L1, bounded security-sensitive test deletion and CI membership.
- Required reviews: pre-implementation plan; QA/test-delta, security/CI-integrity,
  and test-architecture/docs/reuse review, combined by affected boundaries.
- Human focus: preserved assertions and fixture ownership, not deletion volume.
- Size exception: relocation plus deletion may exceed 500 changed lines; exact
  old/new matrix comparison distinguishes moves from semantic changes.

## Evidence

Run focused new modules locally, Ruff on changed Python, module/structural and
behavior-ownership validation, Commitrail and Markdown/stale-wording checks.
Use hosted PROJECT execution for retained database proofs; never run the full
15,700-line suite locally. Compare baseline/current hosted node manifests:
relocations preserve cases, five duplicates disappear, two absence tests appear.
Run one temporary route-registration mutation and one readiness-guard bypass
probe to verify intended assertions fail rather than setup failing.
Run the existing exact lane ownership/inventory tests after adding both paths.

## Plan review corrections

- PLAN-01: explicitly include the exact CI membership assertion's file above.
- PLAN-02: preserve automatic warning-status translation through live sufficiency
  execution before deleting the obsolete endpoint setups. All original
  report-coexistence assertions remain. These are bounded scope corrections,
  not permission to change production or weaken gates.

## Reconciliation

- Baseline: main `0333faa1`, merged first proof cleanup PR #366.
- Next: continue PROJECT fixture/test decomposition and add inactive-project
  locked-policy denial with real PostgreSQL custody; AUTH decomposition follows.
- Most PROJECT bodies and the broader suite remain unaudited. The inactive-project
  database gap is explicitly not repaired by this change.
