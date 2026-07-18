# Internal Review Evidence: WS-POL-001-15

## Chunk

WS-POL-001-15

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: 49101d4ad3fc22ec6e6065b1e593ef04145db953

Reviewed at: 2026-07-09T06:13:59Z

Reviewer run IDs: senior-engineering-final-reviewer-run-id, qa-test-final-reviewer-run-id, security-auth-final-reviewer-run-id, product-ops-final-reviewer-run-id, architecture-final-reviewer-run-id, docs-final-reviewer-run-id, reuse-dedup-final-reviewer-run-id, test-delta-final-reviewer-run-id, ci-integrity-final-reviewer-run-id

Current privacy-scrub chunk: `WS-POL-001-16-terminal-benchmark-live-api-drill`.
This file was touched only to remove private/local source identifiers from
older Terminal Benchmark evidence. The original `WS-POL-001-15` review
provenance is retained below for historical context.

Original reviewed revision:

Reviewed code SHA: b72a5b90979137d31127c2292f85ae350918f4f7

Reviewed at: 2026-07-08T16:23:01Z

Reviewer run IDs: senior-engineering-reviewer-run-id, qa-test-reviewer-run-id, security-auth-reviewer-run-id, product-ops-initial-reviewer-run-id, product-ops-final-reviewer-run-id, architecture-reviewer-run-id, docs-reviewer-run-id, reuse-dedup-reviewer-run-id, test-delta-reviewer-run-id

After the reviewed SHA, only evidence and review-bundle files changed.

## Reviewed Change

Scope:

- Added corrective chunk contract `WS-POL-001-15` after the accepted no-DB Terminal Benchmark drill from `main` failed during agent-derived submission artifact policy creation.
- Hardened `SubmissionArtifactPolicyDerivationAgent` instructions so derived policies must be project-level worker submission contracts, not reviewer packets or copies of source-snapshot material.
- Prohibited self-conflicting policies where forbidden artifact patterns match required artifact keys, paths, descriptions, required evidence keys, labels, or descriptions.
- Prohibited secret/credential/token wording in required artifact and evidence fields that the server treats as forbidden artifact surfaces.
- Required exact safe relative file paths for required artifacts; broad globs remain allowed only for forbidden artifact patterns.
- Added a prompt-contract regression test for the derivation instructions.
- Added a Terminal Benchmark-shaped validation case where `steps/milestone_1/tests/test_m1.py` is required while `steps/*/tests/*` is forbidden, preserving fail-closed server validation.
- Updated loop state, work queue, review log, status, chunk map, and roadmap status so the failed main-branch drill and corrective chunk are not stale.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS WITH LOW RISKS | None | Confirmed the fix is narrow and server validation remains the enforcement boundary. Low note: the prompt constant is growing. |
| qa/test | PASS WITH LOW RISKS | None | Confirmed acceptance criteria coverage, prompt-contract test, fail-closed validation regression, and live-drill evidence. Optional fake-runtime endpoint replay was noted as follow-up only. |
| security/auth | PASS WITH LOW RISKS | None | Found a low issue that descriptions were not explicitly covered by prompt wording; fixed before reviewed SHA. Confirmed default forbidden artifact validation remains fail-closed. |
| product/ops | PASS WITH LOW RISKS | None | Initial review failed on stale prompt-test assertions after security wording changed; assertions were fixed and final product/ops review passed. |
| architecture | PASS WITH LOW RISKS | None | Confirmed no task-level checker generation, new runtime provider, auth, model, migration, or checker boundary drift. |
| docs | PASS WITH LOW RISKS | None | Found stale current-gate wording in work queue, review log, and roadmap status; fixed before reviewed SHA. |
| reuse/dedup | PASS WITH LOW RISKS | None | Confirmed no duplicate validator/helper was added; the existing policy creation and forbidden-pattern path are reused. |
| test delta | PASS WITH LOW RISKS | None | Confirmed no tests were removed, skipped, or weakened. Low note: prompt string assertions are brittle but acceptable because the prompt is the contract. |

## Valid Findings Addressed

- Added required artifact and evidence descriptions to the derivation prompt's self-conflict prohibition.
- Added required evidence keys, labels, and descriptions to the secret/credential/token prompt prohibition.
- Updated prompt-pin test assertions to match the strengthened prompt wording.
- Updated `.agent-loop/WORK_QUEUE.md`, `.agent-loop/REVIEW_LOG.md`, and `docs/roadmap_status.md` so they no longer describe the accepted no-DB Terminal Benchmark drill as merely pending from `main`.
- Added `.agent-loop/WORK_QUEUE.md` to the `WS-POL-001-15` allowed-file lists after the docs review correctly identified it as in-scope state.
- Added the project-level artifact-intake criterion to the chunk-map summary so it matches the chunk contract.

## Commands Run

```bash
cd backend && .venv/bin/pytest tests/test_projects.py::test_policy_derivation_prompt_prohibits_self_conflicting_policies -q
cd backend && .venv/bin/pytest tests/test_projects.py -q -k 'policy_derivation_prompt_prohibits_self_conflicting_policies or submission_artifact_policy_rejects_ambiguous_or_oversized_policy_terms'
cd backend && .venv/bin/pytest tests/test_projects.py -q
bash -lc 'set -a; set +a; export WORKSTREAM_DATABASE_URL=<local-test-db-url>; export WORKSTREAM_PROJECT_AGENT_OPENAI_AGENT_SDK_MODEL=${WORKSTREAM_PROJECT_AGENT_OPENAI_AGENT_SDK_MODEL:-gpt-4.1}; export WORKSTREAM_TERMINAL_BENCH_FIXTURE=<redacted-local-fixture-path>; export WORKSTREAM_TERMINAL_BENCH_GUIDE_ROOT=<redacted-local-guide-root>; backend/.venv/bin/python examples/terminal_benchmark/terminal_benchmark_api_e2e.py'
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

Results:

- Prompt-contract test: `1 passed in 4.69s`.
- Targeted project subset: `16 passed, 193 deselected in 120.49s`.
- Full project suite on final diff: `209 passed in 1740.01s`.
- Terminal Benchmark real API E2E on final diff: passed with the real OpenAI Agents SDK derivation path.
- Terminal Benchmark scenario summary: `complete_packet=review_pending`, `missing_static_guard=pre_submit_blocked_no_submission`, `low_quality_v1=needs_revision`, `fixed_low_quality_v2=review_pending`, `worker_profile_setup=canonical_worker_profile_api`.
- Stale wording check: passed.
- Markdown link check: passed for 7 changed Markdown files.
- Diff whitespace check: passed.

## External Review Separation

CodeRabbit and GitHub checks are external review. They will be tracked
separately if comments arrive after the PR opens.

## Remaining Risks

- Prompt hardening improves the agent output contract, but the deterministic server guard remains the authority and may still reject invalid future model output.
- The server path validator already rejects empty/traversal/URL/storage/absolute paths; a stricter explicit no-glob path guard can be considered in a later checker-policy hardening chunk if real output requires it.
- A fake-runtime endpoint replay of the exact self-conflict could be added later, but the current chunk has shared-validator regression coverage and a passing real Terminal Benchmark API drill.
