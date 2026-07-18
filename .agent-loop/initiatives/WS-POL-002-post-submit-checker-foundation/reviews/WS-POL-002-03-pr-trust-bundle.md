# PR Trust Bundle: WS-POL-002-03

## Chunk

`WS-POL-002-03` - Server-Owned Policy Approval And Visibility APIs

## Reviewed Revision

Reviewed code SHA: `0e59873971db8c2a7d9d6f9f7e725cb902eb888e`

Reviewed at: `2026-07-11T18:04:17Z`

Internal review evidence:

- `.agent-loop/initiatives/WS-POL-002-post-submit-checker-foundation/reviews/WS-POL-002-03-internal-review-evidence.md`

## Goal

Expose generated post-submit checker setup state through safe APIs and replace
manual setup approval shortcuts with server-owned approval/correction actions.

## Human-Approved Intent

Post-submit setup mirrors the pre-submit separation:

```text
Project guide/source material
-> setup-time derivation agent
-> trusted Workstream compiler
-> generated project PostSubmitCheckerPolicy
-> setup-authorized admin/project_manager approval or correction request
-> active guide can lock the approved policy
```

The agent derives constrained setup policy. Workstream owns approval,
correction, visibility, and activation checks. The agent still does not judge
worker submissions at runtime.

## What Changed

- Added setup visibility endpoint:
  - `GET /api/v1/projects/{project_id}/guides/{guide_id}/post-submit-checker-policy/setup`
- Added server-owned approval endpoint:
  - `POST /api/v1/projects/{project_id}/guides/{guide_id}/post-submit-checker-policy/approve`
- Added server-owned correction endpoint:
  - `POST /api/v1/projects/{project_id}/guides/{guide_id}/post-submit-checker-policy/request-correction`
- Added safe setup summaries that expose IDs, lifecycle status, checker counts/names, policy hash, approval provenance, and bounded derivation input context.
- Kept raw source text, local paths, exact source hashes, source item refs, policy bodies, and credential-shaped strings out of setup visibility responses.
- Added row-locking and current-context validation before approval/correction.
- Made approval idempotent without rewriting existing approval provenance.
- Made correction supersede and retain rejected compiled output with bounded
  actor/role/time/reason provenance, feed feedback only into the exact matching
  setup context, reject unchanged replacement hashes, and requeue continuation.
- Distinguished correction from upstream-policy supersession and added
  migration `0015_post_submit_correction` with append-only audit rows plus
  current-policy uniqueness.
- Updated docs and loop state to reflect the new server-owned setup boundary.
- Reconciled shared loop state so PR #90 is current while leaving WS-AUTH
  initiative files unchanged for the separate authorization worktree.

## Design Chosen

Approval is a server-owned state transition, not a client patch:

```text
compiled policy
-> lock guide and policy rows
-> validate guide/source/effective/pre-submit/setup-run context
-> mark policy approved with server actor/role/time provenance
-> return safe setup summary
```

Correction is also server-owned and append-only:

```text
draft guide + unapproved compiled policy
-> lock exact setup context
-> supersede and retain rejected policy/hash/body
-> record bounded actor/role/time/reason provenance
-> enqueue correction-aware setup continuation after commit
-> reject unchanged replacement hash
```

## Alternatives Rejected

- Client-provided approval notes: rejected because they were not consumed by the domain model and could become misleading ignored input.
- Worker-visible policy bodies: rejected. Workers only need actionable checker results later in runtime flows.
- Manual guide payload policy fields: rejected. Generated setup output is the authoritative path.
- Destructive correction cleanup: rejected because it loses audit provenance.
- Unscoped correction feedback: rejected because stale feedback must never cross
  source/effective/pre-submit setup contexts.
- Runtime agent judgment: rejected. Runtime remains deterministic checker execution.

## Scope Control

This chunk stays inside project setup visibility and approval. It does not
change task runtime, checker runtime, frontend/demo work, payment, reputation,
blockchain settlement, reviewer decision records, or per-task checker policy
generation.

## Acceptance Criteria Proof

