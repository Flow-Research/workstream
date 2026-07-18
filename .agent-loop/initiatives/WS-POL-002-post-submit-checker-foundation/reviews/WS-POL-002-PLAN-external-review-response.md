# External Review Response

## PR

`https://github.com/Flow-Research/workstream/pull/85`

## Chunk

`WS-POL-002-PLAN`

## Source

CodeRabbit / GitHub checks

## Summary

CodeRabbit flagged missing PR-description structure, one inconsistent chunk
title, a missing risk-class declaration, and incomplete committed-evidence hash
redaction wording. GitHub Actions failed because internal review evidence was
not bound to the reviewed code SHA and had reviewer run IDs on separate lines.

## External Findings

| Source | Finding | Severity | Status | Response |
|---|---|---:|---:|---|
| CodeRabbit | PR description omitted required trust-bundle sections. | Warning | Fixed | Added a committed PR trust bundle and updated the PR body with the same structure. |
| CodeRabbit | `WS-POL-002-01` title differed between `STATUS.md` and `CHUNK_MAP.md`. | Trivial | Fixed | Normalized `STATUS.md` to `Post-Submit Provenance And Compiler Contract`. |
| CodeRabbit | `WS-POL-002-05` omitted explicit risk class. | Minor | Fixed | Added `Risk class: L1`; internal review then required the same metadata across every WS-POL-002 chunk contract. |
| CodeRabbit | Privacy scan acceptance criteria rejected raw source hashes but not raw policy hashes. | Major | Fixed | Updated the live proof contract to reject exact source and policy hashes and require `sha256:<redacted>` placeholders. |
| GitHub Actions | Agent Gates and Backend failed internal review evidence validation. | Major | Fixed locally | Replaced stale `Base SHA` evidence with `Reviewed code SHA` and same-line reviewer run IDs. |

## Fix plan

- Normalize the first implementation chunk title.
- Add approved-plan reference, risk class, SLA, and stop conditions to every
  WS-POL-002 chunk contract.
- Tighten evidence privacy wording for source hashes, policy hashes, and
  actor/source/setup identifiers.
- Add this external review response and a PR trust bundle.
- Update internal review evidence to bind reviewer output to
  `f07160145fd5b92515cfbbd1c78c81a583a86508`.
- Rerun local gates, push the branch, and allow GitHub checks and CodeRabbit to
  rerun on the updated PR head.

## Out-of-scope items to defer

None.

## Evidence after fixes

```bash
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
python3 scripts/check_internal_review_evidence.py
git diff --check
```

Expected PR follow-up:

```text
GitHub Actions and CodeRabbit must rerun on the pushed branch head before merge.
```
