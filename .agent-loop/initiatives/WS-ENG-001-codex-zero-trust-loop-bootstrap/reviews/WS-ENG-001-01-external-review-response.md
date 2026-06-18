# External Review Response: WS-ENG-001-01

## PR

https://github.com/Flow-Research/workstream/pull/23

## Chunk

`WS-ENG-001-01`

## Source

CodeRabbit, GitHub checks, and human review feedback.

## Summary

External review feedback was handled separately from internal sub-agent evidence.
CodeRabbit findings hardened the engineering loop gates and templates. Human
review feedback corrected the artifact structure so internal review evidence
proves only the sub-agent review loop, while CodeRabbit/GitHub outcomes live in
this external review response file.

## External Findings

| Source | Finding | Severity | Status | Response |
|---|---|---:|---:|---|
| CodeRabbit | Shell interpolation in workflow command could be hardened. | High | Fixed | Moved `github.base_ref` into `BASE_REF` and quoted it in the workflow command. |
| CodeRabbit | Missing/deleted evidence files could fail unclearly. | Medium | Fixed | Added structured missing/unreadable evidence failures and regression coverage. |
| CodeRabbit | Markdown checker should skip unreadable or deleted changed files. | Medium | Fixed | Skips unreadable/deleted changed Markdown files. |
| CodeRabbit | Stale wording matcher needed case-insensitive patterns. | Low | Fixed | Added case-insensitive regex patterns for known obsolete Workstream terms. |
| CodeRabbit | Static sensor should fail closed on unresolved base refs. | Medium | Fixed | Resolves base refs before diff analysis and reports `BASE_REF_UNRESOLVED`. |
| CodeRabbit | Static sensor undercounted duplicate-path numstat entries. | Medium | Fixed | Accumulates additions/deletions per path across committed, staged, and dirty diffs. |
| CodeRabbit | Template wording and review checklist nitpicks. | Low | Fixed | Updated conditional reviewer wording, chunk-map template, remaining-risk template, external review DoD criteria, and explicit merge-approval checklist item. |
| CodeRabbit | Test monkeypatch restoration and stale-wording assertion order. | Low | Fixed | Added `try/finally` restore blocks and order-independent set comparison. |
| CodeRabbit | Docs reviewer Medium finding handling was ambiguous. | Low | Fixed | Requires Medium findings to appear in PASS WITH LOW RISKS or FAIL outcomes. |
| CodeRabbit | Product wording scope was broad. | Low | Fixed | Defines borderline product wording as human-owned decisions. |
| Human review | Internal review evidence was not bound to a reviewed revision. | High | Fixed | Requires reviewed code SHA, reviewed-at timestamp, reviewer run IDs, PR head SHA validation, and stale reviewed-SHA invalidation for non-evidence changes. |
| Human review | Reviewer routing and exact result handling needed hardening. | Medium | Fixed | Added demo UI route coverage, exact reviewer result parsing, N/A reason enforcement, and narrower stale-wording scope. |
| Human review | External review feedback was mixed into internal evidence. | High | Fixed | Added this external response artifact, updated templates/protocol/skill wording, and kept internal evidence focused on sub-agent review. |
| GitHub checks | Agent Gates, Backend, and Week 1 demo UI checks must pass. | High | Fixed | All checks passed after the final push. |

## Fix Plan

- Keep internal sub-agent evidence in `*-internal-review-evidence.md`.
- Keep CodeRabbit, GitHub checks, and human PR review responses in `*-external-review-response.md`.
- Ensure the internal evidence gate accepts only internal evidence files for initiative-scoped reviews.
- Update templates, protocol docs, and the external-review skill so future agents follow the separation by default.

## Out-of-Scope Items To Defer

None.

## Evidence After Fixes

```bash
python3 scripts/check_internal_review_evidence.py
python3 scripts/test_agent_gates.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 -m py_compile scripts/check_internal_review_evidence.py scripts/workstream_agent_gate.py scripts/check_stale_workstream_wording.py scripts/check_markdown_links.py scripts/test_agent_gates.py
git diff --check f3ed9af..6042c44
```

Final GitHub state after push:

```text
agent-gates: pass
backend test: pass
week1 demo UI: pass
CodeRabbit: pass, review skipped on final artifact-only push
```
