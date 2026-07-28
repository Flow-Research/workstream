# WS-AUTH-001-11B Internal Review Evidence

## Scope

Project identity and self authorization-context hard cutover to current local
grants. Review covered the complete branch diff against the corrected 11B
contract.

## Plan review

| Track | Result | Resolution |
|---|---|---|
| Architecture | PASS | AUTH owns the context projection; project and contributor response schemas remain distinct. |
| Security/auth | PASS | Exact actor/link revalidation, project scope, concealment, and route/action/evidence binding are explicit. |
| QA/test | PASS | Role matrix, denial cases, API controls, E2E, and focused project-read coverage are required. |
| Product/ops | PASS | Admin and contributor projections and role precedence are explicit. |
| Senior engineering | PASS | Exact manifests and the central decision/evidence path are explicit. |
| CI integrity | PASS WITH CONDITIONS | Preserve all existing lanes and floors; prove every new project-read branch without misrepresenting legacy project coverage. |

## Implementation review

| Track | Final result | Findings resolved |
|---|---|---|
| Architecture | PASS WITH LOW RISKS | Missing-project decisions now use AUTH evidence; unrelated roles are filtered; project lifecycle projection shares the kernel guard. |
| Security/auth | PASS | Both reads use human/rate admission; decisions retain matched grant/project evidence; matched grants remain locked through projection. |
| QA/test | PASS WITH LOW RISKS | Added contributor, cross-project, revocation, suspension, link-revocation, rate, nonhuman, missing-project, and archived-project proof. |
| Product/ops | PASS | Context includes active AUTH-10B/10C/11B project actions and excludes planned 11C actions. |
| Senior engineering | PASS WITH LOW RISKS | Restored scope-specific denial evidence and public service exports. |
| CI integrity | PASS WITH LOW RISKS | No established gate weakening; hosted full-suite, global 78%, and actor/authorization 90% floors remain required. |

## Local evidence

- `ruff check app tests scripts`: passed.
- Focused kernel, context projection, rate-admission, and nonhuman tests: passed.
- `tests/test_api_controls.py`: 27 passed.
- Catalogue activation test: passed.
- Python compile and docstring gate: passed.
- Stale wording, stale authorization docs, Markdown links, lightweight agent
  gates, and `git diff --check`: passed.
- Database-backed route tests and the complete suite/coverage are intentionally
  delegated to the mandatory hosted Backend workflow.

## Residual review focus

The manual `_PROJECT_CONTEXT_ACTIONS` inventory must be updated by future
project-action activation chunks. A later catalogue metadata grouping may
replace it; no additional abstraction is required for 11B.
