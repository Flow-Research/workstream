# WS-XINT-001-PLAN External Review Response

## PR

`#139` - https://github.com/Flow-Research/workstream/pull/139

## Chunk

`WS-XINT-001-PLAN`

## Source

GitHub checks and CodeRabbit

## Summary

The initial Agent Gates and Backend runs both stopped at the internal review
evidence gate. CI does not set the local `INTERNAL_REVIEW_CHUNK_ID` override,
and the former filename parser did not recognize the canonical
`WS-XINT-001-PLAN` chunk ID. CodeRabbit returned a successful status but skipped
review because 127 changed files exceed its 100-file limit.

## External Findings

| Source | Finding | Severity | Status | Response |
|---|---|---:|---:|---|
| GitHub Agent Gates | Internal evidence did not match any filename-derived numeric chunk ID. | High | Fixed | Evidence binding now reads exact IDs from canonical contract headings and exact-matches lifecycle tokens. |
| GitHub Backend | Same evidence-gate failure occurred before backend tests. | High | Fixed | The shared gate repair fixes both workflows; product runtime was unchanged. |
| CodeRabbit | Review skipped because 127 files exceed the 100-file review limit. | Informational | Documented | Internal nine-track exact-SHA review remains complete; no CodeRabbit finding exists to address. |

## Fix Plan

- Extract changed chunk IDs from canonical contract headings rather than
  partial filename regexes.
- Parse complete lifecycle tokens from evidence and compare exact normalized
  IDs so sibling prefixes cannot satisfy the gate.
- Fail closed on missing, empty, malformed, invalid-UTF-8, and unreadable
  changed contracts.
- Add regression coverage for all tracked heading forms, named/compound/revision
  IDs, prefix collisions, and every fail-closed read condition.
- Document the canonical first-line heading in the chunk producer skill and
  template.

## Out-of-Scope Items To Defer

None.

## Evidence After Fixes

```bash
python3 scripts/check_internal_review_evidence.py
python3 scripts/test_agent_gates.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_stale_workstream_wording.py
python3 -m ruff check scripts/check_internal_review_evidence.py scripts/test_agent_gates.py
python3 -m ruff format --check scripts/check_internal_review_evidence.py scripts/test_agent_gates.py
git diff --check
```

Local result: PASS. All 97 tracked contracts produced unique exact IDs; all 80
agent-gate tests passed. Remote GitHub rerun is pending the repaired push.
