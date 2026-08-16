# External Review Response: WS-CI-004-03

## CodeRabbit review at `d55c9b14bb867521d4d529622fc31a425535b45d`

Comments addressed:

- CP03B projections now consistently distinguish its complete executable
  contract from its planned, unmerged implementation.
- The branch-protection verification command uses `jq -e` to assert every
  required setting and fail on a mismatch.
- The contribution boundary's CP02 and CP03A rows use durable `Complete`
  values while preserving their unavailable-action notes.
- `CONTRIBUTING.md` explicitly requires the user's approval of the specific
  pull request in addition to maintainer approval and branch protection.
- The broader exact-head replay found two equivalent temporal phrases that the
  initial scanner missed. The scanner now rejects every case-insensitive
  `on merge` occurrence in active projections, regression tests cover
  `Outcome on merge` and `lands on merge`, and both stale active rows are
  reconciled.

Comments deferred:

- None.

Human decisions needed:

- The user must approve this specific pull request after the final push. The
  latest pusher cannot supply the branch-protection approval.

Commands rerun:

```text
python3 -m unittest -v scripts.test_active_state_projections scripts.test_chunk_state_sync scripts.test_lightweight_agent_gates
python3 scripts/check_active_state_projections.py
python3 scripts/check_chunk_state_sync.py --base-ref origin/main
python3 scripts/check_markdown_links.py
git diff --check
```

Remaining risks:

- External and internal review receipts for earlier heads become stale after
  this correction and must be rerun against the final clean head.
