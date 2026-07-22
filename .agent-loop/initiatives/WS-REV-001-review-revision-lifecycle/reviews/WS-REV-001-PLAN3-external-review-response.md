# External Review Response: WS-REV-001-PLAN3

## Comments addressed

- Retired 02A/02B/02C contracts now state that every remaining section is
  archival, void, and non-authorizing, including operational, schema/database,
  acceptance, verification, merge, and successor guidance.
- The historical checker-remediation statement no longer assigns lineage work
  to retired 02C; any missing capability is explicitly Checker/Submission owner
  work consumed by REV.
- PLAN labels its stale dependency bullets as historical PLAN2 facts.
- Internal evidence and the trust bundle now include required provenance and one
  structured row for every reviewer track.
- CI's internal-review-evidence failure has the same root cause as the fourth
  comment and is repaired by the schema-complete evidence block.

## Comments deferred

None.

## Human decisions needed

None for these repairs. Human approval remains required before PR merge.

## Commands rerun

- `python3 scripts/check_internal_review_evidence.py`
- `python3 scripts/update_post_merge_memory.py validate-merge-intent --base-ref origin/main`
- `python3 scripts/check_markdown_links.py`
- `python3 scripts/check_stale_workstream_wording.py`
- `python3 scripts/test_agent_gates.py`
- `git diff --check origin/main...HEAD`

## Remaining risks

Fresh GitHub and CodeRabbit checks must pass on the pushed repair head. Merge
still does not authorize 03P; it requires a separate signed start.