- Project setup APIs show generated post-submit policy status without database inspection.
- Guide create/update still rejects obsolete `post_submit_checker_policy` payload fields.
- Guide activation blocks unless the compiled post-submit policy is approved and matches the current guide/source/effective/pre-submit context.
- Approval provenance is server-owned, immutable on retry, and records actor id, role, timestamp, source snapshot id/hash, and compiled policy hash.
- Setup visibility does not leak internal policy body details, raw source material, local source refs, exact source hashes, or credential-shaped correction text.
- Worker, reviewer, finance, and auditor roles are denied on setup visibility, approval, and correction endpoints.
- Correction preserves rejected output, returns bounded audit history, and
  requeues exact-context correction-aware derivation rather than becoming a
  dead end.

## Tests/Checks Run

```bash
cd backend && .venv/bin/pytest tests/test_projects.py::test_post_submit_checker_policy_approval_uses_server_provenance tests/test_projects.py::test_post_submit_checker_policy_correction_clears_unapproved_output -q
cd backend && .venv/bin/pytest tests/test_projects.py -q -k "post_submit_checker_policy or post_submit_setup_visibility"
cd backend && .venv/bin/pytest tests/test_auth.py -q
cd backend && .venv/bin/pytest tests/test_alembic.py -q
cd backend && .venv/bin/pytest tests/test_projects.py::test_post_submit_checker_policy_correction_preserves_audit_and_guides_rederivation tests/test_projects.py::test_corrected_submission_artifact_policy_resumes_post_submit_setup tests/test_projects.py::test_database_rejects_superseded_post_submit_policy_without_correction_provenance -q
cd backend && .venv/bin/ruff check app tests scripts
cd backend && .venv/bin/docstr-coverage --config .docstr.yaml
cd backend && .venv/bin/pytest tests/test_projects.py tests/test_auth.py -q
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

Result summary:

- Targeted approval/correction tests: 2 passed.
- Focused post-submit project setup slice: 9 passed.
- Auth suite: 21 passed.
- Alembic suite: 6 passed.
- Final correction/upstream/database slice: 3 passed.
- Ruff: passed.
- Docstring coverage: 100%.
- Stale wording scan: passed.
- Markdown link check: passed.
- Diff whitespace check: passed.

## Reviewer Results

These are Codex engineering-loop reviewer verdicts, not Workstream product
review decisions. Product review decisions remain `accept`, `needs_revision`,
and `reject`; internal reviewer agents report `PASS`, `PASS WITH LOW RISKS`,
`PASS AFTER FIXES`, or `FAIL` so process evidence stays separate from product
lifecycle records.

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS WITH LOW RISKS | None | Service/repository boundary stayed narrow. |
| QA/test | PASS | None | Correction, upstream supersession, blank reason, stale-context, and migration cases passed. |
| security/auth | PASS | None | Credential-shaped redaction and non-setup role denials covered. |
| product/ops | PASS WITH LOW RISKS | None | Correction is actionable, auditable, and exact-context scoped. |
| architecture | PASS WITH LOW RISKS | None | Append-only project boundary and zero WS-AUTH delta confirmed. |
| docs | PASS | None | Active docs and migration 0015 are aligned. |
| reuse/dedup | PASS WITH LOW RISKS | None | No blocking reuse issues. |
| test delta | PASS WITH LOW RISKS | None | Leak assertions broadened. |
| CI integrity | PASS | None | No CI/test weakening found; local CI-equivalent checks passed. |

## External Review

External review response:

- `.agent-loop/initiatives/WS-POL-002-post-submit-checker-foundation/reviews/WS-POL-002-03-external-review-response.md`

Earlier CodeRabbit and GitHub Actions runs passed on the prior pushed head. The
current implementation and review-response fixes are bound to non-evidence
commit `0e59873971db8c2a7d9d6f9f7e725cb902eb888e`; external checks must rerun on
the evidence-only pushed head before merge.

## Remaining Risks

- The current bootstrap authorization still treats global `admin` and
  `project_manager` as setup-authorized; project-scoped role assignment remains
  future Workstream role work.
- `WS-POL-002-04` still owns runtime hardening for locked post-submit policy
  execution and routing.

## Human Review Focus

- Confirm there is one authoritative server-owned post-submit policy approval path.
- Confirm correction preserves rejected-policy audit history, scopes feedback
  to the exact setup context, and resumes derivation without accepting an
  unchanged replacement.
- Confirm operator visibility is useful without leaking source/policy secrets.
- Confirm worker-facing APIs remain out of scope for setup internals.

## Human Merge Ownership

Only the user can approve and merge this PR. Codex must not merge it without
explicit user approval for this specific PR.
