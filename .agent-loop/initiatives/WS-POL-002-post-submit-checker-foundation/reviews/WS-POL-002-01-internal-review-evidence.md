# Internal Review Evidence: WS-POL-002-01

## Chunk

WS-POL-002-01

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: 438361aeda2d7655384b9d86d3ccdf0c5c44f0d1

Reviewed at: 2026-07-09T17:54:38Z

Reviewer run IDs: senior-engineering-019f4800-640f-7073-bb9e-8b0a9fe4bd1a, qa-test-019f47f8-14e8-7b53-ae3b-0bb1156e7347, security-auth-019f47f8-1ff9-7bb1-8a73-610a944cec0d, product-ops-019f47f8-34ee-7c91-a47c-47ed2556b1ae, architecture-019f47f8-569e-77f2-a998-3a5ee02493a6, docs-019f47fc-8e3e-7cf2-82ab-83c62be2a42f, reuse-dedup-019f479e-04bb-7063-9df0-2a6c5b2d20d6, test-delta-019f4801-ea4b-7191-96d6-be8efa6339df, ci-integrity-019f479e-2886-7f53-8777-b7f93f4a033b

## Reviewed Change

Branch: `codex/ws-pol-002-01-post-submit-compiler`

Scope:

- Adds the trusted project-scoped post-submit checker compiler contract.
- Keeps compiler ownership in `backend/app/modules/projects/post_submit_policy.py`.
- Keeps the pre-submit compiler module separate and unmodified.
- Makes default-only project post-submit policies valid while preserving
  mandatory platform defaults through `default_checkers` and
  `execution_checkers`.
- Fails closed on unknown checker names, duplicate/conflicting classifications,
  warning-only default overrides, non-list spec fields, compiler-version
  default drift, and blocking severity downgrades.
- Maps compiler failures to generic API-safe setup errors.
- Aligns existing real API drill payloads with the non-weakenable
  `["critical", "high"]` severity floor.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS WITH LOW RISKS | None | Confirmed implementation simplicity and truthful pending external-check status after fixes. |
| QA/test | PASS WITH LOW RISKS | None | Confirmed versioned locked-body validation and snapshot tests; future v0.2 should add multi-version fixture. |
| security/auth | PASS WITH LOW RISKS | None | Confirmed unsupported compiler versions fail closed, policy hash binds body, and mutable defaults no longer weaken locked execution. |
| product/ops | PASS WITH LOW RISKS | None | Confirmed locked v0.1 task/submission/checker context stays fair after future default changes. |
| architecture | PASS WITH LOW RISKS | None | Confirmed compiler-owned boundary and frozen v0.1 snapshot; data model clarified the snapshot invariant. |
| docs | PASS | None | Confirmed stale 422/default-current wording is removed and compiler_version is documented. |
| reuse/dedup | PASS WITH LOW RISKS | None | Low future drift risk from duplicating severity literals; no blocking missed abstraction. |
| test delta | PASS | None | Confirmed additive tests and no skipped, xfailed, or weakened tests. |
| ci integrity | PASS WITH LOW RISKS | None | No workflow/config weakening; full CI still runs complete backend pytest. |

## Valid Findings Addressed

- Pre-implementation architecture review found the chunk too broad. The chunk
  contract was narrowed to compiler/body/hash behavior only.
- Reviewers found the locked parser accepted severity downgrade and default-list
  drift scenarios. The parser now requires the frozen default-checker snapshot
  for the stamped compiler version, canonical execution list, matching hash, and
  the critical/high severity floor.
- Reviewers found compiler errors could leak raw checker details through API
  setup paths. Project service now maps compiler failures to
  `post-submit checker policy compilation failed`.
- Security review found an activation fallback could leak raw unregistered
  checker names for corrupted persisted rows. Activation now returns a generic
  unregistered-checker message.
- Test-delta found missing API-level explicit empty severity coverage and
  weaker locked-body drift coverage. Added guide-create API coverage for
  `blocking_severities: []`, self-consistent versioned locked defaults,
  conflicting locked classifications, and raw-spec downgrade tests.
- QA found tuple-shaped spec fields were still accepted by the shared validator.
  The compiler now accepts only JSON-list-shaped `list` values and has a
  tuple-spec regression test.
- Docs review found data-model wording overstated locked-body independence from
  future default-list compatibility. Updated the docs to require an approved
  versioning, compatibility, or migration path for future default-list changes.
- Product/ops and QA found stale live-drill payloads with old severity lists.
  Updated the API contract and Terminal Benchmark example payloads to include
  `critical` and `high`.
- Senior/product/docs initially failed only because final evidence artifacts
  were missing. This evidence file and the PR trust bundle address that process
  blocker.
- Final re-review found and resolved the stronger invariant: v0.1 default
  checkers are now a literal frozen tuple, the version map is immutable, and the
  parser validates locked bodies against the snapshot for their stamped
  `compiler_version`.

## Commands Run

```bash
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
cd backend && .venv/bin/ruff check app/modules/projects/post_submit_policy.py app/modules/projects/service.py app/modules/projects/schemas.py tests/test_checkers.py tests/test_projects.py tests/test_tasks.py scripts/api_contract_e2e.py ../examples/terminal_benchmark/terminal_benchmark_api_e2e.py
cd backend && .venv/bin/pytest tests/test_projects.py -q -k 'default_only_post_submit or unregistered_checker_names or post_submit_compiler_validation'
cd backend && .venv/bin/pytest tests/test_checkers.py -q
cd backend && .venv/bin/pytest tests/test_projects.py tests/test_checkers.py -q
cd backend && .venv/bin/pytest tests/test_checkers.py::test_post_submit_compiler_accepts_default_only_policy tests/test_checkers.py::test_locked_post_submit_policy_parser_uses_v01_snapshot_not_current_defaults tests/test_tasks.py::test_screening_uses_versioned_post_submit_policy_body_after_default_drift -q
```

Results:

- Stale wording scan: passed.
- Markdown link check: passed for 22 changed Markdown files.
- Diff whitespace check: passed.
- Ruff: passed.
- Focused project API compiler slice: 5 passed, 208 deselected.
- Full checker suite: 75 passed.
- Focused final snapshot/task slice: 3 passed.
- Exact contracted backend command: 282 passed in 2494.22s.

## Remaining Risks

- Reuse/dedup noted a low future drift risk because
  `post_submit_policy.py` owns explicit ordered severity strings while
  `checkers.runner` also has severity constants. This is accepted for this
  chunk because the compiler floor is a policy contract; future severity model
  changes should consolidate or version this intentionally.
- CI integrity noted the local chunk contract no longer lists Alembic tests.
  This is accepted because this compiler-only chunk does not change models,
  repositories, or migrations, and backend CI still runs full `pytest -q`.
- CodeRabbit and GitHub Actions passed on the previous push. They must rerun
  after this fix push, and any new external comments must be recorded
  separately in `WS-POL-002-01-external-review-response.md`.
