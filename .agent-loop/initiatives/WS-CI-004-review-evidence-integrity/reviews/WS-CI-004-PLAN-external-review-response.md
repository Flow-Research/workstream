# External Review Response: WS-CI-004-PLAN

## Comments addressed

- Defined collision-safe typed receipt keys, Unicode normalization, injective
  encoding, separator rejection, symlink rejection, and root containment.
- Required a clean worktree for final verdicts and added local-change replay.
- Added the exact nine custom-agent to repository-skill mappings and excluded
  unmatched `plan-review` explicitly.
- Pinned external design sources by version or access date.
- Replaced the PR description with the repository trust-bundle structure.

## Comments deferred

None.

## Human decisions needed

Human approval remains required before merge and before any implementation step.

## Commands rerun

- `python3 scripts/check_markdown_links.py`
- `python3 scripts/check_stale_workstream_wording.py`
- `python3 scripts/check_stale_authorization_docs.py`
- `python3 scripts/check_chunk_state_sync.py --base-ref origin/main`
- `git diff --check`

## Remaining risks

The PR defines planning behavior only. Receipt and evaluator implementation must
still prove these contracts through the future explicitly started change.
