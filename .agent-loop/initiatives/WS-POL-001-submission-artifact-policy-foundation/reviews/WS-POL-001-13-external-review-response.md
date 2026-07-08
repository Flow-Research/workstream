# External Review Response: WS-POL-001-13

## PR

PR #77: https://github.com/Flow-Research/workstream/pull/77

## Chunk

`WS-POL-001-13`

## Source

CodeRabbit

## Summary

CodeRabbit reported one valid test-maintainability nitpick and one PR
description warning. No product, architecture, security, authorization, or API
contract changes were requested.

## External Findings

| Source | Finding | Severity | Status | Response |
|---|---|---:|---:|---|
| CodeRabbit | The malformed locked-context regression test read `pre_submit_policy.compiled_bundle` after `session.delete()` and `flush()`. | Trivial | Addressed | Captured `original_compiled_bundle` before deleting the ORM row and used the saved bundle when constructing the malformed checker bundle. |
| CodeRabbit | The PR description omitted explicit template sections for chunk, goal, changed behavior, acceptance proof, and test delta. | Warning | Addressed | Reshaped the PR trust bundle and PR body around the required review sections. |

## Fix plan

- Update `backend/tests/test_tasks.py` so the malformed locked-context test does
  not dereference a deleted ORM instance.
- Update the PR trust bundle with explicit review-template headings.
- Record this external review response separately from internal review
  evidence.
- Update the GitHub PR body from the corrected trust bundle.

## Out-of-scope items to defer

None.

## Evidence after fixes

```bash
cd backend && .venv/bin/pytest tests/test_tasks.py::test_submission_requirements_fail_closed_on_hash_consistent_malformed_policy_shape -q
cd backend && .venv/bin/python -m ruff check tests/test_tasks.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

Result summary:

```text
Focused pytest: 1 passed
Ruff: All checks passed
Stale wording: passed
Markdown links: passed for changed Markdown files
git diff --check: passed
```
