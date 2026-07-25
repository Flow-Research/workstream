# PR Trust Bundle: WS-AUTH-002-PLAN

## Chunk

`WS-AUTH-002-PLAN` — Authorization Docstring Lint Correction Planning Intake

## Intent and outcome

Establish a narrow AUTH-owned corrective contract for four public-docstring
findings without weakening Ruff, docstring coverage, CI, or authorization
behavior. This PR is planning-only and does not apply the docstrings.

## Design and scope

- Adds exactly one new initiative planning tree and one merge intent.
- Names `WS-AUTH-002-01` as the same-initiative implementation successor.
- Leaves the initiative stopped and requires a separate explicit signed start.
- Preserves `WS-AUTH-001-11` as the unrelated project visibility cutover.
- Forbids runtime, schema structure, API structure, migration, test, workflow,
  package, configuration, and gate changes.

## Acceptance proof

- The successor owns only `_reason`, `ProjectRoleGrantIssueBody`,
  `ProjectRoleGrantRevokeBody`, and `ProjectRoleGrantMutationResponse` in one
  AUTH schema module plus its evidence and merge intent.
- Exact Ruff 0.15.22 and the unchanged Ruff invocation pass.
- Unchanged docstring coverage passes at 84.3 percent overall.
- All 100 agent-gate regression tests pass.
- Merge-intent validation, Markdown links, stale wording, module compilation,
  and whitespace checks pass.

## Reviewer results

Reviewed code SHA: 9b2677b01aee3842850292566ab8a4450cc6ba26

Reviewed at: 2026-07-25T09:06:31Z

Open sub-agent sessions: none

Valid findings addressed: yes

| Reviewer | Result |
|---|---:|
| senior engineering | PASS |
| QA/test | PASS |
| security/auth | PASS |
| product/ops | PASS |
| architecture | PASS |
| CI integrity | PASS WITH LOW RISKS |
| docs | PASS |
| reuse/dedup | PASS |
| test delta | PASS |

The CI low risk is informational: no CI file changes, and the exact existing
Ruff/docstring gates pass. There is no remaining blocking finding.

## Remaining risks and sequence

This planning PR intentionally leaves the four findings unresolved until its
successor is signed. After human-approved merge, dispatch `WS-AUTH-002-01`,
implement the four docstrings, run its full review/evidence loop, and merge that
corrective PR. Only then should PR #198 integrate trusted `main` and rerun
exact-head checks.

## Human review focus

Confirm the PR contains planning artifacts only, preserves AUTH-11, permits
exactly four docstrings, and cannot weaken Ruff or any CI/test gate. Only the
user may approve and merge this specific PR.
