# WS-QUAL-001-PLAN3 PR Trust Bundle

## Chunk

`WS-QUAL-001-PLAN3` — Behavior And Mutation Assurance Planning.

## Goal

Keep the global Backend floor at 78 percent and replace the unstarted
percentage-only floor raise with a safe path for behavior-owned mutation
assurance.

## Human-approved intent

Coverage remains a permitted baseline, not proof that tests verify behavior.
The user confirmed 78 percent and directed planning for behavior and mutation
quality before implementation.

## What changed and why

- Reframed QUAL from “raise global coverage” to “prove assertion sensitivity.”
- Marked unstarted `WS-QUAL-001-04R` superseded.
- Declared `04M`, a bounded non-blocking-score mutation pilot.
- Declared `05M`, a separately approved blocking survivor policy only after
  accepted hosted pilot evidence.
- Added current-main facts, security/runtime risks, claim ownership, evidence
  rules, contributor boundaries, and exact chunk contracts.

## Design chosen

Mutation selection always includes eligible changed production logic and then
adds any explicit test-only behavior claims with owning test nodes. Claims use schema-v1
`.ci/behavior-claims/<chunk-id>.json`; mutable PR prose cannot widen them.
`04M` runs independently under hard limits and records complete outcomes.
`05M` is not authorized until pilot evidence is accepted by a human.

## Alternatives rejected

- Raising global coverage from 78 to 90: execution percentage is not behavior
  proof.
- Full-backend mutation per PR: operationally impractical.
- A global mutation score or “one mutant killed” rule: gameable and opaque.
- Immediate blocking rollout: uncalibrated noise and runtime.
- Retired signed-loop/machine-scope machinery: unnecessary for current simple
  contribution flow.

## Scope control

Only QUAL initiative planning records change. PLAN3 installs no tool, changes
no workflow or dependency, modifies no tests/application code, and changes no
coverage threshold.

## Product behavior

None. Product review decisions remain `accept`, `needs_revision`, and `reject`;
mutation outcomes are engineering evidence and never product decisions.

## Acceptance criteria proof

- Current main is recorded from Backend run `30926337804` on commit
  `5f2baf90`: 3,162 completed tests, 21,620 / 23,938 coverage (90.316651
  percent), 620.264 seconds wall, and 464.471 seconds slowest lane.
- Global 78 and protected 90 floors are explicitly preserved.
- Changed-production and test-only behavior paths are both planned.
- Strong-vs-weak seeded mutant proof, complete outcome evidence, runtime bounds,
  dependency custody, CI privilege controls, and a second human checkpoint are
  explicit acceptance requirements.

## Tests and checks run

Markdown links, all three stale scans, ten lightweight Agent Gate regression
tests, scope review, and whitespace validation pass.

## Test delta and CI integrity

No tests or CI files change. Future contracts forbid skips, xfails, assertion
weakening, coverage exclusions, Backend replacement, and changes to the 78/90
coverage policy.

## Reviewer results

All nine required tracks pass after resolving shared-helper, claim-boundary,
CI-privilege, dependency-custody, and contributor-onboarding conditions. No
reviewer session remains open.

## External review

Agent Gates, CodeRabbit, and human review are pending publication. Backend is
not required by the planning diff unless GitHub policy schedules it; no Backend
file changes.

## Remaining risks

Tool compatibility, equivalent-mutant noise, target/test selection quality,
and hosted runtime remain deliberately assigned to 04M pilot evidence.

## Follow-up work

After PLAN3 merges, 04M may start only by explicit human instruction. 05M
requires accepted 04M hosted evidence and a separate explicit decision.

## Human review focus

- Confirm the 78-percent global floor remains unchanged.
- Confirm this measures behavior rather than another percentage.
- Confirm the pilot is safe for untrusted contributor code and blocking remains
  behind a second human checkpoint.

## Human merge ownership

GitHub checks and explicit human approval are required. PLAN3 authorizes no
mutation implementation.
