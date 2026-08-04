# WS-QUAL-001-PLAN2 Review And PR Trust Bundle

## Intent

Reconcile QUAL from current hosted evidence and replace its obsolete 78-to-90
milestone ladder with the smallest owner-scoped path to a global 90-percent
backend floor.

## Baseline evidence

Backend run `30854931616` on exact tested tree
`19d48f7ea4bf20cb29f03cbba54f98683ce52661` and its hosted evidence record 2,925
completed tests, 20,793 covered of 23,475 statements, 88.575080-percent global
coverage, 640.284 seconds wall time, and a 468.506-second slowest lane. This is
the final ART-03C tested tree later merged to `main` through PR #249.

## Scope

Planning records only. No application, test, workflow, coverage threshold,
dependency, AUTH, ART, REV, CON, or external contributor change.

## Design

- 02R: exact PROJECT/setup test ownership in `test_projects.py`, target 89.55%.
- optional 03R: exact CHECKER ownership in `test_checkers.py`, target 90.25%.
- 04R: separate global CI floor change from 78 to 90 after exact >=90.25% proof.
- Any further gap requires one new owner-specific plan; no mixed residual bucket.
- Old 01B2 and 02-06 contracts are explicitly historical and non-executable.

## Internal review

- Architecture: initial FAIL on placeholder contracts, old active-looking
  contracts, and global/per-module ambiguity; all repaired; final PASS.
- Senior engineering: same contract/classification/wording blockers repaired;
  final PASS.
- QA: initial FAIL on missing exact commands/targets and inconsistent 90.25%
  headroom; repaired; final PASS WITH LOW RISKS, with wording polished.
- Product/operations: initial FAIL on cross-owner residual and CHECKER/TASK
  coupling; mixed residual deleted and 03R narrowed to CHECKER; final PASS.
- CI integrity: hosted counts independently verified; runtime stop controls and
  exact final headroom added; final PASS.
- Docs: PASS WITH LOW RISKS; original combined chunk disposition added to the
  map for complete historical navigation.

## Deterministic evidence

- `python3 scripts/check_stale_workstream_wording.py`
- `python3 scripts/check_markdown_links.py`
- `PYTHONPATH=. python3 scripts/test_lightweight_agent_gates.py`
- `git diff --check`

## Risks and human focus

Confirm the plan does not reward artificial tests, does not revive static
parser complexity, and keeps CI runtime visible. The first implementation
contract remains separately started after this planning PR merges.

## Merge ownership

GitHub checks and explicit human approval are required. PLAN2 authorizes no
test or workflow implementation by itself.

## External repair

Hosted Agent Gates found two ambiguous role-like references in changed planning
lines. They now say background-job modules/ownership, avoiding confusion with a
product actor class. CodeRabbit produced no actionable finding because its
review request was temporarily rate-limited.

After PRs #258 and #249 advanced `main`, PLAN2 merged that trusted head and
replaced its older PR #259 baseline with the final ART-03C hosted evidence.
