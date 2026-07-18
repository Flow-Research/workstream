# PR Trust Bundle: WS-POL-001-15

## Intent

Fix the real Terminal Benchmark no-DB API drill failure where the OpenAI Agents
SDK derivation agent emitted a self-conflicting project submission artifact
policy: a required artifact and forbidden artifact pattern matched each other.

The fix must keep Workstream defaults strict. The server should still reject
unsafe or self-conflicting policies; the agent prompt should steer the model
away from producing those invalid policies.

## Scope

Changed:

- `backend/app/adapters/project_agents/openai_agent_sdk.py`
- `backend/tests/test_projects.py`
- `.agent-loop/LOOP_STATE.md`
- `.agent-loop/WORK_QUEUE.md`
- `.agent-loop/REVIEW_LOG.md`
- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/CHUNK_MAP.md`
- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/STATUS.md`
- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/chunks/WS-POL-001-15-agent-derivation-policy-conflict-hardening.md`
- `docs/roadmap_status.md`

Not changed:

- No migrations.
- No auth adapter changes.
- No task/checker runtime changes.
- No project model/router/repository changes.
- No new agent runtime provider.
- No weakening of Workstream default forbidden artifact validation.

## Design

The derivation prompt now requires:

- a project-level worker submission contract;
- source/reviewer/example material to be context, not automatically required worker artifacts;
- no forbidden pattern overlap with required artifact or evidence fields;
- no secret/credential/token wording in required artifact or evidence fields;
- exact safe relative file paths for required artifacts, with globs limited to forbidden artifact patterns.

The deterministic server validation remains the enforcement layer. If the agent
still emits invalid policy, setup still fails closed.

## Verification

Passed:

```bash
cd backend && .venv/bin/pytest tests/test_projects.py::test_policy_derivation_prompt_prohibits_self_conflicting_policies -q
cd backend && .venv/bin/pytest tests/test_projects.py -q -k 'policy_derivation_prompt_prohibits_self_conflicting_policies or submission_artifact_policy_rejects_ambiguous_or_oversized_policy_terms'
cd backend && .venv/bin/pytest tests/test_projects.py -q
bash -lc 'set -a; set +a; export WORKSTREAM_DATABASE_URL=<local-test-db-url>; export WORKSTREAM_PROJECT_AGENT_OPENAI_AGENT_SDK_MODEL=${WORKSTREAM_PROJECT_AGENT_OPENAI_AGENT_SDK_MODEL:-gpt-4.1}; export WORKSTREAM_TERMINAL_BENCH_FIXTURE=<redacted-local-fixture-path>; export WORKSTREAM_TERMINAL_BENCH_GUIDE_ROOT=<redacted-local-guide-root>; backend/.venv/bin/python examples/terminal_benchmark/terminal_benchmark_api_e2e.py'
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

Key results:

- `209 passed in 1740.01s` for `tests/test_projects.py`.
- Terminal Benchmark real API E2E passed after derivation, activation, task
  locked context, pre-submit blocking, finalization, checker-run reads, audit
  reads, `needs_revision`, and fixed v2 finalization.
- Scenario summary included `complete_packet=review_pending`,
  `missing_static_guard=pre_submit_blocked_no_submission`,
  `low_quality_v1=needs_revision`, and `fixed_low_quality_v2=review_pending`.
- Stale wording, Markdown links, and whitespace checks passed.

## Internal Review

| Reviewer | Result |
|---|---:|
| senior engineering | PASS WITH LOW RISKS |
| QA/test | PASS WITH LOW RISKS |
| security/auth | PASS WITH LOW RISKS |
| product/ops | PASS WITH LOW RISKS after fixing stale assertions |
| architecture | PASS WITH LOW RISKS |
| docs | PASS WITH LOW RISKS after state wording fixes |
| reuse/dedup | PASS WITH LOW RISKS |
| test delta | PASS WITH LOW RISKS |

Evidence:

- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-15-internal-review-evidence.md`

## Human Review Focus

- Confirm the prompt wording matches the product intent: project-level worker
  submission artifact policy, not task-specific checker generation.
- Confirm server validation remains the source of truth and still fails closed.
- Confirm loop state accurately records why `WS-POL-001-15` exists.

## Remaining Risks

- Prompt hardening does not guarantee all future model output is valid. The
  server guard remains responsible for rejecting invalid policies.
- A future hardening chunk can make explicit no-glob required artifact path
  validation server-side if real output shows that gap again.
