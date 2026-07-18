# Internal Review Evidence: WS-POL-001-11

## Chunk

WS-POL-001-11

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: 07295316c5973ea544d766b291d790147bc38920

Reviewed at: 2026-07-07T06:30:00Z

Reviewer run IDs: senior-engineering-review-019f3aa7-a13d-7052-85dc-635cbfa7dadb, senior-engineering-final-019f3ad7-f6ea-7d63-a2ba-614a31be77e1, senior-engineering-external-followup-019f3b41-4157-7651-a4f4-7882d0d27743, qa-test-review-019f3aa7-a9a4-7e80-9fb5-8b9961b0c913, qa-test-rerun-019f3ac2-c5d7-7e90-947f-85309bd89808, qa-test-final-019f3ad7-e4ed-78d2-a2f2-cccd1ed13172, qa-test-external-followup-019f3b41-4884-7582-bb51-431e9ba771cc, security-auth-review-019f3aa7-b1b3-73f2-959e-9eaae25fabd3, security-auth-final-019f3ad7-c49d-7141-95f3-3e7e7e4321e3, security-auth-final-019f3ae4-00fc-7083-8b3f-09e6dfe9cdbc, security-auth-external-followup-019f3b41-5050-7d03-b46b-1211feb41ab5, product-ops-review-019f3aa7-bce6-77b1-9053-09926c54b4c9, product-ops-final-019f3ad7-d48d-7712-8fe6-ac16bc686a9b, product-ops-final-019f3ae3-f393-7e22-85be-f5ddea8bc26f, product-ops-external-followup-019f3b41-575a-7150-b0e4-178bf73c413f, architecture-review-019f3ab2-f368-7f03-bff7-29999e5a076f, ci-integrity-review-019f3ab2-f9fd-7263-82a3-d6fdf9d3967b, ci-integrity-rerun-019f3ac2-d856-7c80-9bcf-63f5c5b71c2d, ci-integrity-final-019f3ad7-b07d-7b01-9d88-034546c16eb2, ci-integrity-final-019f3ae3-da6f-7522-a591-7aba0b86c168, ci-integrity-external-followup-019f3b41-7044-7971-8952-a3e914dd5f29, docs-review-019f3ab3-0752-7391-adac-3a72c9af37ba, docs-rerun-019f3ac2-ce8e-7c12-9bbe-c3ffc54d1166, docs-final-019f3ad7-b67e-7fe3-9601-fb0f8e8557bf, docs-final-019f3ae3-ea83-7fc3-82c2-50ebbef57bb1, docs-external-followup-019f3b41-60ff-7003-9180-c978466cfcba, reuse-dedup-review-019f3ab3-12ad-7c92-86e7-eee531d82a6a, reuse-dedup-rerun-019f3ac2-e587-7d33-a978-57734c17d681, test-delta-review-019f3ab3-2436-7b82-9e17-7dd083ef1afa, test-delta-rerun-019f3ac2-fb49-7530-968f-50cd1b79041b

After the reviewed SHA, only evidence and status files changed.

## Reviewed Change

Scope:

- Implements local `ActorIdentity` and shared `ActorProfile` persistence for verified Flow actors.
- Keeps `get_current_actor` as the pure Flow-token boundary and adds `get_registered_actor` for explicit registry side effects.
- Creates new `actor_identities` and `actor_profiles` tables, then drops obsolete `worker_profiles` and `reviewer_profiles` without compatibility backfill.
- Makes worker profile activation write `ActorProfile(profile_type="worker", status="active")` through the actor module.
- Applies registration side effects to `/auth/me`, worker profile setup, project routes, checker routes, and task routes touched by this chunk.
- Makes task claim require both a verified `worker` token role and an active worker profile.
- Preserves active/disabled profile metadata during token observation refreshes.
- Keeps persisted profiles as workflow eligibility/audit records, never route permission authority.
- Rewires demo/scripts/examples from `/api/v1/demo/worker-profile` to `POST /api/v1/workers/me/profile`.
- Aligns docs with Flow issuer plus subject as the canonical identity anchor and Workstream actor id as a local durable reference.
- Tightens role wording so Flow issuer plus subject is only the identity anchor; Workstream-owned role assignment is the product-role authority.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS AFTER FIXES | None | Required stale evidence wording to be fixed so the PR no longer claims compatibility backfill or deleted demo UI proof. |
| QA/test | PASS AFTER FIXES | None | Added disabled-worker claim denial and deleted demo-route regression coverage. |
| security/auth | PASS | None | Confirmed no valid security/auth findings on the final code SHA. |
| product/ops | PASS AFTER FIXES | None | Fixed role wording so Identity Issuer does not read as product-role authority. |
| architecture | PASS WITH LOW RISKS | None | Confirmed Flow auth boundary, actor/profile non-auth semantics, worker claim gate, and documented v0.1 audit ledger coupling. |
| CI integrity | PASS AFTER FIXES | None | Fixed the API contract E2E source-ref namespace and kept source-ref validation intact. |
| docs | PASS AFTER FIXES | None | Tightened Identity Issuer versus Workstream-owned role wording across docs and scripts. |
| reuse/dedup | PASS AFTER FIXES | None | Added full reviewer provenance and corrected route-registration scope in evidence. |
| test delta | PASS AFTER FIXES | None | Added disabled-profile claim denial, deleted demo-route assertion, and gate behavior coverage. |

