# WS-AUTH-001-11 Internal Review Evidence

Reviewed code SHA: `ed0f58732fd76388ec32309fccd37c4ad377ffad`

Reviewed planning SHA: `ed0f58732fd76388ec32309fccd37c4ad377ffad`

Reviewed against trusted main: `03a05eeb8f129e0d5f226cc5c058965f43590a81`

Reviewed at: `2026-07-25T19:20:00Z`

Reviewer run IDs: `auth11_senior`, `auth11_qa`, `auth11_security`,
`auth11_product`, `auth11_arch`, `auth11_ci`, `auth11_docs`, `auth11_reuse`,
and `auth11_testdelta`

External wording repair re-review: the same nine tracks re-reviewed the repair
from `ab16a1d7` through exact SHA `ed0f5873`; the sole reported blocker was this
evidence rebinding, resolved by this evidence-only update.

Reviewer tracks: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, and test delta

## Scope

AUTH-11 is a planning-only parent. It inventories ten existing project GET
surfaces plus one deferred self authorization-context route, records D34, and
splits runtime work into 11A, 11B, 11C1, and 11C2. It changes no runtime,
migration, route, test, workflow, action availability, or product behavior.

## Deterministic evidence

- Merge-intent validation: PASS for `WS-AUTH-001-11`; only 11A is named and a
  fresh explicit start is required.
- Stale Workstream wording: PASS.
- Markdown links: PASS for all nine changed Markdown files.
- Agent gates: PASS, 100 tests.
- `git diff --check`: PASS.
- Changed files remain inside the planning-parent allowed paths.
- No CI, package, test, dependency, coverage threshold, or skip changed.

## Reviewer results

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| senior engineering | PASS AFTER FIXES | none | Literal routes, actor-route ownership, executable commands, and child stop conditions are exact. |
| QA/test | PASS AFTER FIXES | none | Cross-project, cross-guide, child binding, role matrix, OpenAPI, migration, and hosted proof are testable. |
| security/auth | PASS AFTER FIXES | none | No token-role fallback; permissions and projections preserve least privilege. |
| product/ops | PASS AFTER FIXES | none | Read-only Operator/Audit API inspection remains available without database access or mutation authority. |
| architecture | PASS AFTER FIXES | none | Catalogue, project application, repository, actor route, and child ownership boundaries are coherent. |
| CI integrity | PASS AFTER FIXES | none | Hosted full suite, 78 percent global, and applicable 90 percent subsystem floors remain mandatory. |
| docs | PASS AFTER FIXES | none | Every runtime child names required authorization, role, and project operations documentation. |
| reuse/dedup | PASS | none | Existing catalogue, policy matrix, resource-context, kernel, and project repository patterns remain canonical. |
| test delta | PASS | none | Planning parent changes no tests or thresholds; child proof requirements strengthen coverage. |

## Findings resolved

The first review rejected invented project-only paths that omitted `guide_id`,
an unavailable actor router path, a nonexistent merge-intent command, and broad
reuse of `project.read` for sensitive data. Repairs now use literal mounted
paths and project/guide/child bindings, the existing auth router composition,
the canonical validator, and two narrow read-only permissions.

Product review then identified that denying Operator/Audit would force setup
inspection outside the API. 11A now introduces exactly
`project.setup_diagnostic.read` and `project.effective_policy.read` for Project
Manager, system Operator, and covered Audit Authority. Finance Authority,
Access Administrator, and contributors deny. Read access never implies
management. Final contract consistency, role-matrix proof, documentation, and
signed-state wording findings were repaired and re-reviewed at the exact SHA.

Valid findings addressed: yes

Open sub-agent sessions: none after evidence publication

## Remaining gate

GitHub Agent Gates, external CodeRabbit review, and explicit human review remain.
After merge, signed memory must stop with 11A named but inactive; 11A requires a
fresh protected explicit start on exact current `main`.
