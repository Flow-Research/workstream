# WS-ART-001 04B1 PR Trust Bundle

## Chunk

`WS-ART-001-04B1` — Default Checker Catalogue

## Goal

Install the single typed, versioned Workstream pre-submission catalogue and
compile one immutable effective plan from platform defaults plus the exact
locked project policy.

## Human-Approved Intent

ART owns the generic platform defaults and the single composition mechanism.
The Project Guide workflow continues to generate and lock project-specific
policy. No second API or registry is allowed.

## What Changed

- added 26 closed platform-capability and policy-primitive definitions;
- added startup-owned enabled/disabled configuration and validation;
- replaced compiler-local primitive/name/policy-field maps and removed the
  durable checker registry as pre-submit compiler authority;
- added a pure effective-plan compiler with exact lineage, catalogue manifest,
  definition/configuration hashes, and deterministic rule-instance identity;
- added focused tests and a non-weakening hosted 90 percent checker coverage
  gate;
- reconciled merged PLAN5 and active 04B1 status.

## Why It Changed

Scattered maps and the durable checker registry could become alternate
pre-submit authorities. Workstream needs one discoverable catalogue where
mandatory disabled state fails closed and locked project policy can only add or
narrow requirements through constrained definitions.

## Design Chosen

Frozen dataclasses and closed enums define catalogue identity, classification,
phase/dependencies, typed inputs, dispatch capability, result schema, budget,
policy trace, and disabled behavior. The effective-plan compiler requires the
startup-owned catalogue explicitly; it has no all-enabled fallback. It is pure
and performs no artifact read, checker execution, persistence, or routing.

## Alternatives Rejected

- Keep compiler maps beside the catalogue: duplicate authority.
- Reuse durable `default_checker_registry`: wrong lifecycle owner.
- Optional catalogue with an enabled fallback: bypasses deployment state.
- Dynamic plugin discovery or project registries: violates the closed v0.1
  contract.

## Scope Control

No ZIP parsing, scratch materialization, checker execution, durable evidence,
migration, route, provider I/O, AUTH availability, Submission/admission,
review, contribution, payment, or reputation behavior changed.

## Product Behavior

No contributor-facing behavior is activated. Unknown startup configuration
fails closed. Mandatory disabled definitions make the future preparation path
infrastructure-unavailable; advisory disabled definitions remain visible in the
plan.

## Acceptance Criteria Proof

- one catalogue owns all pre-submit definition/dispatch metadata;
- all 26 initial definitions are stable, versioned, ordered, bounded, and typed;
- compiler parallel maps and durable-registry dependency are removed;
- plan identity includes project, guide, snapshot, effective policy, pre-submit
  policy, catalogue manifest/state, and ordered configuration facts;
- broad token/secret/credential/dependency-directory heuristics are absent from
  the generic catalogue;
- no runtime bytes or durable effects occur.

## Tests And Checks Run

See `WS-ART-001-04B1-internal-review-evidence.md`. Focused tests and 93.85
percent new-module coverage pass. Database-backed and repository-wide coverage
remain hosted-CI responsibilities.

## Test Delta

One new focused test module; no tests removed, skipped, or weakened.

## CI Integrity

Adds `coverage report --include='app/modules/checkers/*' --fail-under=90`.
No threshold, lane, workflow, package script, or existing gate is weakened.

## Reviewer Results

Preimplementation architecture/security/product reviews passed with conditions
that are incorporated. Final internal reviewers are pending because the
reviewer service authentication failed twice. This PR remains draft.

## External Review

GitHub Backend/Agent Gates and CodeRabbit begin after draft publication.

## Remaining Risks

- final internal reviewers may require repairs;
- hosted database tests and aggregate/per-file coverage must pass;
- 04B2 must consume the exact plan without adding another dispatch path.

## Follow-Up Work

After human merge, stop. `04B2` begins only under a separate explicit request.

## Human Review Focus

- Is the catalogue the only pre-submit authority?
- Can startup-disabled mandatory entries ever be bypassed?
- Does the plan combine locked project policy without executing it?

## Human Merge Ownership

- [ ] Required final internal reviews pass.
- [ ] Hosted CI and CodeRabbit pass.
- [ ] I can explain what changed and what could break.
- [ ] I explicitly approve this PR for merge.
