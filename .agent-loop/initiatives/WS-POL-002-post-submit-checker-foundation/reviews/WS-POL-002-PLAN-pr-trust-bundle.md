# PR Trust Bundle

## Chunk

`WS-POL-002-PLAN` - Post-Submit Checker Foundation Planning

## Goal

Close the previous WS-POL-001 loop state and create the reviewed planning
foundation for project-guide-derived post-submit checker setup.

## Human-approved intent

- Intent: `.agent-loop/initiatives/WS-POL-002-post-submit-checker-foundation/INTENT.md`
- Plan: `.agent-loop/initiatives/WS-POL-002-post-submit-checker-foundation/PLAN.md`
- Chunk contract: `.agent-loop/initiatives/WS-POL-002-post-submit-checker-foundation/chunks/WS-POL-002-PLAN-post-submit-checker-planning.md`

## What changed

- Closed stale `WS-POL-001-16` loop state after PR #84 merged.
- Added WS-POL-002 intent, discovery, plan, decisions, risks, status, chunk map,
  and six chunk contracts.
- Normalized every WS-POL-002 chunk contract with approved-plan reference, risk
  class, SLA, allowed files, not-allowed changes, acceptance criteria,
  verification commands, reviewer set, human review focus, and stop conditions.
- Added external review response and refreshed internal review evidence.

## Why it changed

Post-submit checker setup needs the same discipline as pre-submit: setup-time
derivation, trusted compilation, project-scoped policy, deterministic runtime,
and no manual guide request-body checker payloads.

## Design chosen

The plan keeps `PostSubmitCheckerPolicy` project-scoped. An agent may derive a
constrained setup specification from approved project guide/source context, but
Workstream compiles deterministic checker policy and runtime executes only the
locked compiled policy.

## Alternatives rejected

- Per-task checker generation: rejected because tasks should lock references to
  the project policy/checker context, not compile their own checkers.
- Runtime agent judgment: rejected because submission checks must be
  deterministic and auditable.
- Manual guide payloads for post-submit policy: rejected because policy setup is
  server-owned.

## Scope control

### Allowed files changed

- `.agent-loop/LOOP_STATE.md`
- `.agent-loop/WORK_QUEUE.md`
- `.agent-loop/REVIEW_LOG.md`
- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/STATUS.md`
- `.agent-loop/initiatives/WS-POL-002-post-submit-checker-foundation/**`
- `docs/roadmap_status.md`

### Files outside scope

- None.

## Product Behavior

- [x] No Workstream product runtime behavior changed.
- [ ] Product behavior changed and is explained here:

## Acceptance criteria proof

- [x] WS-POL-001 loop memory closed - `LOOP_STATE.md`, `WORK_QUEUE.md`,
  `REVIEW_LOG.md`, and WS-POL-001 status updated.
- [x] WS-POL-002 planning artifacts created - intent, discovery, plan, decisions,
  risks, status, chunk map, and chunk contracts added.
- [x] Project-scoped post-submit policy preserved - plan and chunks reject
  per-task checker generation.
- [x] External review findings handled - see
  `.agent-loop/initiatives/WS-POL-002-post-submit-checker-foundation/reviews/WS-POL-002-PLAN-external-review-response.md`.
- [x] Internal review evidence refreshed - see
  `.agent-loop/initiatives/WS-POL-002-post-submit-checker-foundation/reviews/WS-POL-002-PLAN-internal-review-evidence.md`.

## Tests/checks run

```bash
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
python3 scripts/check_internal_review_evidence.py
git diff --check
for f in .agent-loop/initiatives/WS-POL-002-post-submit-checker-foundation/chunks/*.md; do rg -n "^## (Approved Plan Reference|Risk class|SLA|Stop conditions)$" "$f"; done
```

Result summary:

```text
Local stale wording, Markdown links, internal review evidence, chunk metadata
scan, and diff whitespace checks passed after the review-artifact update.
```

## Test delta

### Tests added

- None.

### Tests modified

- None.

### Tests removed/skipped

- None.

## CI integrity

- [x] Coverage threshold unchanged
- [x] Lint unchanged
- [x] Typecheck unchanged
- [x] No workflow weakening
- [x] No package script weakening
- [x] No unpinned new GitHub Action
- [x] Checkout credential persistence unchanged

## External review

External review response file:

- `.agent-loop/initiatives/WS-POL-002-post-submit-checker-foundation/reviews/WS-POL-002-PLAN-external-review-response.md`

| Source | Status | Notes |
|---|---:|---|
| CodeRabbit | Fixed locally | Title, risk class, privacy wording, and PR-description structure addressed. |
| GitHub checks | Fixed locally | Evidence provenance updated; checks must rerun on pushed head. |

## Reviewer results

Reviewed code SHA: f07160145fd5b92515cfbbd1c78c81a583a86508

Reviewed at: 2026-07-09T08:46:42Z

Reviewer run IDs: senior-engineering=019f4607-7d3d-75f1-9f95-1c97e6a754ed; QA/test=019f4607-9e65-7dd3-a4a1-e5902738c7ae; security/auth=019f4607-c400-7d70-ba90-d3a864da5619; product/ops=019f4607-e130-7183-935e-399d7c0da675; architecture=019f4608-0acf-72a0-a876-f9e0b2d1f8c6; docs=019f4609-1043-76f0-9474-7a0ecb9d43eb; CI-integrity=019f4610-a68c-7742-bff9-6b89fa3931c9

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS AFTER FIXES | None | Evidence provenance and push findings addressed by follow-up review artifact/push. |
| QA/test | PASS WITH LOW RISKS | None | Remote push was the only remaining low note. |
| security/auth | PASS | None | Privacy and redaction contract passed. |
| product/ops | PASS AFTER FIXES | None | Trust bundle and evidence findings addressed by this artifact. |
| architecture | PASS WITH LOW RISKS | None | Broad future runtime globs accepted as low risk. |
| docs | PASS AFTER FIXES | None | External response/trust-bundle findings addressed by this artifact. |
| CI integrity | PASS | None | Confirmed no workflow, script, package, or CI configuration changes; local evidence gate passes and artifacts do not overclaim remote checks. |

## Remaining risks

- `WS-POL-002-04` still allows broad future runtime globs. Architecture accepted
  this as low risk because the acceptance criteria constrain the allowed work to
  generated-policy runtime deltas.
- GitHub checks must rerun on the pushed PR head before merge.

## Follow-up work

Start `WS-POL-002-01` only after this planning PR is reviewed, merged by the
user, and the user explicitly starts the implementation chunk.

## Human review focus

Please inspect:

- the project-scoped post-submit checker setup direction
- the setup-time derivation versus deterministic runtime boundary
- the v0.1 setup authorization boundary
- the WS-POL-002 chunk sequence and stop condition before implementation starts

## Human ownership

- [ ] I can explain what changed.
- [ ] I can explain why it changed.
- [ ] I know what could break.
- [ ] I accept the remaining risks.
- [ ] The user explicitly approved this specific PR for merge.
