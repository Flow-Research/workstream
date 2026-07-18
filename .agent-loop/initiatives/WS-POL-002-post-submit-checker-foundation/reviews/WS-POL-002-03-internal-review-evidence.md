# Internal Review Evidence: WS-POL-002-03

## Chunk

WS-POL-002-03 - Server-Owned Policy Approval And Visibility APIs

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: 0e59873971db8c2a7d9d6f9f7e725cb902eb888e

Reviewed at: 2026-07-11T18:04:17Z

Reviewer run ids: senior-engineering-019f5244-b92a, qa-test-019f5244-c46c, security-auth-019f5244-d62d, product-ops-019f5244-ec48, architecture-019f5244-f550, docs-019f5245-0359, reuse-dedup-019f5251-ac41, test-delta-019f5251-b004, ci-integrity-019f5251-b7d8

## Reviewed Change

Branch: `codex/ws-pol-002-03-post-submit-approval-visibility`

Scope:

- Adds operator-only setup visibility for generated project `PostSubmitCheckerPolicy` state.
- Adds server-owned approval and correction endpoints for generated post-submit checker policies.
- Keeps obsolete client-owned `post_submit_checker_policy` guide payloads rejected.
- Requires approved post-submit policy context to match the current guide, source snapshot, effective project policy, and compiled pre-submit checker.
- Records immutable approval provenance without accepting caller-provided approval notes.
- Supersedes and retains rejected compiled output, records bounded audit provenance,
  feeds correction feedback only into the exact matching setup context, rejects
  unchanged replacements, and requeues the existing setup continuation.
- Redacts raw source text, local paths, exact source hashes, source item refs, policy bodies, secrets, and credential-shaped values from setup visibility responses.
- Adds negative authorization coverage for worker, reviewer, finance, and auditor roles.
- Updates operator/product/data-model docs and active loop state for this chunk.
- Reconciles shared loop state while leaving the separately active WS-AUTH
  initiative files unchanged from `main`.

## Reviewer Results

These are Codex engineering-loop reviewer verdicts, not Workstream product
review decisions. Product review decisions remain `accept`, `needs_revision`,
and `reject`; internal reviewer agents report `PASS`, `PASS WITH LOW RISKS`,
`PASS AFTER FIXES`, or `FAIL` so process evidence stays separate from product
lifecycle records.

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS WITH LOW RISKS | None | Confirmed centralized append-only supersession and exact-context repository boundaries. |
| QA/test | PASS | None | Verified correction, upstream supersession, blank-reason rejection, stale-context isolation, and migration behavior. |
| security/auth | PASS | None | Initial credential-shaped redaction concern was fixed and retested with `sk-` style redaction in correction metadata. |
| product/ops | PASS WITH LOW RISKS | None | Confirmed correction is actionable, auditable, exact-context scoped, and distinct from upstream-policy supersession. |
| architecture | PASS WITH LOW RISKS | None | Confirmed zero WS-AUTH delta, append-only project policy boundaries, and setup-time-only agent use. |
| docs | PASS | None | Confirmed activation, supersession, correction, and migration 0015 wording across active docs. |
| reuse/dedup | PASS WITH LOW RISKS | None | Found no blocking duplication; service helpers stayed local to the projects boundary. |
| test delta | PASS WITH LOW RISKS | None | Requested broader leakage assertions; fixed by asserting policy body, source refs, source hashes, and guide text are absent. |
| CI integrity | PASS | None | Confirmed no CI weakening; Ruff, docstrings, focused projects, auth, and Alembic checks passed. |

## Valid Findings Addressed

- Removed caller-supplied approval notes from `PostSubmitCheckerPolicyApproval` so approval provenance is server-owned and no ignored input is accepted.
- Added credential-shape redaction for bounded setup summaries and correction metadata.
- Replaced destructive correction cleanup with append-only supersession and a
  partial unique index for the current compiled/approved policy.
- Added bounded correction feedback to the setup agent context and rejected an
  identical replacement policy hash.
- Scoped correction lookup/history to exact guide, source snapshot/hash,
  effective policy/hash, and pre-submit checker/hash provenance.
- Distinguished `correction_requested` from `upstream_policy_changed`; only
  same-context correction replacement uses `supersedes_policy_id`.
- Rejected whitespace-only correction reasons at API and database boundaries.
- Preserved safe correction history in the setup visibility response.
- Added bounded `derivation_input_summary` so operators can see source/effective/pre-submit context without raw source material or policy bodies.
- Changed product wording from "task display" to "operator-visible post-submit checker policy summary".
- Expanded tests to assert no policy body, source item ref, source item hash, raw source hash, or guide text leaks in setup visibility responses.
- Addressed review feedback that correction requests could be read as an
  activation alternative; product and operator docs now state correction blocks
  activation, preserves rejected output, and returns to correction-aware derivation.
- Addressed CodeRabbit feedback that loop artifacts had conflicting
  `WS-POL-002-03` lifecycle states; PR #90 is now represented as the active
  user-review chunk, while `WS-POL-002-04` and future WS-POL work remain
  inactive until explicit starts.

## Commands Run

```bash
cd backend && .venv/bin/pytest tests/test_projects.py::test_post_submit_checker_policy_approval_uses_server_provenance tests/test_projects.py::test_post_submit_checker_policy_correction_preserves_audit_and_guides_rederivation -q
cd backend && .venv/bin/pytest tests/test_projects.py -q -k "post_submit_checker_policy or post_submit_setup_visibility"
cd backend && .venv/bin/pytest tests/test_auth.py -q
cd backend && .venv/bin/pytest tests/test_alembic.py -q
cd backend && .venv/bin/pytest tests/test_projects.py::test_post_submit_checker_policy_correction_preserves_audit_and_guides_rederivation tests/test_projects.py::test_corrected_submission_artifact_policy_resumes_post_submit_setup tests/test_projects.py::test_database_rejects_superseded_post_submit_policy_without_correction_provenance -q
cd backend && .venv/bin/ruff check app tests scripts
cd backend && .venv/bin/docstr-coverage --config .docstr.yaml
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
python3 scripts/check_loop_memory_state.py
git diff --check
```

Results:

- Targeted approval/correction tests: 2 passed.
- Focused post-submit project setup slice: 9 passed, 225 deselected.
- Auth suite: 21 passed.
- Alembic suite: 6 passed.
- Final correction/upstream/database slice: 3 passed.
- Ruff: passed.
- Docstring coverage: 100%.
- Stale wording scan: passed.
- Markdown link check: passed.
- Loop memory state check: passed.
- Diff whitespace check: passed.

Rebind note:

- This evidence binds to the final non-evidence revision after all valid
  CodeRabbit and internal reviewer findings were addressed.
- WS-AUTH initiative files have no diff from `main`; the authorization worktree
  remains independent.

## Remaining Risks

- GitHub Actions and CodeRabbit must rerun after this evidence-only update is pushed.
- Project-scoped `project_manager` role grants remain future Workstream role-assignment work; this chunk keeps the current bootstrap authorization boundary and documents that limit.
- `WS-POL-002-04` still owns runtime hardening for locked post-submit policy execution and routing.
