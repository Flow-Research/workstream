# Terminal Systems repaired recovery trial

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Project-owned runtime checking exercises interruption on repaired retained state and rejects a failed restart verifier despite model approval.

## Intent

A real restart-safe repair must be tested after reference application. Starting
the interruption control from the deliberately broken starter makes valid
recovery work fail; allowing a failed restart verifier to pass model assessment
conceals that failure.

## Current behavior

`post/model/trial_plan.py` requires a fresh interruption workspace and seeds the
starter, while hiding reference material. `trial_assessment.py` guards resource
failures but omits nonzero restart verification from condition 11 contradictions.
The generic relay and execution engine already support exact retained-parent
state, so they need no change.

## Bounded change

### Allowed

- `pilots/terminal_systems/checkers/post/model/{trial_plan,trial_assessment,test_trial_plan,test_trial_assessment,test_runtime_checker}.py`.
- Focused local subprocess recovery proof under the existing model test suite.
- Checker README, qualification fixture README/author notes, affected capability wording in `docs/roadmap_status.md`, and this record.

### Not allowed

- Generic backend/runtime/relay changes, new schemas, migrations, subsystems or fallback paths.
- Reference visibility in interruption/restart/verification, or changing incomplete repair from fresh state.
- Changing retained-parent/export custody, existing locked bindings, deployed resources or unrelated worktrees.

## Design and decisions

Require `reference_baseline` in the prompt and strict proposal validator; the
existing plan builder resolves it to `reference_verify_3`. The interruption
projection inherits retained state without seed roles and exposes verification
only. Restart still inherits the exact interruption export and full verification
inherits the exact restart export. Require successful `restart_verification`
for condition 11, while allowing the documented interruption to be signalled.
Any subsequent use needs a new immutable image and projection binding; existing
locked selectors are not mutated.

## Acceptance criteria

- [x] Complete and partial proposals reject fresh interruption state.
- [x] Incomplete repair remains fresh; interruption inherits repaired state with no seed and verification-only visibility.
- [x] Local subprocess proof rejects the unrepaired starter and passes repaired interruption/restart through the generated plan and projection; restored defects fail the regression.
- [x] A nonzero restart verifier cannot receive an all-satisfied model pass; an exact condition 11 finding is accepted and a documented signalled interruption remains valid.
- [x] Focused suites, lint, stale wording and Markdown links pass; evidence distinguishes local semantics from real isolated/runtime qualification.

## Risk and review routing

- Risk class: L1 — bounded untrusted trial evidence and model false-pass boundary.
- Required reviewers: QA, test delta, security, documentation; lead coordinates focused independent review.
- Human review focus: Repaired-state intent, exact retained lineage, protected material visibility, false-pass rejection and new immutable runtime selector qualification.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Repaired recovery and failed-verifier guards | `python3 -m unittest discover -s pilots/terminal_systems/checkers/post/model -p 'test_*.py'` | Pass | Local subprocess proof does not qualify Smol, image registration or live model quality |
| Existing qualification fixture behavior | `python3 -m unittest discover -s pilots/terminal_systems/checkers/post/qualification -p 'test_*.py'` | Pass | Engineering fixture only |
| Regression sensitivity | In temporary copies, restore original plan; restore fresh seeded interruption projection; remove partial-plan state guard; remove restart-verifier contradiction | Each exact focused regression fails | Scoped manual defect probes, not general mutation coverage |
| Project code quality | `ruff check pilots/terminal_systems/checkers/post/model` and `ruff format --check pilots/terminal_systems/checkers/post/model` | Pass | No generic-owner or hosted suite claim |
| Current documentation | `python3 scripts/check_stale_workstream_wording.py`, `python3 scripts/check_markdown_links.py`, `git diff --check` | Pass | Markdown check covers changed local links |

## Review findings

Independent pre-implementation inspection identified both owner defects and
confirmed that generic state custody must remain unchanged. Lead-managed
independent review follows the frozen candidate.
The qualification fixture's author notes now agree with repaired-baseline
interruption; its README explicitly limits the literal-output restart control
to plumbing proof. The existing synthetic test remains intact, alongside the
new recovery-code regression.

## Reconciliation

- Current-source reconciliation: Based on main `ac637495f`; no generic-owner changes required.
- Roadmap reconciliation: Updated the detailed project-checker boundary. Executive summary, scoreboard, dependency diagram and remaining gates still correctly require exact image/binding/runtime qualification; this repair adds no generic capability or lifecycle branch. No local sheet exports exist in this worktree.
- Next usable boundary: Build/register an exact new image and projection, then qualify the real task through the public journey.
- Remaining risks: Real nested runtime and live-provider qualification remain separate from local tests.