## Valid Findings Addressed

- Fixed active/disabled profile observation so token-role observation refreshes do not overwrite explicit workflow provenance metadata.
- Added regression coverage proving active and disabled worker profile metadata stays `worker_profile_api` after observation.
- Added a shared `AuditRepository` so actor profile audit writes no longer depend on `TaskRepository`.
- Removed the redundant task-service worker-profile facade; the route calls `ActorService.activate_worker_profile` directly.
- Added persisted-value overposting assertions for `POST /api/v1/workers/me/profile` and task claim so spoofed identity fields cannot write malicious registry rows.
- Added migration assertions proving new actor registry tables exist and obsolete worker/reviewer profile tables are removed rather than kept as compatibility stores.
- Added metadata negative assertions so old `worker_profiles`/`reviewer_profiles` metadata exports cannot silently return.
- Removed stale `/api/v1/demo/worker-profile` usage from backend scripts, Terminal Benchmark example, and README.
- Removed the obsolete Week 1 demo UI package and workflow instead of preserving a stale compatibility surface.
- Documented exact `workstream_relationship_profiles` trusted claim schema and its non-authorizing behavior.
- Updated audit-event docs to match actual `actor_roles`, `from_status`, `to_status`, `is_dev_auth`, and `event_payload` fields.
- Aligned Flow Identity wording so docs consistently name Flow issuer plus subject as the canonical identity anchor.
- Fixed stale evidence after final internal review so the trust bundle no longer claims compatibility backfill or deleted demo UI proof.
- Added a disabled-worker-profile claim regression proving disabled profiles cannot satisfy worker eligibility.
- Added a route-regression assertion proving `/api/v1/demo/worker-profile` is no longer mounted.
- Documented destructive actor-profile migration behavior in the public data model.
- Updated historical internal-review notes to mark removed demo helper behavior as superseded.
- Changed the internal-review evidence gate so ordinary `docs/internal_reviews` notes are documentation, while current gate-satisfying evidence must live in `.agent-loop/...-internal-review-evidence.md`.
- Updated this evidence with full reviewer run IDs and project/checker route-registration scope.
- Fixed the API contract E2E source snapshot ref from an unapproved opaque namespace to `inline:/guides/...`.
- Reworded role documentation so v0.1 token roles are bootstrap request context and Workstream remains product-role authority.
- Reworded API drill docstrings so signed-token roles are bootstrap role claims, not roles granted by Flow.
- Fixed CodeRabbit follow-up findings for actor registry hot-path profile reads, shared relationship-claim parsing, actor audit repository coupling, and exact API contract output wording.
- Added regression coverage for malformed relationship claims, multiple scoped project-owner observations, missing scoped-profile refresh invalidation, and exact actor-profile audit payloads.
- Recorded the CodeRabbit response separately from internal review evidence.

## Commands Run

```bash
cd backend && .venv/bin/python -m ruff check app tests scripts
cd backend && .venv/bin/docstr-coverage --config .docstr.yaml
cd backend && .venv/bin/python -m ruff check scripts/api_contract_e2e.py scripts/week2_api_e2e.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check origin/main...HEAD
python3 scripts/test_agent_gates.py
python3 scripts/check_internal_review_evidence.py
cd backend && .venv/bin/python -m pytest tests/test_alembic.py tests/test_actors.py tests/test_auth.py -q
cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest -q
cd backend && .venv/bin/python -m pytest tests/test_auth.py::test_no_local_login_password_or_session_routes -q
cd backend && .venv/bin/python -m pytest tests/test_tasks.py::test_disabled_worker_profile_cannot_claim_ready_task tests/test_tasks.py::test_worker_without_profile_cannot_claim_ready_task -q
cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python scripts/api_contract_e2e.py
```

Results:

- Ruff: passed.
- Docstring coverage: passed at 100.0%.
- Stale wording scan: passed.
- Markdown link check: passed for 25 changed Markdown files.
- Diff whitespace check: passed.
- Agent gate tests: 26 passed.
- Internal review evidence gate: passed after this evidence update.
- Full backend pytest: 369 passed in 3116.81s.
- Migration/actor/auth tests: 41 passed in 348.89s.
- Actor registry focused tests: 16 passed in 190.65s.
- Auth tests: 21 passed in 57.37s.
- Worker profile/task targeted tests: 7 passed in 113.12s.
- Demo route regression: 1 passed in 14.77s.
- Task eligibility regressions: 2 passed in 84.84s.
- API contract real API E2E: passed on final patch state.
- Local XLSX export: not present.

## Remaining Risks

- The audit event table still lives with the current task-domain models in v0.1. Actor services now use a shared audit repository boundary, but a future audit module should own the model when actor/reputation work grows.
- Existing routes outside the chunk may continue using pure `get_current_actor` until deliberately migrated. This chunk adds registration side effects to `/auth/me`, worker profile setup, project routes, checker routes, and task routes touched here.
- The next Terminal Benchmark live API drill still needs to run through real HTTP calls against this implementation after PR review.
